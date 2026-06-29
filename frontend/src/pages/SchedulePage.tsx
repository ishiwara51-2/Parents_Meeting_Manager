/**
 * 日程案表示画面
 * requirements.md §4.7
 *
 * Phase 4.4a: 日付×時間枠マトリクス表示 + 解なし情報表示（read-only）
 * Phase 4.4b: ドラッグ&ドロップ（次フェーズ）
 * Phase 4.4c: 保存ボタン（次フェーズ）
 */

import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { scheduleApi } from '../api'
import type { SchedulingResult, Assignment } from '../api/types'

// "HH:MM:SS" → "HH:MM" に変換するユーティリティ（バックエンドは秒付きで返す）
function toHHMM(timeStr: string): string {
  return timeStr.slice(0, 5)
}

// assignments から日付×時間枠マトリクスを構築する
function buildMatrix(assignments: Assignment[]) {
  const datesSet = new Set<string>()
  const startTimesSet = new Set<string>()

  for (const a of assignments) {
    datesSet.add(a.date)
    startTimesSet.add(a.start)
  }

  // 日付・時間枠をソート（アルファベット順 = 時刻・日付順）
  const dates = Array.from(datesSet).sort()
  const startTimes = Array.from(startTimesSet).sort()

  // (date, start) → {student_number, end} のマッピング
  const cellMap = new Map<string, { studentNumber: number; end: string }>()
  for (const a of assignments) {
    cellMap.set(`${a.date}|${a.start}`, {
      studentNumber: a.student_number,
      end: a.end,
    })
  }

  return { dates, startTimes, cellMap }
}

// ===== サブコンポーネント =====

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

interface ScheduleMatrixProps {
  assignments: Assignment[]
}

function ScheduleMatrix({ assignments }: ScheduleMatrixProps) {
  if (assignments.length === 0) {
    return <p>配置可能な面談がありません。</p>
  }

  const { dates, startTimes, cellMap } = buildMatrix(assignments)

  return (
    <div style={{ overflowX: 'auto' }}>
      <table
        style={{
          borderCollapse: 'collapse',
          width: '100%',
        }}
      >
        <thead>
          <tr>
            <th
              style={{
                border: '1px solid #d1d5db',
                padding: '8px',
                backgroundColor: '#f9fafb',
                textAlign: 'center',
                whiteSpace: 'nowrap',
              }}
            >
              時間枠
            </th>
            {dates.map((date) => (
              <th
                key={date}
                style={{
                  border: '1px solid #d1d5db',
                  padding: '8px',
                  backgroundColor: '#f9fafb',
                  textAlign: 'center',
                  whiteSpace: 'nowrap',
                }}
              >
                {date}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {startTimes.map((startTime) => {
            // この startTime の end を任意の日付から取得（全日共通）
            let endTime = ''
            for (const date of dates) {
              const cell = cellMap.get(`${date}|${startTime}`)
              if (cell) {
                endTime = cell.end
                break
              }
            }

            return (
              <tr key={startTime}>
                <td
                  style={{
                    border: '1px solid #d1d5db',
                    padding: '8px',
                    backgroundColor: '#f9fafb',
                    textAlign: 'center',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {toHHMM(startTime)}
                  {endTime ? ` - ${toHHMM(endTime)}` : ''}
                </td>
                {dates.map((date) => {
                  const cell = cellMap.get(`${date}|${startTime}`)
                  return (
                    <td
                      key={date}
                      style={{
                        border: '1px solid #d1d5db',
                        padding: '8px',
                        textAlign: 'center',
                        minWidth: '60px',
                      }}
                    >
                      {cell !== undefined ? cell.studentNumber : ''}
                    </td>
                  )
                })}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ===== メインコンポーネント =====

export default function SchedulePage() {
  const { projectId } = useParams<{ projectId: string }>()
  const [result, setResult] = useState<SchedulingResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!projectId) return
    setLoading(true)
    setError(null)

    scheduleApi
      .run(projectId)
      .then((res) => {
        setResult(res)
        setLoading(false)
      })
      .catch((err: Error) => {
        setError(err.message ?? 'スケジューリングに失敗しました')
        setLoading(false)
      })
  }, [projectId])

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

      {/* 解なし・警告情報（画面上部） */}
      {result && (
        <InfeasibleInfo
          violatedConstraints={result.violated_constraints}
          unassignedStudents={result.unassigned_students}
        />
      )}

      {/* 日付×時間枠マトリクス */}
      {result && <ScheduleMatrix assignments={result.assignments} />}
    </div>
  )
}
