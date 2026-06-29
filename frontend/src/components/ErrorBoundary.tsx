/**
 * エラーバウンダリコンポーネント
 *
 * 子コンポーネントで発生した予期しない例外を捕捉し、
 * 日本語のフォールバック UI を表示する。
 *
 * requirements.md §4.1 のエラー時確認観点に対応。
 */

import React from 'react'

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
}

interface ErrorBoundaryProps {
  children: React.ReactNode
}

/**
 * アプリ全体を包むエラーバウンダリ。
 *
 * 子コンポーネントが throw したとき、フォールバック UI（日本語メッセージ +
 * 再読み込みボタン）を表示する。
 */
class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    console.error('ErrorBoundary がエラーを捕捉しました:', error, info)
  }

  render(): React.ReactNode {
    if (this.state.hasError) {
      return (
        <div
          role="alert"
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            minHeight: '100vh',
            padding: '2rem',
            textAlign: 'center',
          }}
        >
          <h1 style={{ fontSize: '1.5rem', marginBottom: '1rem' }}>
            エラーが発生しました。ページを再読み込みしてください。
          </h1>
          <button
            onClick={() => window.location.reload()}
            style={{
              padding: '0.5rem 1.5rem',
              fontSize: '1rem',
              cursor: 'pointer',
            }}
          >
            再読み込み
          </button>
        </div>
      )
    }

    return this.props.children
  }
}

export default ErrorBoundary
