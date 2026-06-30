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
import {
  Alert,
  AppShell,
  Button,
  Card,
  CardHeader,
  FormField,
  Input,
  Textarea,
} from '../components/ui'
import { cn } from '../components/ui/cn'

/** "YYYY-MM-DD" 形式に整形 */
function formatYMD(year: number, month0: number, day: number): string {
  return `${year}-${String(month0 + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`
}

interface CandidateDatesCalendarProps {
  value: string[]
  onChange: (next: string[]) => void
  /** 過去日を選択不可にするか（既定: true） */
  disablePast?: boolean
}

function CandidateDatesCalendar({
  value,
  onChange,
  disablePast = true,
}: CandidateDatesCalendarProps) {
  const today = new Date()
  const [viewYear, setViewYear] = useState(today.getFullYear())
  const [viewMonth, setViewMonth] = useState(today.getMonth())

  const selectedSet = new Set(value)
  const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate()
  const firstWeekday = new Date(viewYear, viewMonth, 1).getDay()
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

  const cells: Array<{ day: number; dateStr: string } | null> = []
  for (let i = 0; i < firstWeekday; i++) cells.push(null)
  for (let d = 1; d <= daysInMonth; d++) {
    cells.push({ day: d, dateStr: formatYMD(viewYear, viewMonth, d) })
  }
  while (cells.length % 7 !== 0) cells.push(null)
  const weeks: Array<Array<{ day: number; dateStr: string } | null>> = []
  for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7))

  const dayLabels = ['日', '月', '火', '水', '木', '金', '土']

  return (
    <div
      data-testid="candidate-dates-calendar"
      className="inline-block rounded-md border border-border bg-surface p-3"
    >
      <div className="flex items-center justify-between gap-2 mb-3">
        <button
          type="button"
          onClick={gotoPrevMonth}
          aria-label="前の月"
          data-testid="calendar-prev-month"
          className="h-8 w-8 rounded-md text-fg-muted hover:bg-surface-sunken hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
        >
          ◀
        </button>
        <span className="text-sm font-semibold text-fg min-w-[7em] text-center">
          {viewYear}年 {viewMonth + 1}月
        </span>
        <button
          type="button"
          onClick={gotoNextMonth}
          aria-label="次の月"
          data-testid="calendar-next-month"
          className="h-8 w-8 rounded-md text-fg-muted hover:bg-surface-sunken hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
        >
          ▶
        </button>
      </div>
      <table
        className="border-collapse"
        aria-label={`${viewYear}年${viewMonth + 1}月のカレンダー`}
      >
        <thead>
          <tr>
            {dayLabels.map((d, i) => (
              <th
                key={d}
                className={cn(
                  'w-10 h-7 text-center text-xs font-medium',
                  i === 0 && 'text-danger-600',
                  i === 6 && 'text-brand-600',
                  i !== 0 && i !== 6 && 'text-fg-muted',
                )}
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
                  return <td key={ci} className="w-10 h-9 p-0" />
                }
                const isSelected = selectedSet.has(cell.dateStr)
                const isToday = cell.dateStr === todayStr
                const isPast = disablePast && cell.dateStr < todayStr
                return (
                  <td key={ci} className="w-10 h-9 p-0.5">
                    <button
                      type="button"
                      onClick={() => toggleDate(cell.dateStr)}
                      data-testid={`calendar-day-${cell.dateStr}`}
                      aria-label={`${cell.dateStr}${isSelected ? '（選択中）' : ''}${isPast ? '（選択不可）' : ''}`}
                      aria-pressed={isSelected}
                      disabled={isPast}
                      className={cn(
                        'w-full h-full rounded-md text-sm font-medium transition-colors',
                        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500',
                        isPast
                          ? 'text-fg-subtle/50 line-through cursor-not-allowed'
                          : isSelected
                            ? 'bg-brand-600 text-white hover:bg-brand-700'
                            : isToday
                              ? 'border border-brand-500 text-brand-700 hover:bg-brand-50'
                              : ci === 0
                                ? 'text-danger-600 hover:bg-surface-sunken'
                                : ci === 6
                                  ? 'text-brand-600 hover:bg-surface-sunken'
                                  : 'text-fg hover:bg-surface-sunken',
                      )}
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

      <div className="mt-3">
        {value.length === 0 ? (
          <p className="text-xs text-fg-muted">
            まだ候補日が選択されていません。カレンダーから日付をクリックして選択してください。
          </p>
        ) : (
          <div
            data-testid="selected-dates-list"
            className="flex flex-wrap gap-1.5"
          >
            {value.map((d) => (
              <span
                key={d}
                className="inline-flex items-center gap-1 rounded-full bg-brand-50 border border-brand-200 px-2.5 py-0.5 text-xs font-medium text-brand-700"
              >
                {d}
                <button
                  type="button"
                  onClick={() => toggleDate(d)}
                  aria-label={`${d} を解除`}
                  data-testid={`selected-date-remove-${d}`}
                  className="text-brand-700 hover:text-brand-900 leading-none focus-visible:outline-none"
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

function parseHHMM(s: string): number | null {
  const m = /^(\d{1,2}):(\d{2})$/.exec(s)
  if (!m) return null
  const h = Number(m[1])
  const min = Number(m[2])
  if (h < 0 || h > 23 || min < 0 || min > 59) return null
  return h * 60 + min
}

function formatHHMM(totalMin: number): string {
  const h = Math.floor(totalMin / 60)
  const m = totalMin % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}

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

/**
 * カンマ/改行区切りの出席番号テキストを解析し、有効な番号・重複・無効トークンに分類する。
 * - 正の整数のみ採用
 * - 0 や負数、非数値（"abc"）は invalid に分類
 * - 同じ番号が複数回出現したら duplicates に記録（採用リストは重複排除）
 */
function parseStudentNumbers(text: string): {
  numbers: number[]
  duplicates: number[]
  invalid: string[]
} {
  const tokens = text
    .split(/[\n,]/)
    .map((s) => s.trim())
    .filter(Boolean)

  const numbers: number[] = []
  const seen = new Set<number>()
  const duplicates: number[] = []
  const invalid: string[] = []

  for (const t of tokens) {
    const n = Number(t)
    if (!Number.isInteger(n) || n <= 0) {
      invalid.push(t)
      continue
    }
    if (seen.has(n)) {
      if (!duplicates.includes(n)) duplicates.push(n)
      continue
    }
    seen.add(n)
    numbers.push(n)
  }

  return {
    numbers: [...numbers].sort((a, b) => a - b),
    duplicates: duplicates.sort((a, b) => a - b),
    invalid,
  }
}

type FieldKey = 'displayName' | 'candidateDates' | 'timeSlots'

export default function ProjectNewPage() {
  const navigate = useNavigate()

  const [displayName, setDisplayName] = useState('')
  const [slotMinutes, setSlotMinutes] = useState(60)
  const [candidateDates, setCandidateDates] = useState<string[]>([])
  const [startTime, setStartTime] = useState('16:00')
  const [endTime, setEndTime] = useState('17:00')
  const [studentNumbersText, setStudentNumbersText] = useState('')
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<FieldKey, string>>>(
    {},
  )
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

  const studentParse = parseStudentNumbers(studentNumbersText)
  const slicePreview = sliceTimeRange(startTime, endTime, slotMinutes)

  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setValidationError('')

    const errors: Partial<Record<FieldKey, string>> = {}

    if (!displayName.trim()) {
      errors.displayName = 'プロジェクト名を入力してください'
    }

    const dates = [...candidateDates].sort()
    if (dates.length === 0) {
      errors.candidateDates = '候補日をカレンダーから1日以上選択してください'
    }

    const timeSlots = sliceTimeRange(startTime, endTime, slotMinutes)
    if (timeSlots.length === 0) {
      errors.timeSlots = `時間枠が生成できません。終了時刻が開始時刻より後で、(終了 - 開始) が ${slotMinutes} 分以上必要です`
    }

    setFieldErrors(errors)

    if (Object.keys(errors).length > 0) {
      // テストや AT が getByRole('alert') で具体メッセージを参照できるよう、
      // 個別エラー文をすべて連結してトップ Alert に表示する。
      setValidationError(Object.values(errors).join(' / '))
      return
    }

    mutation.mutate({
      display_name: displayName.trim(),
      slot_minutes: slotMinutes,
      candidate_dates: dates,
      candidate_time_slots: timeSlots,
      student_numbers: studentParse.numbers,
    })
  }

  return (
    <AppShell
      breadcrumbs={[{ label: '新規プロジェクト作成' }]}
      title="新規プロジェクト作成"
      subtitle="面談調整に必要な基本情報を入力します。"
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-5">
        {(validationError || mutation.error) && (
          <Alert variant="error" title="入力内容を確認してください">
            {validationError || (mutation.error as Error)?.message}
          </Alert>
        )}

        <Card>
          <CardHeader
            title="基本情報"
            description="このプロジェクトを識別するための情報を入力します。"
          />
          <FormField
            label="プロジェクト名"
            htmlFor="display-name"
            required
            hint="例: 3年A組 7月面談"
            error={fieldErrors.displayName}
          >
            <Input
              id="display-name"
              type="text"
              value={displayName}
              onChange={(e) => {
                setDisplayName(e.target.value)
                if (fieldErrors.displayName) {
                  setFieldErrors((p) => ({ ...p, displayName: undefined }))
                }
              }}
              placeholder="3年A組 7月面談"
              aria-required="true"
              aria-invalid={fieldErrors.displayName ? 'true' : undefined}
              className="max-w-md"
            />
          </FormField>

          <FormField
            label="1コマの長さ"
            htmlFor="slot-minutes"
            hint="保護者1組あたりの面談時間です。5分単位で指定してください。"
          >
            <div className="flex items-center gap-2">
              <Input
                id="slot-minutes"
                type="number"
                value={slotMinutes}
                onChange={(e) => setSlotMinutes(Number(e.target.value))}
                min={5}
                max={120}
                step={5}
                className="w-24"
              />
              <span className="text-sm text-fg-muted">分</span>
            </div>
          </FormField>
        </Card>

        <Card>
          <CardHeader
            title="候補日"
            description="面談を行える日付をカレンダーから複数選択します。過去の日付は選択できません。"
            actions={
              candidateDates.length > 0 ? (
                <span className="text-xs font-medium text-fg-muted">
                  {candidateDates.length} 日選択中
                </span>
              ) : undefined
            }
          />
          <div id="candidate-dates-label" className="sr-only">
            候補日
          </div>
          <CandidateDatesCalendar
            value={candidateDates}
            onChange={(next) => {
              setCandidateDates(next)
              if (next.length > 0 && fieldErrors.candidateDates) {
                setFieldErrors((p) => ({ ...p, candidateDates: undefined }))
              }
            }}
          />
          {fieldErrors.candidateDates && (
            <p className="mt-3 text-xs text-danger-700 font-medium">
              {fieldErrors.candidateDates}
            </p>
          )}
        </Card>

        <Card>
          <CardHeader
            title="候補時間枠"
            description="開始〜終了の範囲を「1コマの長さ」ごとに分割して候補時間枠とします。"
          />
          <div className="flex flex-wrap items-end gap-4">
            <FormField label="開始" htmlFor="start-time" className="mb-0">
              <Input
                id="start-time"
                type="time"
                value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
                className="w-32"
              />
            </FormField>
            <FormField label="終了" htmlFor="end-time" className="mb-0">
              <Input
                id="end-time"
                type="time"
                value={endTime}
                onChange={(e) => setEndTime(e.target.value)}
                className="w-32"
              />
            </FormField>
          </div>

          <div className="mt-4">
            {slicePreview.length === 0 ? (
              <Alert variant="error">
                {fieldErrors.timeSlots ??
                  `現在の入力では時間枠が生成されません。終了時刻が開始時刻より後で、(終了 - 開始) が ${slotMinutes} 分以上必要です。`}
              </Alert>
            ) : (
              <div className="rounded-md bg-surface-sunken border border-border px-3 py-3">
                <div className="flex items-baseline justify-between mb-2">
                  <span className="text-xs font-medium text-fg-subtle uppercase tracking-wider">
                    生成される時間枠
                  </span>
                  <span className="text-sm font-semibold text-fg">
                    {slicePreview.length} コマ
                  </span>
                </div>
                <div className="flex flex-wrap gap-1.5 max-h-32 overflow-y-auto">
                  {slicePreview.map((s) => (
                    <span
                      key={s.start}
                      className="inline-flex items-center rounded-full bg-surface border border-border-strong px-2.5 py-0.5 text-xs font-medium text-fg"
                    >
                      {s.start}-{s.end}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </Card>

        <Card>
          <CardHeader
            title="出席番号"
            description="このプロジェクトの対象生徒の出席番号を入力します。カンマ区切り、または 1 行 1 番号で記入してください。"
            actions={
              studentParse.numbers.length > 0 ? (
                <span className="text-xs font-medium text-fg-muted">
                  {studentParse.numbers.length} 名
                </span>
              ) : undefined
            }
          />
          <FormField
            label="出席番号一覧"
            htmlFor="student-numbers"
          >
            <Textarea
              id="student-numbers"
              value={studentNumbersText}
              onChange={(e) => setStudentNumbersText(e.target.value)}
              placeholder={'1, 2, 3, ...\nまたは1行1番号'}
              rows={4}
              className="max-w-md"
            />
          </FormField>

          {/* ライブ解析結果 */}
          {studentNumbersText.trim() !== '' && (
            <div className="mt-3 flex flex-col gap-2">
              {studentParse.numbers.length > 0 && (
                <div className="rounded-md bg-surface-sunken border border-border px-3 py-2">
                  <div className="text-xs text-fg-subtle mb-1.5">
                    認識した出席番号
                  </div>
                  <div className="flex flex-wrap gap-1 max-h-24 overflow-y-auto">
                    {studentParse.numbers.map((n) => (
                      <span
                        key={n}
                        className="inline-flex items-center rounded-full bg-brand-50 border border-brand-200 px-2 py-0.5 text-xs font-medium text-brand-700"
                      >
                        {n}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {studentParse.duplicates.length > 0 && (
                <Alert variant="warning">
                  重複する番号があります（自動で 1 件にまとめます）:{' '}
                  <strong>{studentParse.duplicates.join(', ')}</strong>
                </Alert>
              )}
              {studentParse.invalid.length > 0 && (
                <Alert variant="warning">
                  正の整数として解釈できなかったため除外します:{' '}
                  <strong>{studentParse.invalid.join(', ')}</strong>
                </Alert>
              )}
            </div>
          )}
        </Card>

        <div className="flex gap-2 sticky bottom-0 bg-surface-muted py-3 -mx-6 px-6 border-t border-border">
          <Button
            type="submit"
            variant="primary"
            size="lg"
            disabled={mutation.isPending}
          >
            {mutation.isPending ? '作成中...' : '作成'}
          </Button>
          <Button
            type="button"
            variant="secondary"
            size="lg"
            onClick={() => navigate('/')}
          >
            キャンセル
          </Button>
        </div>
      </form>
    </AppShell>
  )
}
