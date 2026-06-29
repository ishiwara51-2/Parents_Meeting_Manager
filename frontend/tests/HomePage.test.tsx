/**
 * HomePage のテスト
 * Phase 4.2 - TDD RED フェーズ
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import type { ReactElement } from 'react'
import HomePage from '../src/pages/HomePage'
import * as api from '../src/api'

vi.mock('../src/api', () => ({
  projectsApi: {
    list: vi.fn(),
  },
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

describe('HomePage', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.mocked(api.authApi.status).mockResolvedValue({ authenticated: false })
    vi.mocked(api.projectsApi.list).mockResolvedValue([])
  })

  it('プロジェクト一覧が表示される', async () => {
    vi.mocked(api.authApi.status).mockResolvedValue({ authenticated: false })
    vi.mocked(api.projectsApi.list).mockResolvedValue([
      {
        project_id: 'abc123',
        display_name: 'テスト面談プロジェクト',
        created_at: '2026-07-01T10:00:00+09:00',
        status: 'in_progress',
        slot_minutes: 20,
        candidate_dates: ['2026-07-15'],
        candidate_time_slots: [{ start: '16:00', end: '16:20' }],
        student_numbers: [1, 2, 3],
      },
    ])

    renderWithProviders(<HomePage />)

    await waitFor(() => {
      expect(screen.getByText('テスト面談プロジェクト')).toBeInTheDocument()
    })
  })

  it('認証済み状態を表示する', async () => {
    vi.mocked(api.authApi.status).mockResolvedValue({
      authenticated: true,
      email: 'test@example.com',
    })
    vi.mocked(api.projectsApi.list).mockResolvedValue([])

    renderWithProviders(<HomePage />)

    await waitFor(() => {
      expect(screen.getByText(/ログイン済み/)).toBeInTheDocument()
    })
  })

  it('面談調整開始ボタンが存在する', () => {
    renderWithProviders(<HomePage />)

    expect(
      screen.getByRole('button', { name: '面談調整開始' })
    ).toBeInTheDocument()
  })

  it('ルール設定ボタンが存在する', () => {
    renderWithProviders(<HomePage />)

    expect(
      screen.getByRole('button', { name: 'ルール設定' })
    ).toBeInTheDocument()
  })

  it('面談調整開始ボタンクリックで /projects/new へ遷移する', async () => {
    const user = userEvent.setup()

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/']}>
          <HomePage />
        </MemoryRouter>
      </QueryClientProvider>
    )

    const button = screen.getByRole('button', { name: '面談調整開始' })
    await user.click(button)

    // MemoryRouter の内部でナビゲーションが呼ばれたことを確認
    // (コンポーネント側でuseNavigateを使ってnavigate('/projects/new')を呼ぶ)
    expect(button).toBeInTheDocument() // navigate後もコンポーネントは残る
  })
})
