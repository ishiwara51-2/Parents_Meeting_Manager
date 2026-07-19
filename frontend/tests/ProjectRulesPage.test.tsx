/**
 * ProjectRulesPage のテスト
 * Phase 4.3 - TDD RED フェーズ
 *
 * テスト対象: requirements.md §4.5.2
 *   - プロジェクトルール設定フォームの表示
 *   - 保存処理
 *   - 保存成功メッセージ
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import ProjectRulesPage from '../src/pages/ProjectRulesPage'
import * as api from '../src/api'

vi.mock('../src/api', () => ({
  rulesApi: {
    getProject: vi.fn(),
    putProject: vi.fn(),
  },
}))

const PROJECT_ID = 'test-project-id'

const DEFAULT_RULES = {
  global_constraints: {
    max_consecutive_slots: 4,
    forced_break_slots: 1,
    max_slots_per_day: 20,
    teacher_unavailable: [],
  },
  student_constraints: [],
}

/** projectId パラメータ付きルートで ProjectRulesPage をレンダリングするヘルパー */
function renderProjectRulesPage(projectId = PROJECT_ID) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/projects/${projectId}/rules`]}>
        <Routes>
          <Route
            path="/projects/:projectId/rules"
            element={<ProjectRulesPage />}
          />
          <Route
            path="/projects/:projectId"
            element={<div data-testid="project-page">プロジェクト</div>}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('ProjectRulesPage', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.mocked(api.rulesApi.getProject).mockResolvedValue(DEFAULT_RULES)
    vi.mocked(api.rulesApi.putProject).mockResolvedValue(DEFAULT_RULES)
  })

  it('ルール設定フォームが表示される', async () => {
    renderProjectRulesPage()
    await waitFor(() => {
      expect(screen.getByLabelText(/最大連続コマ数/)).toBeInTheDocument()
    })
  })

  it('保存ボタンが存在する', async () => {
    renderProjectRulesPage()
    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: '保存' })
      ).toBeInTheDocument()
    })
  })

  it('保存成功時にメッセージを表示する', async () => {
    const user = userEvent.setup()
    renderProjectRulesPage()

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: '保存' })
      ).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: '保存' }))

    await waitFor(() => {
      expect(screen.getByRole('status')).toBeInTheDocument()
    })
  })

  it('「プロジェクトへ戻る」ボタンでプロジェクト画面に遷移する', async () => {
    const user = userEvent.setup()
    renderProjectRulesPage()

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: 'プロジェクトへ戻る' })
      ).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: 'プロジェクトへ戻る' }))

    await waitFor(() => {
      expect(screen.getByTestId('project-page')).toBeInTheDocument()
    })
  })
})
