/**
 * 期間選択（プロジェクトの候補日の中から、開始日と終了日をカレンダー上でクリックして選ぶ）。
 *
 * - ボタンを押すとカレンダーが開く。候補日だけがクリックできる。
 * - 1 回目のクリックで開始日、2 回目のクリックで終了日（開始日以降）を決めて閉じる。
 *   開始日より前の日、または選択済みの状態でクリックした場合は、開始日の選び直しになる。
 */
import { useState } from 'react'
import { Button } from './ui'
import { cn } from './ui/cn'

interface Props {
  from: string
  to: string
  /** 選択できる日（"YYYY-MM-DD"）。プロジェクトの候補日 */
  candidateDates: string[]
  onChange: (from: string, to: string) => void
  ariaLabel: string
}

const WEEKDAYS = ['日', '月', '火', '水', '木', '金', '土']

const pad = (n: number) => String(n).padStart(2, '0')

/** "2026-07-15" → "7/15" */
function shortDate(iso: string): string {
  return `${Number(iso.slice(5, 7))}/${Number(iso.slice(8, 10))}`
}

export default function PeriodPicker({ from, to, candidateDates, onChange, ariaLabel }: Props) {
  const sorted = [...candidateDates].sort()
  const candidateSet = new Set(sorted)
  const anchor = from || sorted[0] || ''
  const [open, setOpen] = useState(false)
  const [view, setView] = useState<{ y: number; m: number }>(() => {
    const base = anchor ? new Date(Number(anchor.slice(0, 4)), Number(anchor.slice(5, 7)) - 1, 1) : new Date()
    return { y: base.getFullYear(), m: base.getMonth() }
  })

  const label = from && to
    ? `${shortDate(from)} 〜 ${shortDate(to)}`
    : from
      ? `${shortDate(from)} 〜 （終了日を選択）`
      : '期間を選択'

  const moveMonth = (delta: number) => {
    const d = new Date(view.y, view.m + delta, 1)
    setView({ y: d.getFullYear(), m: d.getMonth() })
  }

  const pick = (date: string) => {
    if (!from || to || date < from) {
      onChange(date, '')
    } else {
      onChange(from, date)
      setOpen(false)
    }
  }

  const daysInMonth = new Date(view.y, view.m + 1, 0).getDate()
  const firstWeekday = new Date(view.y, view.m, 1).getDay()
  const cells: (number | null)[] = [
    ...Array<null>(firstWeekday).fill(null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ]

  return (
    <div className="relative min-w-0 flex-[2]">
      <button
        type="button"
        aria-label={ariaLabel}
        aria-expanded={open}
        disabled={sorted.length === 0}
        onClick={() => setOpen((o) => !o)}
        className={cn(
          'h-10 w-full truncate rounded-md border border-border-strong bg-surface px-3 text-left text-sm',
          'focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/30',
          'disabled:cursor-not-allowed disabled:bg-surface-sunken disabled:opacity-70',
          !from && 'text-fg-subtle',
        )}
      >
        {sorted.length === 0 ? '候補日がありません' : label}
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="期間の選択"
          className="absolute left-0 top-full z-20 mt-1 w-72 rounded-lg border border-border bg-surface p-3 shadow-lg"
        >
          <div className="mb-2 flex items-center justify-between">
            <button
              type="button"
              aria-label="前の月"
              onClick={() => moveMonth(-1)}
              className="h-8 w-8 rounded-md text-fg-muted hover:bg-surface-sunken"
            >
              ◀
            </button>
            <span className="text-sm font-semibold">
              {view.y}年 {view.m + 1}月
            </span>
            <button
              type="button"
              aria-label="次の月"
              onClick={() => moveMonth(1)}
              className="h-8 w-8 rounded-md text-fg-muted hover:bg-surface-sunken"
            >
              ▶
            </button>
          </div>

          <div className="grid grid-cols-7 gap-0.5 text-center">
            {WEEKDAYS.map((w) => (
              <div key={w} className="h-6 text-xs font-medium text-fg-muted">
                {w}
              </div>
            ))}
            {cells.map((day, i) => {
              if (day === null) return <div key={`b${i}`} />
              const date = `${view.y}-${pad(view.m + 1)}-${pad(day)}`
              const isCandidate = candidateSet.has(date)
              const isEdge = date === from || date === to
              const inRange = !!from && !!to && date >= from && date <= to
              return (
                <button
                  key={date}
                  type="button"
                  aria-label={`${date}${isCandidate ? '' : '（選択不可）'}`}
                  disabled={!isCandidate}
                  onClick={() => pick(date)}
                  className={cn(
                    'h-8 rounded-md text-sm transition-colors',
                    !isCandidate && 'cursor-not-allowed text-fg-subtle/50',
                    isCandidate && !isEdge && !inRange && 'font-medium text-fg hover:bg-brand-50',
                    isCandidate && inRange && !isEdge && 'bg-brand-50 font-medium text-brand-700',
                    isEdge && 'bg-brand-600 font-medium text-white',
                  )}
                >
                  {day}
                </button>
              )
            })}
          </div>

          <div className="mt-2 flex items-center justify-between">
            <p className="text-xs text-fg-muted">
              {from && !to ? '終了日をクリックしてください' : '開始日、終了日の順にクリックします'}
            </p>
            <Button variant="secondary" size="sm" onClick={() => setOpen(false)}>
              閉じる
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
