/**
 * 日程案表示画面
 * requirements.md §4.7
 *
 * Phase 4.4a: 日付×時間枠マトリクス表示 + 解なし情報表示（read-only）
 * Phase 4.4b: ドラッグ&ドロップ（dnd-kit）+ 候補日時外移動の警告
 * Phase 4.4c: 保存ボタン（次フェーズ）
 */

import { useState, useEffect, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  DndContext,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
import type { DragEndEvent } from '@dnd-kit/core'
import { scheduleApi, projectsApi, responsesApi, draftsApi } from '../api'
import type {
  SchedulingResult,
  Assignment,
  Project,
  Response as ApiResponse,
  Draft,
} from '../api/types'

// ===== 公開ユーティリティ関数（テスト用エクスポート）=====

/** "HH:MM:SS" → "HH:MM" に変換する */
export function toHHMM(timeStr: string): string {
  return timeStr.slice(0, 5)
}

/**
 * ドラッグ&ドロップ後の割り当て配列を返す純粋関数。
 * フロムキー・トゥキーはいずれも "date|HH:MM" 形式。
 * - 両スロットに生徒がいる場合: 生徒番号をスワップ（スロット位置は固定）
 * - 移動先が空きの場合: 生徒を空きスロットへ移動
 */
export function applyDrop(
  assignments: Assignment[],
  fromKey: string,
  toKey: string,
  candidateTimeSlots: Array<{ start: string; end: string }>,
): Assignment[] {
  const [fromDate, fromStart] = fromKey.split('|')
  const [toDate, toStart] = toKey.split('|')

  const fromIdx = assignments.findIndex(
    (a) => a.date === fromDate && toHHMM(a.start) === fromStart,
  )
  if (fromIdx === -1) return assignments

  const toIdx = assignments.findIndex(
    (a) => a.date === toDate && toHHMM(a.start) === toStart,
  )

  const movedStudent = assignments[fromIdx].student_number
  const result = assignments.map((a) => ({ ...a }))

  if (toIdx !== -1) {
    // スワップ: 生徒番号のみ交換、スロット位置は固定
    const toStudent = result[toIdx].student_number
    result[fromIdx] = { ...result[fromIdx], student_number: toStudent }
    result[toIdx] = { ...result[toIdx], student_number: movedStudent }
  } else {
    // 空きスロットへ移動
    const slot = candidateTimeSlots.find((s) => s.start === toStart)
    const toEnd = slot != null ? `${slot.end}:00` : assignments[fromIdx].end
    result.splice(fromIdx, 1)
    result.push({
      student_number: movedStudent,
      date: toDate,
      start: `${toStart}:00`,
      end: toEnd,
    })
  }

  return result
}

/**
 * 既存ドラフトに新規スケジューリング結果をマージする純粋関数。
 *
 * 方針:
 *  - 既存ドラフトの assignments は固定（再スケジュール対象外）
 *  - 新規スケジュール結果のうち、既存ドラフトのスロットと競合するものは未配置に回す
 *  - unassigned_students / violated_constraints は重複排除のうえ結合
 */
export function mergeWithExistingDraft(
  existing: Draft,
  added: SchedulingResult,
): SchedulingResult {
  const occupied = new Set<string>(
    existing.assignments.map((a) => `${a.date}|${toHHMM(a.start)}`),
  )

  const mergedAssignments: Assignment[] = [...existing.assignments]
  const conflictedStudents: number[] = []

  for (const a of added.assignments) {
    const key = `${a.date}|${toHHMM(a.start)}`
    if (occupied.has(key)) {
      conflictedStudents.push(a.student_number)
    } else {
      mergedAssignments.push(a)
      occupied.add(key)
    }
  }

  const unassignedSet = new Set<number>([
    ...existing.unassigned_students,
    ...added.unassigned_students,
    ...conflictedStudents,
  ])

  const violated = [
    ...existing.violated_constraints,
    ...added.violated_constraints,
  ]
  if (conflictedStudents.length > 0) {
    violated.push(
      `既存ドラフトのスロットと競合したため未配置にした生徒: ${[...conflictedStudents]
        .sort((a, b) => a - b)
        .join(', ')}`,
    )
  }

  return {
    assignments: mergedAssignments,
    unassigned_students: Array.from(unassignedSet).sort((a, b) => a - b),
    violated_constraints: violated,
  }
}

/**
 * 配置の検証: 重複と名簿外（認可済みを除く）を検出する純粋関数。
 * - duplicates: 同じ出席番号が複数の assignment に出現するもの
 * - outOfRoster: roster にも authorizedExtras にも含まれない出席番号
 */
export function validateAssignments(
  assignments: Assignment[],
  roster: number[],
  authorizedExtras: number[],
): { duplicates: number[]; outOfRoster: number[] } {
  const counts = new Map<number, number>()
  for (const a of assignments) {
    counts.set(a.student_number, (counts.get(a.student_number) ?? 0) + 1)
  }
  const duplicates = [...counts.entries()]
    .filter(([, c]) => c > 1)
    .map(([sn]) => sn)
    .sort((a, b) => a - b)

  const rosterSet = new Set(roster)
  const authSet = new Set(authorizedExtras)
  const outOfRoster = Array.from(
    new Set(
      assignments
        .map((a) => a.student_number)
        .filter((sn) => !rosterSet.has(sn) && !authSet.has(sn)),
    ),
  ).sort((a, b) => a - b)

  return { duplicates, outOfRoster }
}

/**
 * 指定の生徒が指定のスロットを候補日時として回答しているか判定する。
 * responses が空または該当生徒のデータなし → true（候補内扱い）
 *
 * 比較は HH:MM に正規化してから行う。backend は time を "HH:MM:SS" で
 * シリアライズするが、呼び出し側（マトリクスのセル ID）は "HH:MM" を渡す
 * ことが多いため、両端を toHHMM で揃える。
 */
export function isInAvailability(
  studentNumber: number,
  date: string,
  startHHMM: string,
  responses: ApiResponse[],
): boolean {
  const studentResponse = responses.find((r) => r.student_number === studentNumber)
  if (!studentResponse) return true
  const target = toHHMM(startHHMM)
  return studentResponse.availability.some(
    (av) => av.date === date && toHHMM(av.start) === target,
  )
}

// ===== 名簿外確認ダイアログ（エクスポート: テスト用）=====

export interface ExtraStudentsConfirmDialogProps {
  /** 名簿外として検出された出席番号 */
  extras: number[]
  /** 「日程案に含める」選択時 */
  onInclude: () => void
  /** 「除外する」選択時 */
  onExclude: () => void
}

/**
 * 名簿外の出席番号から回答が来ている場合に表示する確認ダイアログ。
 * スケジューリング実行前に表示し、日程案に含めるか除外するかをユーザーに尋ねる。
 */
export function ExtraStudentsConfirmDialog({
  extras,
  onInclude,
  onExclude,
}: ExtraStudentsConfirmDialogProps) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      data-testid="extras-confirm-dialog"
      style={{
        position: 'fixed',
        top: '50%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
        backgroundColor: '#fff',
        border: '2px solid #2563eb',
        borderRadius: '8px',
        padding: '24px',
        zIndex: 1000,
        boxShadow: '0 4px 16px rgba(0,0,0,0.25)',
        maxWidth: '480px',
        width: '90%',
      }}
    >
      <h2 style={{ color: '#1d4ed8', marginTop: 0, fontSize: '1.1rem' }}>
        名簿外の出席番号からの回答
      </h2>
      <p style={{ margin: '8px 0' }}>
        出席番号 <strong>{extras.join(', ')}</strong>{' '}
        は生徒名簿に登録されていません。
      </p>
      <p style={{ margin: '8px 0', color: '#6b7280', fontSize: '0.9rem' }}>
        日程案に含めますか？
      </p>
      <div style={{ display: 'flex', gap: '8px', marginTop: '16px' }}>
        <button
          onClick={onInclude}
          style={{
            padding: '8px 20px',
            cursor: 'pointer',
            backgroundColor: '#2563eb',
            color: '#fff',
            border: 'none',
            borderRadius: '4px',
          }}
        >
          含める
        </button>
        <button
          onClick={onExclude}
          style={{
            padding: '8px 20px',
            cursor: 'pointer',
            backgroundColor: '#fff',
            color: '#374151',
            border: '1px solid #d1d5db',
            borderRadius: '4px',
          }}
        >
          除外する
        </button>
      </div>
    </div>
  )
}

// ===== 警告ダイアログ（エクスポート: テスト用）=====

export interface WarningDialogProps {
  studentNumber: number
  date: string
  start: string
  onClose: () => void
}

/** 候補日時外への移動警告ダイアログ */
export function WarningDialog({ studentNumber, date, start, onClose }: WarningDialogProps) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      data-testid="warning-dialog"
      style={{
        position: 'fixed',
        top: '50%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
        backgroundColor: '#fff',
        border: '2px solid #f59e0b',
        borderRadius: '8px',
        padding: '24px',
        zIndex: 1000,
        boxShadow: '0 4px 16px rgba(0,0,0,0.25)',
        maxWidth: '400px',
        width: '90%',
      }}
    >
      <h2 style={{ color: '#b45309', marginTop: 0, fontSize: '1.1rem' }}>
        ⚠ 候補日時外への移動
      </h2>
      <p style={{ margin: '8px 0' }}>
        出席番号 <strong>{studentNumber}</strong> の生徒は、
        <strong>
          {date} {start}
        </strong>{' '}
        を候補日時として回答していません。
      </p>
      <p style={{ margin: '8px 0', color: '#6b7280', fontSize: '0.9rem' }}>
        移動は許可されますが、この生徒の希望に沿わない可能性があります。
      </p>
      <button
        onClick={onClose}
        style={{
          marginTop: '12px',
          padding: '8px 20px',
          cursor: 'pointer',
          backgroundColor: '#f59e0b',
          color: '#fff',
          border: 'none',
          borderRadius: '4px',
        }}
      >
        閉じる
      </button>
    </div>
  )
}

// ===== 内部サブコンポーネント =====

interface AvailabilityIssueAlertProps {
  /** 現在の回答では候補日時が完全に無くなった生徒の出席番号 */
  noAvailability: number[]
  /** 現在の回答に配置スロットが含まれていない生徒の出席番号（noAvailability と別の場合のみ） */
  outOfCurrentAvailability: number[]
  /** 「警告対象を再配置する」ボタン押下時のコールバック */
  onReorganize: () => void
  /** ボタンを無効化するか（再スケジューリング実行中など）*/
  reorganizeDisabled?: boolean
}

/**
 * 既存ドラフトの配置を維持しているが、現在の回答との不整合がある場合に
 * 画面上部へ目立つ警告を表示する。
 *
 * 想定ケース:
 *  - Form 再送で候補日時が空 になった生徒の配置が残っている
 *  - Form 再送で配置スロットが候補から外された生徒の配置が残っている
 */
function AvailabilityIssueAlert({
  noAvailability,
  outOfCurrentAvailability,
  onReorganize,
  reorganizeDisabled,
}: AvailabilityIssueAlertProps) {
  if (noAvailability.length === 0 && outOfCurrentAvailability.length === 0) {
    return null
  }
  return (
    <div
      role="alert"
      data-testid="availability-issue-alert"
      style={{
        border: '1px solid #f59e0b',
        backgroundColor: '#fffbeb',
        borderRadius: '4px',
        padding: '12px 16px',
        marginBottom: '16px',
      }}
    >
      <h2 style={{ color: '#b45309', marginTop: 0, fontSize: '1rem' }}>
        ⚠ 候補日時に関する警告
      </h2>
      {noAvailability.length > 0 && (
        <p style={{ margin: '4px 0' }}>
          出席番号 <strong>{noAvailability.join(', ')}</strong>{' '}
          は最新の回答では候補日時がありません。既存ドラフトの配置を維持していますが、配置先を再検討してください。
        </p>
      )}
      {outOfCurrentAvailability.length > 0 && (
        <p style={{ margin: '4px 0' }}>
          出席番号 <strong>{outOfCurrentAvailability.join(', ')}</strong>{' '}
          の現在の配置先は、最新の回答の候補日時に含まれていません。
        </p>
      )}
      <button
        type="button"
        onClick={onReorganize}
        disabled={reorganizeDisabled}
        data-testid="reorganize-warning-students-button"
        style={{
          marginTop: '8px',
          padding: '6px 16px',
          cursor: reorganizeDisabled ? 'not-allowed' : 'pointer',
          backgroundColor: '#f59e0b',
          color: '#fff',
          border: 'none',
          borderRadius: '4px',
          opacity: reorganizeDisabled ? 0.6 : 1,
        }}
      >
        警告対象を再配置する
      </button>
    </div>
  )
}

interface ValidationAlertProps {
  duplicates: number[]
  outOfRoster: number[]
}

/**
 * 手動入力による配置の検証エラーを動的に表示する。
 * - 重複（同一出席番号が複数セル）
 * - 名簿外（roster にも authorizedExtras にも含まれない）
 */
function ValidationAlert({ duplicates, outOfRoster }: ValidationAlertProps) {
  if (duplicates.length === 0 && outOfRoster.length === 0) {
    return null
  }
  return (
    <div
      role="alert"
      data-testid="validation-alert"
      style={{
        border: '1px solid #ef4444',
        backgroundColor: '#fef2f2',
        borderRadius: '4px',
        padding: '12px 16px',
        marginBottom: '16px',
      }}
    >
      <h2 style={{ color: '#b91c1c', marginTop: 0, fontSize: '1rem' }}>
        ⚠ 配置の検証エラー
      </h2>
      {duplicates.length > 0 && (
        <p style={{ margin: '4px 0' }}>
          出席番号 <strong>{duplicates.join(', ')}</strong>{' '}
          が複数のセルに入力されています。重複を解消してください。
        </p>
      )}
      {outOfRoster.length > 0 && (
        <p style={{ margin: '4px 0' }}>
          出席番号 <strong>{outOfRoster.join(', ')}</strong>{' '}
          は生徒名簿に登録されていません。
        </p>
      )}
    </div>
  )
}

interface InfeasibleInfoProps {
  violatedConstraints: string[]
  unassignedStudents: number[]
}

function InfeasibleInfo({ violatedConstraints, unassignedStudents }: InfeasibleInfoProps) {
  if (violatedConstraints.length === 0 && unassignedStudents.length === 0) {
    return null
  }

  return (
    <div
      role="alert"
      style={{
        border: '1px solid #f87171',
        borderRadius: '4px',
        backgroundColor: '#fef2f2',
        padding: '16px',
        marginBottom: '16px',
      }}
    >
      {violatedConstraints.length > 0 && (
        <div>
          <h2 style={{ color: '#b91c1c', marginTop: 0 }}>違反している制約</h2>
          <ul>
            {violatedConstraints.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </div>
      )}
      {unassignedStudents.length > 0 && (
        <div>
          <h2 style={{ color: '#b91c1c', marginTop: 0 }}>未配置の生徒</h2>
          <p>出席番号: {unassignedStudents.join(', ')}</p>
        </div>
      )}
    </div>
  )
}

// --- DnD セルコンポーネント ---

interface DraggableStudentCardProps {
  /** セルID: "date|HH:MM" */
  id: string
  studentNumber: number
  outOfAvailability: boolean
}

function DraggableStudentCard({ id, studentNumber, outOfAvailability }: DraggableStudentCardProps) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id })

  return (
    <div
      ref={setNodeRef}
      {...listeners}
      {...attributes}
      data-testid={`draggable-student-${studentNumber}`}
      style={{
        cursor: isDragging ? 'grabbing' : 'grab',
        opacity: isDragging ? 0.4 : 1,
        transform:
          transform != null
            ? `translate3d(${transform.x}px, ${transform.y}px, 0)`
            : undefined,
        padding: '4px 6px',
        userSelect: 'none',
        display: 'inline-block',
      }}
    >
      {studentNumber}
      {outOfAvailability && (
        <span
          title="この生徒の候補日時外です"
          aria-label="候補外"
          style={{ marginLeft: '4px', color: '#b45309' }}
        >
          ⚠
        </span>
      )}
    </div>
  )
}

interface MatrixCellProps {
  /** セルID: "date|HH:MM" */
  id: string
  studentNumber?: number
  outOfAvailability: boolean
  /** 既存ドラフトに由来する配置か（true=元から存在、false=新規・更新） */
  isOriginal: boolean
  /** 既存ドラフト由来か否かの視覚区別を有効にするか（既存ドラフトが無い場合は false）*/
  showDistinction: boolean
  /** このセルが編集中（入力モード）か */
  isEditing: boolean
  /** このセルの内容が検証エラー対象か（重複 or 名簿外）*/
  hasIssue: boolean
  onStartEdit: (cellId: string) => void
  onCommit: (cellId: string, value: number | null) => void
  onCancelEdit: () => void
}

function MatrixCell({
  id,
  studentNumber,
  outOfAvailability,
  isOriginal,
  showDistinction,
  isEditing,
  hasIssue,
  onStartEdit,
  onCommit,
  onCancelEdit,
}: MatrixCellProps) {
  const { setNodeRef, isOver } = useDroppable({ id })

  // 背景色の優先度:
  //   ドロップオーバー > 候補外（警告）> 新規/更新（緑）> 既存ドラフト（灰）> なし
  let backgroundColor: string | undefined = undefined
  if (isOver) {
    backgroundColor = '#e0f2fe'
  } else if (studentNumber !== undefined && outOfAvailability) {
    backgroundColor = '#fef3c7'
  } else if (studentNumber !== undefined && showDistinction) {
    backgroundColor = isOriginal ? '#f3f4f6' : '#dcfce7'
  }

  const cellTestId =
    studentNumber !== undefined && showDistinction
      ? isOriginal
        ? `cell-original-${studentNumber}`
        : `cell-new-${studentNumber}`
      : undefined

  const cellBorder = hasIssue ? '2px solid #ef4444' : '1px solid #d1d5db'

  return (
    <td
      ref={setNodeRef}
      data-testid={cellTestId}
      style={{
        border: cellBorder,
        padding: '8px',
        textAlign: 'center',
        minWidth: '60px',
        backgroundColor,
        transition: 'background-color 0.1s ease',
      }}
    >
      {isEditing ? (
        <input
          type="number"
          min="1"
          autoFocus
          defaultValue={studentNumber ?? ''}
          data-testid={`cell-input-${id}`}
          aria-label={`セル ${id} の生徒番号`}
          onBlur={(e) => {
            const v = e.currentTarget.value.trim()
            onCommit(id, v === '' ? null : Number(v))
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.currentTarget.blur()
            } else if (e.key === 'Escape') {
              onCancelEdit()
            }
          }}
          style={{
            width: '52px',
            textAlign: 'center',
            padding: '2px 4px',
            fontSize: '0.9rem',
            border: '1px solid #2563eb',
            borderRadius: '2px',
          }}
        />
      ) : (
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '4px',
            justifyContent: 'center',
          }}
        >
          {studentNumber !== undefined && (
            <DraggableStudentCard
              id={id}
              studentNumber={studentNumber}
              outOfAvailability={outOfAvailability}
            />
          )}
          <button
            type="button"
            onClick={() => onStartEdit(id)}
            data-testid={`cell-edit-button-${id}`}
            aria-label={
              studentNumber !== undefined
                ? '出席番号を編集'
                : '出席番号を入力'
            }
            style={{
              padding: '2px 6px',
              fontSize: '0.8rem',
              cursor: 'pointer',
              backgroundColor: '#fff',
              color: '#6b7280',
              border: '1px solid #d1d5db',
              borderRadius: '2px',
              minWidth: '24px',
              lineHeight: 1,
            }}
          >
            {studentNumber !== undefined ? '✎' : '＋'}
          </button>
        </div>
      )}
    </td>
  )
}

// --- 候補日時マトリクス（読み取り専用、Form 回答の集計表示）---

interface AvailabilityMatrixProps {
  responses: ApiResponse[]
  project: Project | null
}

/**
 * 日付 × 時間枠 のマトリクスで、各セルに「その枠を可と回答した出席番号」を列挙する。
 * 配置編集の対象ではないため DnD ハンドラは持たない。
 */
function AvailabilityMatrix({ responses, project }: AvailabilityMatrixProps) {
  if (!project) {
    return null
  }
  const dates = [...project.candidate_dates].sort()
  const timeSlots = [...project.candidate_time_slots]
    .map((s) => ({ start: toHHMM(s.start), end: toHHMM(s.end) }))
    .sort((a, b) => a.start.localeCompare(b.start))

  // "date|HH:MM" → 出席番号の昇順リスト
  const cellMap = new Map<string, number[]>()
  for (const r of responses) {
    for (const av of r.availability) {
      const key = `${av.date}|${toHHMM(av.start)}`
      const arr = cellMap.get(key) ?? []
      if (!arr.includes(r.student_number)) {
        arr.push(r.student_number)
      }
      cellMap.set(key, arr)
    }
  }
  for (const arr of cellMap.values()) {
    arr.sort((a, b) => a - b)
  }

  const thStyle: React.CSSProperties = {
    border: '1px solid #d1d5db',
    padding: '8px',
    backgroundColor: '#f9fafb',
    textAlign: 'center',
    whiteSpace: 'nowrap',
  }
  const labelCellStyle: React.CSSProperties = thStyle
  const cellStyle: React.CSSProperties = {
    border: '1px solid #d1d5db',
    padding: '8px',
    textAlign: 'center',
    minWidth: '60px',
    verticalAlign: 'top',
  }

  return (
    <div style={{ overflowX: 'auto' }} data-testid="availability-matrix">
      <table style={{ borderCollapse: 'collapse', width: '100%' }}>
        <thead>
          <tr>
            <th style={thStyle}>時間枠</th>
            {dates.map((date) => (
              <th key={date} style={thStyle}>
                {date}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {timeSlots.map((slot) => (
            <tr key={slot.start}>
              <td style={labelCellStyle}>
                {slot.start} - {slot.end}
              </td>
              {dates.map((date) => {
                const key = `${date}|${slot.start}`
                const sns = cellMap.get(key) ?? []
                return (
                  <td key={date} style={cellStyle}>
                    {sns.length > 0 ? sns.join(', ') : ''}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// --- マトリクス表示 ---

interface ScheduleMatrixProps {
  assignments: Assignment[]
  project: Project | null
  outOfAvailCells: Set<string>
  /** "student|date|HH:MM" 形式の、既存ドラフト由来の配置キー集合 */
  originalDraftKeys: Set<string>
  /** 既存ドラフト由来か否かの視覚区別を行うか（既存ドラフトが無い初回作成時は false）*/
  showOriginalDistinction: boolean
  /** 編集中セルの ID（"date|HH:MM"）。null なら編集中なし */
  editingCellId: string | null
  /** "date|HH:MM" 形式の、検証エラー（重複/名簿外）対象セル集合 */
  issueCells: Set<string>
  onStartEdit: (cellId: string) => void
  onCommitEdit: (cellId: string, value: number | null) => void
  onCancelEdit: () => void
}

function ScheduleMatrix({
  assignments,
  project,
  outOfAvailCells,
  originalDraftKeys,
  showOriginalDistinction,
  editingCellId,
  issueCells,
  onStartEdit,
  onCommitEdit,
  onCancelEdit,
}: ScheduleMatrixProps) {
  // グリッド軸の構築: プロジェクト情報があればそちらを優先（空きセルも表示する）
  const dates: string[] = project
    ? [...project.candidate_dates].sort()
    : Array.from(new Set(assignments.map((a) => a.date))).sort()

  // backend は time フィールドを "HH:MM:SS" として JSON 化するため、
  // cellMap の key (toHHMM 正規化済み) と一致させるよう "HH:MM" に揃える。
  const timeSlots: Array<{ start: string; end: string }> = project
    ? [...project.candidate_time_slots]
        .map((s) => ({ start: toHHMM(s.start), end: toHHMM(s.end) }))
        .sort((a, b) => a.start.localeCompare(b.start))
    : Array.from(
        new Map(
          assignments.map((a) => [
            toHHMM(a.start),
            { start: toHHMM(a.start), end: toHHMM(a.end) },
          ]),
        ).values(),
      ).sort((a, b) => a.start.localeCompare(b.start))

  if (assignments.length === 0 && timeSlots.length === 0) {
    return <p>配置可能な面談がありません。</p>
  }

  // セルマップ構築: "date|HH:MM" → { studentNumber, endHHMM }
  const cellMap = new Map<string, { studentNumber: number; endHHMM: string }>()
  for (const a of assignments) {
    cellMap.set(`${a.date}|${toHHMM(a.start)}`, {
      studentNumber: a.student_number,
      endHHMM: toHHMM(a.end),
    })
  }

  const thStyle: React.CSSProperties = {
    border: '1px solid #d1d5db',
    padding: '8px',
    backgroundColor: '#f9fafb',
    textAlign: 'center',
    whiteSpace: 'nowrap',
  }

  const labelCellStyle: React.CSSProperties = {
    border: '1px solid #d1d5db',
    padding: '8px',
    backgroundColor: '#f9fafb',
    textAlign: 'center',
    whiteSpace: 'nowrap',
  }

  return (
    <div style={{ overflowX: 'auto' }}>
      {showOriginalDistinction && (
        <div
          data-testid="schedule-matrix-legend"
          style={{
            display: 'flex',
            gap: '16px',
            marginBottom: '8px',
            fontSize: '0.875rem',
            color: '#374151',
          }}
        >
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
            <span
              aria-hidden="true"
              style={{
                display: 'inline-block',
                width: '14px',
                height: '14px',
                backgroundColor: '#f3f4f6',
                border: '1px solid #d1d5db',
              }}
            />
            既存ドラフトの配置
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
            <span
              aria-hidden="true"
              style={{
                display: 'inline-block',
                width: '14px',
                height: '14px',
                backgroundColor: '#dcfce7',
                border: '1px solid #d1d5db',
              }}
            />
            新規 / 更新された配置
          </span>
        </div>
      )}
      <table style={{ borderCollapse: 'collapse', width: '100%' }}>
        <thead>
          <tr>
            <th style={thStyle}>時間枠</th>
            {dates.map((date) => (
              <th key={date} style={thStyle}>
                {date}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {timeSlots.map((slot) => (
            <tr key={slot.start}>
              <td style={labelCellStyle}>
                {slot.start} - {slot.end}
              </td>
              {dates.map((date) => {
                const cellKey = `${date}|${slot.start}`
                const cell = cellMap.get(cellKey)
                const isOriginal =
                  cell != null &&
                  originalDraftKeys.has(
                    `${cell.studentNumber}|${date}|${slot.start}`,
                  )
                return (
                  <MatrixCell
                    key={date}
                    id={cellKey}
                    studentNumber={cell?.studentNumber}
                    outOfAvailability={outOfAvailCells.has(cellKey)}
                    isOriginal={isOriginal}
                    showDistinction={showOriginalDistinction}
                    isEditing={editingCellId === cellKey}
                    hasIssue={issueCells.has(cellKey)}
                    onStartEdit={onStartEdit}
                    onCommit={onCommitEdit}
                    onCancelEdit={onCancelEdit}
                  />
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ===== メインコンポーネント =====

export default function SchedulePage() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()

  // スケジューリング結果（元データ）
  const [result, setResult] = useState<SchedulingResult | null>(null)
  // プロジェクト情報（空きセル表示のため）
  const [project, setProject] = useState<Project | null>(null)
  // 回答データ（候補日時外警告のため）
  const [responses, setResponses] = useState<ApiResponse[]>([])

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // 保存処理の state
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  // DnD 操作後に更新される割り当て（ミュータブル）
  const [localAssignments, setLocalAssignments] = useState<Assignment[]>([])
  // 候補外移動の警告ダイアログ情報
  const [warningInfo, setWarningInfo] = useState<{
    studentNumber: number
    date: string
    start: string
  } | null>(null)
  // 候補日時外に配置されているセルのキーセット（視覚的マーキング用）
  const [outOfAvailCells, setOutOfAvailCells] = useState<Set<string>>(new Set())

  // 名簿外の出席番号からの回答が見つかった場合、ユーザー確認を待つために
  // 出席番号リストを保持する。null = 確認不要 or 確認済み。
  const [pendingExtras, setPendingExtras] = useState<number[] | null>(null)

  // 既存ドラフト（あれば）。新規スケジューリングはこれにマージする。
  const [existingDraft, setExistingDraft] = useState<Draft | null>(null)

  // 既存ドラフト由来の配置キー "student|date|HH:MM" の集合。
  // DnD やリオーガナイズで配置が変わったらキーは外れる（=「新規/更新」扱い）。
  const [originalDraftKeys, setOriginalDraftKeys] = useState<Set<string>>(
    new Set(),
  )

  // 編集中のセル ID（"date|HH:MM"）。null なら編集中なし。
  const [editingCellId, setEditingCellId] = useState<string | null>(null)

  // 名簿外として「一度認可された」出席番号の集合。
  // - 既存ドラフトに含まれる名簿外 → 過去のセッションで認可済み扱い
  // - 名簿外確認ダイアログで「含める」を選んだ番号 → 今セッションで認可
  // これらは検証エラー（名簿外）から除外する。
  const [authorizedExtras, setAuthorizedExtras] = useState<Set<number>>(
    new Set(),
  )

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
  )

  // 既存ドラフト + 新規スケジュール対象の状態に応じてスケジューリングを実行する。
  // existingArg / draftStudentsArg を引数で受けるのは初回ロード時の useEffect から
  // 同期的に呼び出される（=state がまだ反映されていない）場合に対応するため。
  function runScheduleAndMerge(
    userExcluded: number[],
    respList: ApiResponse[],
    existingArg: Draft | null,
    draftStudentsArg: Set<number>,
  ) {
    if (!projectId) return

    // 既存ドラフトに含まれている出席番号 + ユーザーが「除外」を選んだ名簿外番号
    const toExclude = new Set<number>([...draftStudentsArg, ...userExcluded])
    const newToSchedule = respList.filter(
      (r) => !toExclude.has(r.student_number),
    )

    // 新規にスケジューリングすべき生徒がいなければ、API は呼ばずに既存ドラフトをそのまま表示
    if (newToSchedule.length === 0) {
      if (existingArg) {
        const stub: SchedulingResult = {
          assignments: existingArg.assignments,
          unassigned_students: existingArg.unassigned_students,
          violated_constraints: existingArg.violated_constraints,
        }
        setResult(stub)
        setLocalAssignments(stub.assignments)
      } else {
        const empty: SchedulingResult = {
          assignments: [],
          unassigned_students: [],
          violated_constraints: [],
        }
        setResult(empty)
        setLocalAssignments([])
      }
      setLoading(false)
      return
    }

    setLoading(true)
    setError(null)
    const excludedList = Array.from(toExclude)
    const promise =
      excludedList.length > 0
        ? scheduleApi.run(projectId, { excluded_students: excludedList })
        : scheduleApi.run(projectId)
    promise
      .then((scheduleResult) => {
        const merged = existingArg
          ? mergeWithExistingDraft(existingArg, scheduleResult)
          : scheduleResult
        setResult(merged)
        setLocalAssignments(merged.assignments)
        setLoading(false)
      })
      .catch((err: Error) => {
        setError(err.message ?? 'スケジューリングに失敗しました')
        setLoading(false)
      })
  }

  // 初回データ取得: project / responses / 既存ドラフト（あれば）を並列ロードし、
  // - 名簿外回答（既存ドラフトに含まれないもの）があれば確認ダイアログ
  // - そうでなければ即スケジューリング
  useEffect(() => {
    if (!projectId) return
    setLoading(true)
    setError(null)

    Promise.all([
      projectsApi.get(projectId),
      responsesApi.list(projectId),
      draftsApi
        .getLatest(projectId)
        .then((d) => d as Draft | null)
        .catch((err: Error & { status?: number }) => {
          if (err.status === 404) return null
          throw err
        }),
    ])
      .then(([proj, resps, draft]) => {
        setProject(proj)
        const respList = resps ?? []
        setResponses(respList)
        setExistingDraft(draft)
        setOriginalDraftKeys(
          new Set(
            draft
              ? draft.assignments.map(
                  (a) => `${a.student_number}|${a.date}|${toHHMM(a.start)}`,
                )
              : [],
          ),
        )

        const roster = new Set(proj.student_numbers)
        const draftStudents = new Set<number>(
          draft
            ? [
                ...draft.assignments.map((a) => a.student_number),
                ...draft.unassigned_students,
              ]
            : [],
        )
        // 既存ドラフトに含まれる名簿外番号は過去に認可済み扱い
        const initialAuthorized = new Set<number>()
        for (const sn of draftStudents) {
          if (!roster.has(sn)) initialAuthorized.add(sn)
        }
        setAuthorizedExtras(initialAuthorized)

        // 名簿外 かつ 既存ドラフトにも含まれていない生徒だけが確認対象
        const extras = Array.from(
          new Set(
            respList
              .map((r) => r.student_number)
              .filter((sn) => !roster.has(sn) && !draftStudents.has(sn)),
          ),
        ).sort((a, b) => a - b)

        if (extras.length === 0) {
          runScheduleAndMerge([], respList, draft, draftStudents)
        } else {
          setPendingExtras(extras)
          setLoading(false)
        }
      })
      .catch((err: Error) => {
        setError(err.message ?? 'データの取得に失敗しました')
        setLoading(false)
      })
    // runScheduleAndMerge は projectId のみに依存
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])

  // 警告対象（候補日時ゼロ・配置スロットが現在の候補外）の生徒のみを対象として
  // 再スケジューリングを実行する。それ以外の生徒の現在配置は固定し、
  // mergeWithExistingDraft で衝突したものは未配置に回す。
  function handleReorganizeWarningStudents(warningStudents: number[]) {
    if (!projectId || !result) return
    if (warningStudents.length === 0) return

    const warningSet = new Set(warningStudents)
    const fixed = localAssignments.filter(
      (a) => !warningSet.has(a.student_number),
    )

    // 警告対象以外は除外（=警告対象のみスケジューラに渡す）
    const excluded = Array.from(
      new Set(
        responses
          .map((r) => r.student_number)
          .filter((sn) => !warningSet.has(sn)),
      ),
    )

    const syntheticExisting: Draft = {
      project_id: projectId,
      saved_at: new Date().toISOString(),
      locked: false,
      assignments: fixed,
      unassigned_students: result.unassigned_students.filter(
        (sn) => !warningSet.has(sn),
      ),
      violated_constraints: [],
    }

    setLoading(true)
    setError(null)
    const promise =
      excluded.length > 0
        ? scheduleApi.run(projectId, { excluded_students: excluded })
        : scheduleApi.run(projectId)
    promise
      .then((scheduleResult) => {
        const merged = mergeWithExistingDraft(syntheticExisting, scheduleResult)
        setResult(merged)
        setLocalAssignments(merged.assignments)
        setLoading(false)
      })
      .catch((err: Error) => {
        setError(err.message ?? '再スケジューリングに失敗しました')
        setLoading(false)
      })
  }

  function handleStartEdit(cellId: string) {
    setEditingCellId(cellId)
  }

  function handleCancelEdit() {
    setEditingCellId(null)
  }

  // セルの編集を確定する。value=null は当該セルの配置を削除。
  function handleCommitEdit(cellId: string, value: number | null) {
    setEditingCellId(null)
    if (!project) return
    const [date, startHHMM] = cellId.split('|')

    setLocalAssignments((prev) => {
      const idx = prev.findIndex(
        (a) => a.date === date && toHHMM(a.start) === startHHMM,
      )
      if (value === null) {
        if (idx === -1) return prev
        return prev.filter((_, i) => i !== idx)
      }
      const slot = project.candidate_time_slots.find(
        (s) => toHHMM(s.start) === startHHMM,
      )
      const endHHMM = slot ? toHHMM(slot.end) : startHHMM
      const start = `${startHHMM}:00`
      const end = `${endHHMM}:00`
      if (idx === -1) {
        return [...prev, { student_number: value, date, start, end }]
      }
      return prev.map((a, i) =>
        i === idx ? { ...a, student_number: value } : a,
      )
    })
  }

  // pendingExtras 確認後にユーザーが選んだ除外リストでスケジュールを継続する
  function continueAfterConfirm(userExcluded: number[]) {
    const draftStudents = new Set<number>(
      existingDraft
        ? [
            ...existingDraft.assignments.map((a) => a.student_number),
            ...existingDraft.unassigned_students,
          ]
        : [],
    )
    runScheduleAndMerge(userExcluded, responses, existingDraft, draftStudents)
  }

  // 手動入力を含む現在の配置に対する検証エラー（重複・名簿外）
  const validationIssues = useMemo(
    () =>
      validateAssignments(
        localAssignments,
        project?.student_numbers ?? [],
        Array.from(authorizedExtras),
      ),
    [localAssignments, project, authorizedExtras],
  )

  // 検証エラーを含むセルの "date|HH:MM" 集合（セル枠の赤強調用）
  const issueCells = useMemo(() => {
    const dupes = new Set(validationIssues.duplicates)
    const outOf = new Set(validationIssues.outOfRoster)
    const set = new Set<string>()
    for (const a of localAssignments) {
      if (dupes.has(a.student_number) || outOf.has(a.student_number)) {
        set.add(`${a.date}|${toHHMM(a.start)}`)
      }
    }
    return set
  }, [localAssignments, validationIssues])

  // 割り当てまたは回答データが変化したとき、候補外セルを再計算
  useEffect(() => {
    const newSet = new Set<string>()
    for (const a of localAssignments) {
      const startHHMM = toHHMM(a.start)
      if (!isInAvailability(a.student_number, a.date, startHHMM, responses)) {
        newSet.add(`${a.date}|${startHHMM}`)
      }
    }
    setOutOfAvailCells(newSet)
  }, [localAssignments, responses])

  // DnD ドロップ時の処理
  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event
    if (!over || active.id === over.id) return

    const fromKey = active.id as string
    const toKey = over.id as string
    const [toDate, toStart] = toKey.split('|')

    // 移動した生徒を特定
    const [fromDate, fromStart] = fromKey.split('|')
    const movingAssignment = localAssignments.find(
      (a) => a.date === fromDate && toHHMM(a.start) === fromStart,
    )
    if (!movingAssignment) return

    const movedStudentNumber = movingAssignment.student_number

    // 割り当てを更新
    // project.candidate_time_slots の time は backend で "HH:MM:SS" 形式に
    // シリアライズされるため、applyDrop が比較する "HH:MM" 形式へ正規化する。
    const normalizedSlots = (project?.candidate_time_slots ?? []).map((s) => ({
      start: toHHMM(s.start),
      end: toHHMM(s.end),
    }))
    const newAssignments = applyDrop(
      localAssignments,
      fromKey,
      toKey,
      normalizedSlots,
    )
    setLocalAssignments(newAssignments)

    // 候補日時外への移動なら警告
    if (!isInAvailability(movedStudentNumber, toDate, toStart, responses)) {
      setWarningInfo({ studentNumber: movedStudentNumber, date: toDate, start: toStart })
    }
  }

  // ドラフト保存処理。
  // 既存ドラフトがロックされている (status=draft_saved) と 409 が返るため、
  // その場合は自動でアンロックして 1 回だけ再保存する。
  async function handleSave() {
    if (!projectId || !result) return
    setSaving(true)
    setSaveError(null)
    // 手動配置で unassigned_students に居た番号が配置済みになった場合は外す
    const placedSet = new Set(localAssignments.map((a) => a.student_number))
    const payload = {
      assignments: localAssignments,
      unassigned_students: result.unassigned_students.filter(
        (sn) => !placedSet.has(sn),
      ),
      violated_constraints: result.violated_constraints,
    }
    try {
      await draftsApi.save(projectId, payload)
      navigate(`/projects/${projectId}/saved`)
    } catch (err) {
      const e = err as Error & { status?: number }
      if (e.status === 409) {
        try {
          await draftsApi.unlock(projectId)
          await draftsApi.save(projectId, payload)
          navigate(`/projects/${projectId}/saved`)
        } catch (err2) {
          const e2 = err2 as Error
          setSaveError(e2.message ?? '保存に失敗しました')
        }
      } else {
        setSaveError(e.message ?? '保存に失敗しました')
      }
    } finally {
      setSaving(false)
    }
  }

  // ===== ローディング・エラー表示 =====

  // 名簿外確認ダイアログが表示中のときは、ローディング表示より優先する
  if (loading && pendingExtras == null) {
    return (
      <div style={{ padding: '16px' }}>
        <h1>日程案</h1>
        <p>スケジューリング実行中...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div style={{ padding: '16px' }}>
        <h1>日程案</h1>
        <div role="alert" style={{ color: '#b91c1c' }}>
          エラー: {error}
        </div>
      </div>
    )
  }

  return (
    <div style={{ padding: '16px' }}>
      <h1>日程案</h1>

      {/* 名簿外回答の確認ダイアログ */}
      {pendingExtras != null && pendingExtras.length > 0 && (
        <ExtraStudentsConfirmDialog
          extras={pendingExtras}
          onInclude={() => {
            const toAuthorize = pendingExtras ?? []
            setPendingExtras(null)
            setAuthorizedExtras(
              (prev) => new Set([...prev, ...toAuthorize]),
            )
            continueAfterConfirm([])
          }}
          onExclude={() => {
            const toExclude = pendingExtras
            setPendingExtras(null)
            continueAfterConfirm(toExclude)
          }}
        />
      )}

      {/* 候補日時外移動の警告ダイアログ */}
      {warningInfo != null && (
        <WarningDialog
          studentNumber={warningInfo.studentNumber}
          date={warningInfo.date}
          start={warningInfo.start}
          onClose={() => setWarningInfo(null)}
        />
      )}

      {/* 既存ドラフトと現在の回答の不整合警告（画面上部）*/}
      {result != null &&
        (() => {
          // 現在の回答が「空」=候補日時ゼロ の生徒で、ドラフトに配置が残っているもの
          const placedStudents = new Set(
            localAssignments.map((a) => a.student_number),
          )
          const noAvail = responses
            .filter(
              (r) =>
                placedStudents.has(r.student_number) &&
                r.availability.length === 0,
            )
            .map((r) => r.student_number)
          const noAvailSet = new Set(noAvail)

          // 配置スロットが現在の回答に含まれない生徒（候補ゼロは別枠で出すため除外）
          const outOfCurrent: number[] = []
          for (const a of localAssignments) {
            if (noAvailSet.has(a.student_number)) continue
            const startHHMM = toHHMM(a.start)
            if (
              !isInAvailability(a.student_number, a.date, startHHMM, responses)
            ) {
              outOfCurrent.push(a.student_number)
            }
          }
          const dedupedNoAvail = Array.from(new Set(noAvail)).sort(
            (a, b) => a - b,
          )
          const dedupedOutOfCurrent = Array.from(new Set(outOfCurrent)).sort(
            (a, b) => a - b,
          )
          return (
            <AvailabilityIssueAlert
              noAvailability={dedupedNoAvail}
              outOfCurrentAvailability={dedupedOutOfCurrent}
              reorganizeDisabled={loading}
              onReorganize={() =>
                handleReorganizeWarningStudents([
                  ...dedupedNoAvail,
                  ...dedupedOutOfCurrent,
                ])
              }
            />
          )
        })()}

      {/* 解なし・警告情報（画面上部） */}
      {result != null && (
        <InfeasibleInfo
          violatedConstraints={result.violated_constraints}
          unassignedStudents={result.unassigned_students}
        />
      )}

      {/* 手動入力の検証エラー（重複・名簿外）*/}
      {result != null && (
        <ValidationAlert
          duplicates={validationIssues.duplicates}
          outOfRoster={validationIssues.outOfRoster}
        />
      )}

      {/* 日付×時間枠マトリクス（DnD コンテキスト内） */}
      {result != null && (
        <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
          <ScheduleMatrix
            assignments={localAssignments}
            project={project}
            outOfAvailCells={outOfAvailCells}
            originalDraftKeys={originalDraftKeys}
            showOriginalDistinction={originalDraftKeys.size > 0}
            editingCellId={editingCellId}
            issueCells={issueCells}
            onStartEdit={handleStartEdit}
            onCommitEdit={handleCommitEdit}
            onCancelEdit={handleCancelEdit}
          />
        </DndContext>
      )}

      {/* Google Form 回答集計マトリクス（参考表示・読み取り専用）*/}
      {result != null && project != null && (
        <section style={{ marginTop: '24px' }}>
          <h2 style={{ fontSize: '1.1rem' }}>候補日時の回答集計</h2>
          <p style={{ fontSize: '0.875rem', color: '#6b7280', marginTop: 0 }}>
            各枠を「可」と回答した出席番号を列挙しています。
          </p>
          <AvailabilityMatrix responses={responses} project={project} />
        </section>
      )}

      {/* 保存ボタン・保存エラー表示 */}
      {result != null && (
        <div style={{ marginTop: '16px' }}>
          {saveError != null && (
            <div
              role="alert"
              style={{
                color: '#b91c1c',
                backgroundColor: '#fef2f2',
                border: '1px solid #f87171',
                borderRadius: '4px',
                padding: '8px 12px',
                marginBottom: '8px',
              }}
            >
              {saveError}
            </div>
          )}
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              onClick={handleSave}
              disabled={saving}
              style={{
                padding: '10px 24px',
                fontSize: '1rem',
                cursor: saving ? 'not-allowed' : 'pointer',
                backgroundColor: '#2563eb',
                color: '#fff',
                border: 'none',
                borderRadius: '4px',
                opacity: saving ? 0.6 : 1,
              }}
            >
              {saving ? '保存中...' : '保存'}
            </button>
            <button
              type="button"
              onClick={() => navigate(`/projects/${projectId}`)}
              style={{
                padding: '10px 24px',
                fontSize: '1rem',
                cursor: 'pointer',
                backgroundColor: '#fff',
                color: '#374151',
                border: '1px solid #d1d5db',
                borderRadius: '4px',
              }}
            >
              プロジェクトへ戻る
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
