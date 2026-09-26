/** フォーム入力の共通スタイルを持つ <input>/<textarea> ラッパー。属性はそのまま透過する。 */
import type { InputHTMLAttributes, TextareaHTMLAttributes } from 'react'
import { cn } from './cn'

// Input と Textarea で共有する枠線・フォーカス・disabled 時のスタイル
const baseField =
  'block w-full rounded-md border bg-surface px-3 py-2 text-sm text-fg ' +
  'border-border-strong placeholder:text-fg-subtle ' +
  'transition-colors ' +
  'focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/30 ' +
  'disabled:bg-surface-sunken disabled:cursor-not-allowed disabled:opacity-70'

export function Input({
  className,
  type = 'text',
  ...rest
}: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      type={type}
      className={cn(baseField, 'h-10', className)}
      {...rest}
    />
  )
}

/** 複数行入力用。rows の既定値は 4。 */
export function Textarea({
  className,
  rows = 4,
  ...rest
}: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      rows={rows}
      className={cn(baseField, 'leading-6 resize-y', className)}
      {...rest}
    />
  )
}
