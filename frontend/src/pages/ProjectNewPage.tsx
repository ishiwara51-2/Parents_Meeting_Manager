/**
 * プロジェクト新規作成画面
 * requirements.md §4.2, §4.3
 * - display_name（必須）
 * - slot_minutes
 * - candidate_dates（候補日、カレンダー UI で複数選択）
 * - candidate_time_slots（候補時間枠、開始/終了ペア）
 * - student_numbers（出席番号リスト、カンマ区切り）
 */

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import type { FormEvent } from 'react'
import { projectsApi } from '../api'

/** "YYYY-MM-DD" 形式に整形 */
function formatYMD(year: number, month0: number, day: number): string {
  return `${year}-${String(month0 + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`
}

interface CandidateDatesCalendarProps {
  value: string[] // "YYYY-MM-DD"[]
  onChange: (next: string[]) => void
}

/**
 * 候補日を複数選択できるカレンダー UI。
 * クリックで日付をトグル選択。月送りボタンで前後の月へ移動可能。
 * 選択済みの日付は下部にチップ表示し、× で個別解除できる。
 */
function CandidateDatesCalendar({ value, onChange }: CandidateDatesCalendarProps) {
  const today = new Date()
  const [viewYear, setViewYear] = useState(today.getFullYear())
  const [viewMonth, setViewMonth] = useState(today.getMonth()) // 0-11

  const selectedSet = new Set(value)

  const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate()
  const firstWeekday = new Date(viewYear, viewMonth, 1).getDay() // 0=Sun..6=Sat
  const todayStr = formatYMD(
    today.getFullYear(),
    today.getMonth(),
    today.getDate(),
  )

  function gotoPrevMonth() {
    if (viewMonth === 0) {
      setViewYear(viewYear - 1)
      setViewMonth(11)
    } else {
      setViewMonth(viewMonth - 1)
    }
  }
  function gotoNextMonth() {
    if (viewMonth === 11) {
      setViewYear(viewYear + 1)
      setViewMonth(0)
    } else {
      setViewMonth(viewMonth + 1)
    }
  }

  function toggleDate(dateStr: string) {
    if (selectedSet.has(dateStr)) {
      onChange(value.filter((d) => d !== dateStr))
    } else {
      onChange([...value, dateStr].sort())
    }
  }

  // 6 行 × 7 列のグリッドを構築
  const cells: Array<{ day: number; dateStr: string } | null> = []
  for (let i = 0; i < firstWeekday; i++) cells.push(null)
  for (let d = 1; d <= daysInMonth; d++) {
    cells.push({ day: d, dateStr: formatYMD(viewYear, viewMonth, d) })
  }
  while (cells.length % 7 !== 0) cells.push(null)
  const weeks: Array<Array<{ day: number; dateStr: string } | null>> = []
  for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7))

  const dayLabels = ['日', '月', '火', '水', '木', '金', '土']
  const cellBase: React.CSSProperties = {
    border: '1px solid #e5e7eb',
    padding: 0,
    textAlign: 'center',
    width: '40px',
    height: '36px',
  }

  return (
    <div data-testid="candidate-dates-calendar">
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
          marginBottom: '0.5rem',
        }}
      >
        <button
          type="button"
          onClick={gotoPrevMonth}
          aria-label="前の月"
          data-testid="calendar-prev-month"
        >
          ◀
        </button>
        <span style={{ minWidth: '7em', textAlign: 'center' }}>
          {viewYear}年 {viewMonth + 1}月
        </span>
        <button
          type="button"
          onClick={gotoNextMonth}
          aria-label="次の月"
          data-testid="calendar-next-month"
        >
          ▶
        </button>
      </div>
      <table
        style={{ borderCollapse: 'collapse' }}
        aria-label={`${viewYear}年${viewMonth + 1}月のカレンダー`}
      >
        <thead>
          <tr>
            {dayLabels.map((d, i) => (
              <th
                key={d}
                style={{
                  ...cellBase,
                  backgroundColor: '#f9fafb',
                  color: i === 0 ? '#dc2626' : i === 6 ? '#2563eb' : '#374151',
                  fontWeight: 'normal',
                  fontSize: '0.875rem',
                }}
              >
                {d}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {weeks.map((week, wi) => (
            <tr key={wi}>
              {week.map((cell, ci) => {
                if (cell == null) {
                  return <td key={ci} style={cellBase} />
                }
                const isSelected = selectedSet.has(cell.dateStr)
                const isToday = cell.dateStr === todayStr
                return (
                  <td key={ci} style={cellBase}>
                    <button
                      type="button"
                      onClick={() => toggleDate(cell.dateStr)}
                      data-testid={`calendar-day-${cell.dateStr}`}
                      aria-label={`${cell.dateStr}${isSelected ? '（選択中）' : ''}`}
                      aria-pressed={isSelected}
                      style={{
                        width: '100%',
                        height: '100%',
                        cursor: 'pointer',
                        border: isToday ? '1px solid #2563eb' : 'none',
                        backgroundColor: isSelected ? '#2563eb' : 'transparent',
                        color: isSelected
                          ? '#fff'
                          : ci === 0
                            ? '#dc2626'
                            : ci === 6
                              ? '#2563eb'
                              : '#111827',
                        fontWeight: isSelected ? 'bold' : 'normal',
                        fontSize: '0.875rem',
                      }}
                    >
                      {cell.day}
                    </button>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>

      {/* 選択済みリスト */}
      <div style={{ marginTop: '0.5rem' }}>
        {value.length === 0 ? (
          <p
            style={{ fontSize: '0.875rem', color: '#6b7280', margin: '0.25rem 0' }}
          >
            まだ候補日が選択されていません。カレンダーから日付をクリックして選択してください。
          </p>
        ) : (
          <div
            data-testid="selected-dates-list"
            style={{ display: 'flex', flexWrap: 'wrap', gap: '0.25rem' }}
          >
            {value.map((d) => (
              <span
                key={d}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.25rem',
                  padding: '0.15rem 0.5rem',
                  backgroundColor: '#e0f2fe',
                  border: '1px solid #bae6fd',
                  borderRadius: '999px',
                  fontSize: '0.85rem',
                }}
              >
                {d}
                <button
                  type="button"
                  onClick={() => toggleDate(d)}
                  aria-label={`${d} を解除`}
                  data-testid={`selected-date-remove-${d}`}
                  style={{
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    color: '#0369a1',
                    fontSize: '1rem',
                    lineHeight: 1,
                    padding: 0,
                  }}
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

/** "HH:MM" → 0時からの分数。形式不正なら null */
function parseHHMM(s: string): number | null {
  const m = /^(\d{1,2}):(\d{2})$/.exec(s)
  if (!m) return null
  const h = Number(m[1])
  const min = Number(m[2])
  if (h < 0 || h > 23 || min < 0 || min > 59) return null
  return h * 60 + min
}

/** 分数 → "HH:MM" */
function formatHHMM(totalMin: number): string {
  const h = Math.floor(totalMin / 60)
  const m = totalMin % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}

/**
 * 開始〜終了の範囲を slotMinutes 刻みでスライスし、
 * バックエンドが期待する個別 TimeSlot 配列を生成する。
 *
 * - end <= start の場合は空配列
 * - (end - start) が slotMinutes で割り切れない場合、末尾の半端は切り捨て
 *   （例: 16:00-17:10, slot=20 → 16:00-16:20, 16:20-16:40, 16:40-17:00）
 */
function sliceTimeRange(
  start: string,
  end: string,
  slotMinutes: number,
): { start: string; end: string }[] {
  const s = parseHHMM(start)
  const e = parseHHMM(end)
  if (s === null || e === null || slotMinutes <= 0 || e <= s) return []
  const slots: { start: string; end: string }[] = []
  for (let t = s; t + slotMinutes <= e; t += slotMinutes) {
    slots.push({ start: formatHHMM(t), end: formatHHMM(t + slotMinutes) })
  }
  return slots
}

export default function ProjectNewPage() {
  const navigate = useNavigate()

  const [displayName, setDisplayName] = useState('')
  const [slotMinutes, setSlotMinutes] = useState(60)
  const [candidateDates, setCandidateDates] = useState<string[]>([])
  const [startTime, setStartTime] = useState('16:00')
  const [endTime, setEndTime] = useState('17:00')
  const [studentNumbersText, setStudentNumbersText] = useState('')
  const [validationError, setValidationError] = useState('')

  const mutation = useMutation({
    mutationFn: projectsApi.create,
    onSuccess: (project) => {
      navigate(`/projects/${project.project_id}`)
    },
    onError: (err: Error) => {
      setValidationError(err.message ?? '作成に失敗しました')
    },
  })

  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setValidationError('')

    // バリデーション
    if (!displayName.trim()) {
      setValidationError('プロジェクト名を入力してください')
      return
    }

    const dates = [...candidateDates].sort()

    if (dates.length === 0) {
      setValidationError('候補日をカレンダーから1日以上選択してください')
      return
    }

    const studentNumbers = studentNumbersText
      .split(/[\n,]/)
      .map((s) => s.trim())
      .filter(Boolean)
      .map(Number)
      .filter((n) => !isNaN(n) && n > 0)

    const timeSlots = sliceTimeRange(startTime, endTime, slotMinutes)
    if (timeSlots.length === 0) {
      setValidationError(
        `時間枠が生成できません。終了時刻が開始時刻より後で、(終了 - 開始) が ${slotMinutes} 分以上必要です`,
      )
      return
    }

    mutation.mutate({
      display_name: displayName.trim(),
      slot_minutes: slotMinutes,
      candidate_dates: dates,
      candidate_time_slots: timeSlots,
      student_numbers: studentNumbers,
    })
  }

  return (
    <div className="container">
      <h1>新規プロジェクト作成</h1>

      <form onSubmit={handleSubmit}>
        {/* バリデーション・APIエラー */}
        {(validationError || mutation.error) && (
          <p role="alert" style={{ color: 'red' }}>
            {validationError || (mutation.error as Error)?.message}
          </p>
        )}

        {/* プロジェクト名 */}
        <div style={{ marginBottom: '1rem' }}>
          <label htmlFor="display-name">
            プロジェクト名
            <span style={{ color: 'red' }}> *</span>
          </label>
          <br />
          <input
            id="display-name"
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder="例: 3年A組 7月面談"
            style={{ width: '100%', maxWidth: '400px' }}
          />
        </div>

        {/* 1コマの長さ */}
        <div style={{ marginBottom: '1rem' }}>
          <label htmlFor="slot-minutes">1コマの長さ（分）</label>
          <br />
          <input
            id="slot-minutes"
            type="number"
            value={slotMinutes}
            onChange={(e) => setSlotMinutes(Number(e.target.value))}
            min={5}
            max={120}
            step={5}
            style={{ width: '100px' }}
          />
        </div>

        {/* 候補日 */}
        <div style={{ marginBottom: '1rem' }}>
          <div id="candidate-dates-label" style={{ marginBottom: '0.25rem' }}>
            候補日
          </div>
          <CandidateDatesCalendar
            value={candidateDates}
            onChange={setCandidateDates}
          />
        </div>

        {/* 候補時間枠（開始〜終了の範囲を 1コマ分ずつスライス）*/}
        <div style={{ marginBottom: '1rem' }}>
          <span>
            候補時間枠（開始〜終了の範囲を「1コマの長さ」ごとに分割します）
          </span>
          <br />
          <label htmlFor="start-time">開始</label>
          <input
            id="start-time"
            type="time"
            value={startTime}
            onChange={(e) => setStartTime(e.target.value)}
            style={{ marginLeft: '0.25rem', marginRight: '0.5rem' }}
          />
          <label htmlFor="end-time">終了</label>
          <input
            id="end-time"
            type="time"
            value={endTime}
            onChange={(e) => setEndTime(e.target.value)}
            style={{ marginLeft: '0.25rem' }}
          />
          {(() => {
            const preview = sliceTimeRange(startTime, endTime, slotMinutes)
            if (preview.length === 0) {
              return (
                <p style={{ fontSize: '0.875rem', color: '#a00', marginTop: '0.25rem' }}>
                  ※ 現在の入力では時間枠が生成されません
                </p>
              )
            }
            const labels = preview.map((s) => `${s.start}-${s.end}`)
            const shown = labels.slice(0, 3).join(', ')
            const more = labels.length > 3 ? ` ... 他 ${labels.length - 3} 枠` : ''
            return (
              <p style={{ fontSize: '0.875rem', color: '#555', marginTop: '0.25rem' }}>
                生成される枠（{labels.length} コマ）: {shown}{more}
              </p>
            )
          })()}
        </div>

        {/* 出席番号 */}
        <div style={{ marginBottom: '1.5rem' }}>
          <label htmlFor="student-numbers">
            出席番号（カンマ区切りまたは1行1番号）
          </label>
          <br />
          <textarea
            id="student-numbers"
            value={studentNumbersText}
            onChange={(e) => setStudentNumbersText(e.target.value)}
            placeholder={'1, 2, 3, ...\nまたは1行1番号'}
            rows={4}
            style={{ width: '100%', maxWidth: '400px' }}
          />
        </div>

        {/* ボタン */}
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? '作成中...' : '作成'}
          </button>
          <button type="button" onClick={() => navigate('/')}>
            キャンセル
          </button>
        </div>
      </form>
    </div>
  )
}
