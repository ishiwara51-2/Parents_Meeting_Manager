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
  authApi: {
    status: vi.fn(),
    startGoogle: vi.fn(),
    logout: vi.fn(),
  },
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
    vi.mocked(api.authApi.status).mockResolvedValue({ authenticated: false })
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

describe('ProjectRulesPage 生徒別ルール', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api.authApi.status).mockResolvedValue({ authenticated: false } as never)
    vi.mocked(api.rulesApi.getProject).mockResolvedValue(DEFAULT_RULES as never)
    vi.mocked(api.rulesApi.putProject).mockResolvedValue(DEFAULT_RULES as never)
  })

  it('行を追加して入力し、保存すると prefer_date_range として送信される', async () => {
    const user = userEvent.setup()
    renderProjectRulesPage()
    await user.click(await screen.findByRole('button', { name: /生徒別ルールを追加/ }))
    await user.type(screen.getByLabelText('1行目 生徒番号（カンマ区切り）'), '3, 8')
    expect(screen.getByLabelText('1行目 ルール')).toHaveDisplayValue(
      '詳細設定で指定した期間の日にちに優先的に割り当てる',
    )
    await user.type(screen.getByLabelText('1行目 優先期間の開始日'), '2026-07-15')
    await user.type(screen.getByLabelText('1行目 優先期間の終了日'), '2026-07-16')
    await user.click(screen.getByRole('button', { name: '保存' }))

    await waitFor(() => expect(api.rulesApi.putProject).toHaveBeenCalled())
    const sent = vi.mocked(api.rulesApi.putProject).mock.calls[0][1]
    expect(sent.student_constraints).toEqual([
      {
        type: 'prefer_date_range',
        student_numbers: [3, 8],
        date_from: '2026-07-15',
        date_to: '2026-07-16',
        weight: 5,
      },
    ])
  })

  it('入力不備があるときは保存せずエラーを表示する', async () => {
    const user = userEvent.setup()
    renderProjectRulesPage()
    await user.click(await screen.findByRole('button', { name: /生徒別ルールを追加/ }))
    await user.click(screen.getByRole('button', { name: '保存' }))
    expect(await screen.findByText('生徒番号を入力してください')).toBeInTheDocument()
    expect(api.rulesApi.putProject).not.toHaveBeenCalled()
  })
})
