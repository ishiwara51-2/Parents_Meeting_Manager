/** 小さなラベル/ステータス表示用の丸みを帯びたバッジ。 */
import type { HTMLAttributes, ReactNode } from 'react'
import { cn } from './cn'

/** バッジの色調（意味づけ: brand=強調, success/warning/danger=状態, neutral=既定） */
export type BadgeTone =
  | 'neutral'
  | 'brand'
  | 'success'
  | 'warning'
  | 'danger'

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone
  children: ReactNode
}

// tone ごとの配色クラス
const tones: Record<BadgeTone, string> = {
  neutral: 'bg-surface-sunken text-fg-muted border-border',
  brand: 'bg-brand-50 text-brand-700 border-brand-200',
  success: 'bg-success-50 text-success-700 border-success-200',
  warning: 'bg-warning-50 text-warning-700 border-warning-200',
  danger: 'bg-danger-50 text-danger-700 border-danger-200',
}

export function Badge({
  tone = 'neutral',
  className,
  children,
  ...rest
}: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full border ' +
          'px-2.5 py-0.5 text-xs font-medium leading-5',
        tones[tone],
        className,
      )}
      {...rest}
    >
      {children}
    </span>
  )
}
