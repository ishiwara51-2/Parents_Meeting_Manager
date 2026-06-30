import type { HTMLAttributes, ReactNode } from 'react'
import { cn } from './cn'

export type AlertVariant = 'error' | 'success' | 'warning' | 'info'

interface AlertProps extends Omit<HTMLAttributes<HTMLDivElement>, 'title'> {
  variant: AlertVariant
  title?: ReactNode
  children?: ReactNode
}

const variants: Record<AlertVariant, { box: string; icon: string; label: string }> = {
  error: {
    box: 'bg-danger-50 border-danger-200 text-danger-700',
    icon: '⛔',
    label: 'エラー',
  },
  success: {
    box: 'bg-success-50 border-success-200 text-success-700',
    icon: '✓',
    label: '完了',
  },
  warning: {
    box: 'bg-warning-50 border-warning-200 text-warning-700',
    icon: '⚠',
    label: '注意',
  },
  info: {
    box: 'bg-brand-50 border-brand-200 text-brand-700',
    icon: 'ℹ',
    label: '情報',
  },
}

export function Alert({
  variant,
  title,
  className,
  children,
  role,
  ...rest
}: AlertProps) {
  const v = variants[variant]
  return (
    <div
      role={role ?? (variant === 'success' ? 'status' : 'alert')}
      className={cn(
        'border rounded-md px-4 py-3 text-sm flex gap-3 items-start',
        v.box,
        className,
      )}
      {...rest}
    >
      <span aria-hidden="true" className="text-base leading-6 shrink-0">
        {v.icon}
      </span>
      <div className="min-w-0 flex-1">
        {title && <div className="font-semibold mb-0.5">{title}</div>}
        {children && <div className="text-current/90">{children}</div>}
      </div>
    </div>
  )
}
