/**
 * 日程案表示画面
 * requirements.md §4.7
 *
 * Phase 4.4a: 日付×時間枠マトリクス表示 + 解なし情報表示（read-only）
 * Phase 4.4b: ドラッグ&ドロップ（dnd-kit）+ 候補日時外移動の警告
 * Phase 4.4c: 保存ボタン（次フェーズ）
 */

import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import {
  DndContext,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
import type { DragEndEvent } from '@dnd-kit/core'
import { scheduleApi, projectsApi, responsesApi } from '../api'
import type {
  SchedulingResult,
  Assignment,
  Project,
  Response as ApiResponse,
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
 * 指定の生徒が指定のスロットを候補日時として回答しているか判定する。
 * responses が空または該当生徒のデータなし → true（候補内扱い）
 */
export function isInAvailability(
  studentNumber: number,
  date: string,
  startHHMM: string,
  responses: ApiResponse[],
): boolean {
  const studentResponse = responses.find((r) => r.student_number === studentNumber)
  if (!studentResponse) return true
  return studentResponse.availability.some(
    (av) => av.date === date && av.start === startHHMM,
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
}

function MatrixCell({ id, studentNumber, outOfAvailability }: MatrixCellProps) {
  const { setNodeRef, isOver } = useDroppable({ id })

  return (
    <td
      ref={setNodeRef}
      style={{
        border: '1px solid #d1d5db',
        padding: '8px',
        textAlign: 'center',
        minWidth: '60px',
        backgroundColor: isOver
          ? '#e0f2fe'
          : outOfAvailability
            ? '#fef3c7'
            : undefined,
        transition: 'background-color 0.1s ease',
      }}
    >
      {studentNumber !== undefined && (
        <DraggableStudentCard
          id={id}
          studentNumber={studentNumber}
          outOfAvailability={outOfAvailability}
        />
      )}
    </td>
  )
}

// --- マトリクス表示 ---

interface ScheduleMatrixProps {
  assignments: Assignment[]
  project: Project | null
  outOfAvailCells: Set<string>
}

function ScheduleMatrix({ assignments, project, outOfAvailCells }: ScheduleMatrixProps) {
  // グリッド軸の構築: プロジェクト情報があればそちらを優先（空きセルも表示する）
  const dates: string[] = project
    ? [...project.candidate_dates].sort()
    : Array.from(new Set(assignments.map((a) => a.date))).sort()

  const timeSlots: Array<{ start: string; end: string }> = project
    ? [...project.candidate_time_slots].sort((a, b) => a.start.localeCompare(b.start))
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
                return (
                  <MatrixCell
                    key={date}
                    id={cellKey}
                    studentNumber={cell?.studentNumber}
                    outOfAvailability={outOfAvailCells.has(cellKey)}
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

  // スケジューリング結果（元データ）
  const [result, setResult] = useState<SchedulingResult | null>(null)
  // プロジェクト情報（空きセル表示のため）
  const [project, setProject] = useState<Project | null>(null)
  // 回答データ（候補日時外警告のため）
  const [responses, setResponses] = useState<ApiResponse[]>([])

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

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

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
  )

  // 初回データ取得: スケジューリング実行 + プロジェクト情報 + 回答データ
  useEffect(() => {
    if (!projectId) return
    setLoading(true)
    setError(null)

    Promise.all([
      scheduleApi.run(projectId),
      projectsApi.get(projectId),
      responsesApi.list(projectId),
    ])
      .then(([scheduleResult, proj, resps]) => {
        setResult(scheduleResult)
        setLocalAssignments(scheduleResult.assignments)
        setProject(proj)
        setResponses(resps ?? [])
        setLoading(false)
      })
      .catch((err: Error) => {
        setError(err.message ?? 'データの取得に失敗しました')
        setLoading(false)
      })
  }, [projectId])

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
    const newAssignments = applyDrop(
      localAssignments,
      fromKey,
      toKey,
      project?.candidate_time_slots ?? [],
    )
    setLocalAssignments(newAssignments)

    // 候補日時外への移動なら警告
    if (!isInAvailability(movedStudentNumber, toDate, toStart, responses)) {
      setWarningInfo({ studentNumber: movedStudentNumber, date: toDate, start: toStart })
    }
  }

  // ===== ローディング・エラー表示 =====

  if (loading) {
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

      {/* 候補日時外移動の警告ダイアログ */}
      {warningInfo != null && (
        <WarningDialog
          studentNumber={warningInfo.studentNumber}
          date={warningInfo.date}
          start={warningInfo.start}
          onClose={() => setWarningInfo(null)}
        />
      )}

      {/* 解なし・警告情報（画面上部） */}
      {result != null && (
        <InfeasibleInfo
          violatedConstraints={result.violated_constraints}
          unassignedStudents={result.unassigned_students}
        />
      )}

      {/* 日付×時間枠マトリクス（DnD コンテキスト内） */}
      {result != null && (
        <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
          <ScheduleMatrix
            assignments={localAssignments}
            project={project}
            outOfAvailCells={outOfAvailCells}
          />
        </DndContext>
      )}
    </div>
  )
}
