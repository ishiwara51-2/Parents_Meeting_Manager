/** 枠線・角丸・影を持つ共通コンテナ。CardHeader と組み合わせて使う想定。 */
import type { HTMLAttributes, ReactNode } from 'react'
import { cn } from './cn'

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode
  padding?: 'none' | 'sm' | 'md' | 'lg'
  /** クリック可能なカード（一覧項目など）にホバー時の視覚フィードバックを付与する */
  interactive?: boolean
}

const paddings = {
  none: '',
  sm: 'p-3',
  md: 'p-5',
  lg: 'p-6',
}

export function Card({
  className,
  padding = 'md',
  interactive = false,
  children,
  ...rest
}: CardProps) {
  return (
    <div
      className={cn(
        'bg-surface border border-border rounded-lg shadow-card',
        paddings[padding],
        interactive &&
          'cursor-pointer transition-colors hover:border-border-strong hover:bg-surface-muted',
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  )
}

interface CardHeaderProps extends Omit<HTMLAttributes<HTMLDivElement>, 'title'> {
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
}

/** Card 上部に置く見出し + 補足説明 + アクションボタン群のレイアウト。 */
export function CardHeader({
  title,
  description,
  actions,
  className,
  ...rest
}: CardHeaderProps) {
  return (
    <div
      className={cn(
        'flex items-start justify-between gap-3 mb-4',
        className,
      )}
      {...rest}
    >
      <div className="min-w-0">
        <h2 className="text-lg font-semibold text-fg leading-tight">{title}</h2>
        {description && (
          <p className="mt-1 text-sm text-fg-muted">{description}</p>
        )}
      </div>
      {actions && <div className="flex gap-2 shrink-0">{actions}</div>}
    </div>
  )
}
