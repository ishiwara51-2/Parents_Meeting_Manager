/**
 * SavedPage のテスト
 * Phase 4.4c - TDD RED フェーズ: 保存完了画面・再編集フロー
 *
 * テスト対象: requirements.md §4.8
 *   - PDF出力ボタンのスタブ表示
 *   - 再編集ボタンで draftsApi.unlock を呼ぶ
 *   - unlock 成功時に SchedulePage へ遷移
 */

import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import SavedPage from '../src/pages/SavedPage'
import * as api from '../src/api'

vi.mock('../src/api', () => ({
  draftsApi: {
    unlock: vi.fn(),
    save: vi.fn(),
    getLatest: vi.fn(),
  },
  scheduleApi: { run: vi.fn() },
  projectsApi: { get: vi.fn() },
  responsesApi: { list: vi.fn() },
}))

const PROJECT_ID = 'test-project-id'

const MOCK_DRAFT = {
  project_id: PROJECT_ID,
  saved_at: '2026-07-15T20:00:00+09:00',
  locked: false,
  assignments: [
    { student_number: 1, date: '2026-07-15', start: '16:00:00', end: '16:20:00' },
  ],
  unassigned_students: [],
  violated_constraints: [],
}

/** projectId パラメータ付きルートで SavedPage をレンダリングするヘルパー */
function renderSavedPage(projectId = PROJECT_ID) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/projects/${projectId}/saved`]}>
        <Routes>
          <Route path="/projects/:projectId/saved" element={<SavedPage />} />
          <Route path="/projects/:projectId/schedule" element={<div>SchedulePage</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('SavedPage', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  it('「PDF出力」ボタンが表示される', () => {
    renderSavedPage()
    expect(screen.getByRole('button', { name: 'PDF出力' })).toBeInTheDocument()
  })

  it('「再編集」ボタンが表示される', () => {
    renderSavedPage()
    expect(screen.getByRole('button', { name: '再編集' })).toBeInTheDocument()
  })

  it('「PDF出力」ボタンクリックでスタブメッセージがコンソールに出力される', () => {
    const consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {})
    renderSavedPage()
    fireEvent.click(screen.getByRole('button', { name: 'PDF出力' }))
    expect(consoleSpy).toHaveBeenCalledWith('PDF download not yet implemented')
    consoleSpy.mockRestore()
  })

  it('「再編集」ボタンクリックで draftsApi.unlock が正しい projectId で呼ばれる', async () => {
    vi.mocked(api.draftsApi.unlock).mockResolvedValue(MOCK_DRAFT)
    renderSavedPage()
    fireEvent.click(screen.getByRole('button', { name: '再編集' }))
    await waitFor(() => {
      expect(vi.mocked(api.draftsApi.unlock)).toHaveBeenCalledWith(PROJECT_ID)
    })
  })

  it('再編集成功時に SchedulePage へ遷移する', async () => {
    vi.mocked(api.draftsApi.unlock).mockResolvedValue(MOCK_DRAFT)
    renderSavedPage()
    fireEvent.click(screen.getByRole('button', { name: '再編集' }))
    await waitFor(() => {
      expect(screen.getByText('SchedulePage')).toBeInTheDocument()
    })
  })
})
