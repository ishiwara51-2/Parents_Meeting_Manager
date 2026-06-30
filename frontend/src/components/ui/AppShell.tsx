import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { cn } from './cn'

export interface Breadcrumb {
  label: ReactNode
  /** 省略すると現在ページ扱いになりリンクではなくテキストで表示される */
  to?: string
}

interface AppShellProps {
  /** ヘッダー右端に表示する内容（認証バッジ等） */
  headerRight?: ReactNode
  /**
   * パンくず。先頭の "ホーム" は自動付与されるため省略可。
   * 末尾要素は現在ページとして強調表示される。
   */
  breadcrumbs?: Breadcrumb[]
  /** 画面タイトル（ページ <h1> として表示） */
  title?: ReactNode
  /** タイトル下の補足説明 */
  subtitle?: ReactNode
  /** ヘッダー右端（タイトル行）に表示するアクション群 */
  actions?: ReactNode
  /** 本文。max-w-5xl で中央寄せされる */
  children: ReactNode
  /** 本文コンテナの幅を広げたい場合 */
  wide?: boolean
}

/** アプリロゴ（インライン SVG）。カレンダー＋人物のモチーフ。 */
function LogoMark({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      width="28"
      height="28"
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <rect
        x="3"
        y="6"
        width="26"
        height="22"
        rx="3"
        className="fill-brand-50"
        stroke="currentColor"
        strokeWidth="2"
      />
      <rect x="3" y="6" width="26" height="6" rx="3" fill="currentColor" />
      <line
        x1="10"
        y1="3"
        x2="10"
        y2="9"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
      <line
        x1="22"
        y1="3"
        x2="22"
        y2="9"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
      <circle cx="16" cy="19" r="2.5" fill="currentColor" />
      <path
        d="M11 25 Q 16 21 21 25"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        fill="none"
      />
    </svg>
  )
}

function Breadcrumbs({ items }: { items: Breadcrumb[] }) {
  // 先頭に "ホーム" を自動付与（先頭がホームでなければ）
  const fullItems: Breadcrumb[] =
    items[0]?.to === '/' ? items : [{ label: 'ホーム', to: '/' }, ...items]

  return (
    <nav aria-label="パンくず" className="mb-2">
      <ol className="flex items-center gap-1.5 text-xs text-fg-muted flex-wrap">
        {fullItems.map((item, i) => {
          const isLast = i === fullItems.length - 1
          return (
            <li key={i} className="flex items-center gap-1.5">
              {i > 0 && (
                <span aria-hidden="true" className="text-fg-subtle">
                  /
                </span>
              )}
              {item.to && !isLast ? (
                <Link
                  to={item.to}
                  className="hover:text-brand-700 hover:underline transition-colors"
                >
                  {item.label}
                </Link>
              ) : (
                <span
                  className={cn(
                    isLast && 'font-semibold text-fg',
                  )}
                  aria-current={isLast ? 'page' : undefined}
                >
                  {item.label}
                </span>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}

export function AppShell({
  headerRight,
  breadcrumbs,
  title,
  subtitle,
  actions,
  children,
  wide = false,
}: AppShellProps) {
  return (
    <div className="min-h-full bg-surface-muted">
      <header className="bg-surface border-b border-border sticky top-0 z-10">
        <div
          className={cn(
            'mx-auto px-6 py-3 flex items-center justify-between gap-4',
            wide ? 'max-w-7xl' : 'max-w-5xl',
          )}
        >
          <Link
            to="/"
            className="flex items-center gap-2.5 font-semibold text-fg hover:text-brand-700 transition-colors"
          >
            <span className="text-brand-600">
              <LogoMark />
            </span>
            <span>保護者面談調整ツール</span>
          </Link>
          {headerRight && (
            <div className="flex items-center gap-3 text-sm">
              {headerRight}
            </div>
          )}
        </div>
      </header>

      <main
        className={cn(
          'mx-auto px-6 py-8',
          wide ? 'max-w-7xl' : 'max-w-5xl',
        )}
      >
        {(title || breadcrumbs || actions) && (
          <div className="mb-6 flex items-start justify-between gap-4 flex-wrap">
            <div className="min-w-0">
              {breadcrumbs && breadcrumbs.length > 0 && (
                <Breadcrumbs items={breadcrumbs} />
              )}
              {title && (
                <h1 className="text-2xl font-semibold text-fg leading-tight">
                  {title}
                </h1>
              )}
              {subtitle && (
                <p className="mt-1 text-sm text-fg-muted">{subtitle}</p>
              )}
            </div>
            {actions && (
              <div className="flex gap-2 shrink-0">{actions}</div>
            )}
          </div>
        )}

        {children}
      </main>
    </div>
  )
}
