/**
 * AppShell のテスト
 * ログイン状態バッジ（全画面ヘッダー共通表示）
 */

import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import type { ReactElement } from 'react'
import { AppShell } from '../src/components/ui'
import * as api from '../src/api'

vi.mock('../src/api', () => ({
  authApi: {
    status: vi.fn(),
    startGoogle: vi.fn(),
  },
}))

function renderWithProviders(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe('AppShell', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  it('未認証時はヘッダーに「Googleでログイン」ボタンを表示する', async () => {
    vi.mocked(api.authApi.status).mockResolvedValue({ authenticated: false })

    renderWithProviders(<AppShell>本文</AppShell>)

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: 'Googleでログイン' })
      ).toBeInTheDocument()
    })
  })

  it('認証済み時はヘッダーに email を表示する', async () => {
    vi.mocked(api.authApi.status).mockResolvedValue({
      authenticated: true,
      email: 'teacher@example.com',
    })

    renderWithProviders(<AppShell>本文</AppShell>)

    await waitFor(() => {
      expect(screen.getByText(/ログイン済み/)).toBeInTheDocument()
      expect(screen.getByText('teacher@example.com')).toBeInTheDocument()
    })
  })

  it('どの画面（headerRight や title の有無に関わらず）でも認証バッジを表示する', async () => {
    vi.mocked(api.authApi.status).mockResolvedValue({ authenticated: false })

    renderWithProviders(
      <AppShell title="任意の画面タイトル">本文</AppShell>
    )

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: 'Googleでログイン' })
      ).toBeInTheDocument()
    })
  })
})
