import type { ReactNode } from 'react'
import { cn } from './cn'

interface FormFieldProps {
  /** input の id と紐づけるラベルテキスト */
  label: ReactNode
  /** input の id（label の htmlFor と紐づく） */
  htmlFor: string
  required?: boolean
  /** 補助テキスト（ラベル下に淡く表示） */
  hint?: ReactNode
  /** エラーメッセージ（赤で表示） */
  error?: ReactNode
  /** ラベルとフィールドの間に挟む追加説明（hint より目立つ） */
  description?: ReactNode
  children: ReactNode
  className?: string
}

export function FormField({
  label,
  htmlFor,
  required = false,
  hint,
  error,
  description,
  children,
  className,
}: FormFieldProps) {
  return (
    <div className={cn('mb-5', className)}>
      <label
        htmlFor={htmlFor}
        className="block mb-1.5 text-sm font-medium text-fg"
      >
        {label}
        {required && (
          <span
            aria-hidden="true"
            className="ml-1 text-danger-600"
            title="必須項目"
          >
            *
          </span>
        )}
      </label>
      {description && (
        <p className="mb-2 text-sm text-fg-muted">{description}</p>
      )}
      {children}
      {hint && !error && (
        <p className="mt-1.5 text-xs text-fg-subtle">{hint}</p>
      )}
      {error && (
        <p className="mt-1.5 text-xs text-danger-700 font-medium">{error}</p>
      )}
    </div>
  )
}
