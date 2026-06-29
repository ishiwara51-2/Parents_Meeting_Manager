/**
 * ErrorBoundary のテスト
 * Phase 6.1 - TDD RED フェーズ: エラーバウンダリのフォールバック UI
 *
 * テスト対象:
 *   - 子コンポーネントがエラーを throw したとき、フォールバック UI が表示される
 *   - 「エラーが発生しました。ページを再読み込みしてください。」が表示される
 *   - 再読み込みボタンが表示される
 *
 * RED フェーズ: ErrorBoundary コンポーネントが未実装のためインポートエラーで全テスト失敗する想定。
 */

import { render, screen } from '@testing-library/react'
import ErrorBoundary from '../src/components/ErrorBoundary'

/** エラーを意図的に throw するコンポーネント */
function ThrowingComponent(): React.ReactNode {
  throw new Error('テスト用エラー')
}

const originalConsoleError = console.error

describe('ErrorBoundary', () => {
  beforeEach(() => {
    // React がエラーバウンダリのエラーをコンソールに出力するため抑制
    console.error = vi.fn()
  })

  afterEach(() => {
    console.error = originalConsoleError
  })

  it('子コンポーネントがエラーを throw したとき、フォールバック UI が表示される', () => {
    render(
      <ErrorBoundary>
        <ThrowingComponent />
      </ErrorBoundary>
    )
    expect(screen.getByText(/エラーが発生しました/)).toBeInTheDocument()
  })

  it('フォールバック UI に再読み込みメッセージが含まれる', () => {
    render(
      <ErrorBoundary>
        <ThrowingComponent />
      </ErrorBoundary>
    )
    // h1 メッセージ・ボタン両方に「再読み込み」が含まれるため getAllByText を使用
    expect(screen.getAllByText(/再読み込み/).length).toBeGreaterThan(0)
  })

  it('再読み込みボタンが表示される', () => {
    render(
      <ErrorBoundary>
        <ThrowingComponent />
      </ErrorBoundary>
    )
    expect(screen.getByRole('button')).toBeInTheDocument()
  })
})
