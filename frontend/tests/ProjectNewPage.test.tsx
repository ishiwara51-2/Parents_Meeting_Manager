/**
 * ProjectNewPage のテスト
 * Phase 4.2 - TDD RED フェーズ
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import type { ReactElement } from 'react'
import ProjectNewPage from '../src/pages/ProjectNewPage'
import * as api from '../src/api'

vi.mock('../src/api', () => ({
  projectsApi: {
    create: vi.fn(),
  },
}))

function renderWithProviders(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/projects/new']}>
        {ui}
      </MemoryRouter>
    </QueryClientProvider>
  )
}

function renderWithRoutes() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/projects/new']}>
        <Routes>
          <Route path="/projects/new" element={<ProjectNewPage />} />
          <Route
            path="/projects/:projectId"
            element={<div data-testid="project-page">プロジェクト画面</div>}
          />
          <Route path="/" element={<div data-testid="home-page">ホーム</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('ProjectNewPage', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  it('プロジェクト名入力フィールドが存在する', () => {
    renderWithProviders(<ProjectNewPage />)

    // display_name に対応するラベル付きinput
    const input = screen.getByLabelText(/プロジェクト名/)
    expect(input).toBeInTheDocument()
  })

  it('作成ボタンが存在する', () => {
    renderWithProviders(<ProjectNewPage />)

    expect(screen.getByRole('button', { name: '作成' })).toBeInTheDocument()
  })

  it('プロジェクト名未入力でサブミットするとエラーを表示する', async () => {
    const user = userEvent.setup()
    renderWithProviders(<ProjectNewPage />)

    const submitButton = screen.getByRole('button', { name: '作成' })
    await user.click(submitButton)

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
  })

  it('APIモックで作成成功後にプロジェクト画面へ遷移する', async () => {
    vi.mocked(api.projectsApi.create).mockResolvedValue({
      project_id: 'new-project-id',
      display_name: 'テスト面談',
      created_at: '2026-07-01T10:00:00+09:00',
      status: 'in_progress',
      slot_minutes: 20,
      candidate_dates: ['2026-07-15'],
      candidate_time_slots: [{ start: '16:00', end: '16:20' }],
      student_numbers: [1, 2, 3],
    })

    const user = userEvent.setup()
    renderWithRoutes()

    // プロジェクト名を入力
    const nameInput = screen.getByLabelText(/プロジェクト名/)
    await user.type(nameInput, 'テスト面談')

    // 候補日を入力 (textarea)
    const datesInput = screen.getByLabelText(/候補日/)
    await user.type(datesInput, '2026-07-15')

    // 作成ボタンをクリック
    const submitButton = screen.getByRole('button', { name: '作成' })
    await user.click(submitButton)

    // プロジェクト画面に遷移していることを確認
    await waitFor(() => {
      expect(screen.getByTestId('project-page')).toBeInTheDocument()
    })
  })
})
