/**
 * プロジェクト新規作成画面
 * requirements.md §4.2, §4.3
 * - display_name（必須）
 * - slot_minutes
 * - candidate_dates（候補日、1行1日 YYYY-MM-DD 形式）
 * - candidate_time_slots（候補時間枠、開始/終了ペア）
 * - student_numbers（出席番号リスト、カンマ区切り）
 */

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import type { FormEvent } from 'react'
import { projectsApi } from '../api'

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
  const [slotMinutes, setSlotMinutes] = useState(20)
  const [candidateDatesText, setCandidateDatesText] = useState('')
  const [startTime, setStartTime] = useState('16:00')
  const [endTime, setEndTime] = useState('16:20')
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

    const dates = candidateDatesText
      .split('\n')
      .map((d) => d.trim())
      .filter(Boolean)

    if (dates.length === 0) {
      setValidationError('候補日を1行以上入力してください（例: 2026-07-15）')
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
          <label htmlFor="candidate-dates">
            候補日（1行1日、YYYY-MM-DD形式）
          </label>
          <br />
          <textarea
            id="candidate-dates"
            value={candidateDatesText}
            onChange={(e) => setCandidateDatesText(e.target.value)}
            placeholder={'2026-07-15\n2026-07-16'}
            rows={4}
            style={{ width: '100%', maxWidth: '400px' }}
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
