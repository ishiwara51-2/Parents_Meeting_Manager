import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { cn } from './cn'

export type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost'
export type ButtonSize = 'sm' | 'md' | 'lg'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  children: ReactNode
}

const base =
  'inline-flex items-center justify-center gap-2 font-medium rounded-md ' +
  'transition-colors duration-150 ' +
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 ' +
  'disabled:cursor-not-allowed disabled:opacity-60 ' +
  'whitespace-nowrap select-none'

const variants: Record<ButtonVariant, string> = {
  primary:
    'bg-brand-600 text-white shadow-sm ' +
    'hover:bg-brand-700 active:bg-brand-800 ' +
    'focus-visible:ring-brand-500 ' +
    'disabled:hover:bg-brand-600',
  secondary:
    'bg-white text-fg border border-border-strong ' +
    'hover:bg-surface-sunken active:bg-border ' +
    'focus-visible:ring-brand-500',
  danger:
    'bg-danger-600 text-white shadow-sm ' +
    'hover:bg-danger-700 active:bg-danger-700 ' +
    'focus-visible:ring-danger-500',
  ghost:
    'bg-transparent text-fg-muted ' +
    'hover:bg-surface-sunken hover:text-fg ' +
    'focus-visible:ring-brand-500',
}

const sizes: Record<ButtonSize, string> = {
  sm: 'h-8 px-3 text-sm',
  md: 'h-10 px-4 text-sm',
  lg: 'h-12 px-6 text-base',
}

export function Button({
  variant = 'secondary',
  size = 'md',
  className,
  type = 'button',
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={cn(base, variants[variant], sizes[size], className)}
      {...rest}
    >
      {children}
    </button>
  )
}
