/**
 * ProjectPage のテスト
 * Phase 4.3 - TDD RED フェーズ
 *
 * テスト対象: requirements.md §4.3
 *   - プロジェクトメタ情報表示
 *   - Google Form 作成 / URL コピー
 *   - 受領状況表示
 *   - 手動ポーリング（最新回答を取得ボタン）
 *   - 自動ポーリング（60秒間隔 setInterval）
 *   - ルールカスタマイズ / 面談日程案作成ボタン
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import ProjectPage from '../src/pages/ProjectPage'
import * as api from '../src/api'

vi.mock('../src/api', () => ({
  projectsApi: {
    get: vi.fn(),
  },
  formApi: {
    create: vi.fn(),
    get: vi.fn(),
  },
  responsesApi: {
    sync: vi.fn(),
    status: vi.fn(),
    list: vi.fn(),
  },
}))

const PROJECT_ID = 'test-project-id'

const MOCK_PROJECT = {
  project_id: PROJECT_ID,
  display_name: '3年A組 7月面談',
  created_at: '2026-07-01T10:00:00+09:00',
  status: 'in_progress' as const,
  slot_minutes: 20,
  candidate_dates: ['2026-07-15', '2026-07-16'],
  candidate_time_slots: [
    { start: '16:00', end: '16:20' },
    { start: '16:20', end: '16:40' },
  ],
  student_numbers: [1, 2, 3, 4, 5],
}

const MOCK_FORM_INFO = {
  formId: 'FAKE_FORM_ID',
  responderUri: 'https://docs.google.com/forms/d/FAKE_FORM_ID/viewform',
  editUri: 'https://docs.google.com/forms/d/FAKE_FORM_ID/edit',
  student_number_question_id: 'QID_SN',
  row_question_id_by_date: { '2026-07-15': 'QID_ROW_0' },
  time_slot_labels: ['16:00-16:20', '16:20-16:40'],
}

const MOCK_STATUS = {
  project_id: PROJECT_ID,
  received: [1, 2],
  pending: [3, 4, 5],
}

const MOCK_RESPONSES = [
  {
    project_id: PROJECT_ID,
    student_number: 1,
    submitted_at: '2026-07-01T00:00:00+09:00',
    google_form_response_id: 'abc1',
    availability: [{ date: '2026-07-15', start: '16:00', end: '16:20' }],
  },
  {
    project_id: PROJECT_ID,
    student_number: 2,
    submitted_at: '2026-07-01T00:00:00+09:00',
    google_form_response_id: 'abc2',
    availability: [{ date: '2026-07-15', start: '16:00', end: '16:20' }],
  },
]

/** projectId パラメータ付きルートで ProjectPage をレンダリングするヘルパー */
function renderProjectPage(projectId = PROJECT_ID) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/projects/${projectId}`]}>
        <Routes>
          <Route path="/projects/:projectId" element={<ProjectPage />} />
          <Route
            path="/projects/:projectId/rules"
            element={<div data-testid="rules-page">ルール設定</div>}
          />
          <Route
            path="/projects/:projectId/schedule"
            element={<div data-testid="schedule-page">日程案</div>}
          />
          <Route
            path="/"
            element={<div data-testid="home-page">ホーム</div>}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('ProjectPage', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.mocked(api.projectsApi.get).mockResolvedValue(MOCK_PROJECT)
    // Form未作成の場合は 404 相当のエラーを返す
    vi.mocked(api.formApi.get).mockRejectedValue(
      Object.assign(new Error('Not Found'), { status: 404 })
    )
    vi.mocked(api.responsesApi.status).mockResolvedValue(MOCK_STATUS)
    vi.mocked(api.responsesApi.sync).mockResolvedValue(undefined)
    vi.mocked(api.responsesApi.list).mockResolvedValue(MOCK_RESPONSES)
  })

  it('プロジェクトのdisplay_nameが表示される', async () => {
    renderProjectPage()
    await waitFor(() => {
      expect(screen.getByText('3年A組 7月面談')).toBeInTheDocument()
    })
  })

  it('Form未作成時にForm作成ボタンが表示される', async () => {
    renderProjectPage()
    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: /候補日程聴取用Google Form作成/ })
      ).toBeInTheDocument()
    })
  })

  it('Form作成ボタンクリックでformApi.createを呼び出す', async () => {
    const user = userEvent.setup()
    vi.mocked(api.formApi.create).mockResolvedValue(MOCK_FORM_INFO)
    renderProjectPage()

    const btn = await screen.findByRole('button', {
      name: /候補日程聴取用Google Form作成/,
    })
    await user.click(btn)

    expect(vi.mocked(api.formApi.create)).toHaveBeenCalledWith(PROJECT_ID)
  })

  it('Form作成済み時にForm URLが表示される', async () => {
    vi.mocked(api.formApi.get).mockResolvedValue(MOCK_FORM_INFO)
    renderProjectPage()

    await waitFor(() => {
      expect(screen.getByText(/FAKE_FORM_ID\/viewform/)).toBeInTheDocument()
    })
  })

  it('Form作成済み時にURLコピーボタンが表示される', async () => {
    vi.mocked(api.formApi.get).mockResolvedValue(MOCK_FORM_INFO)
    renderProjectPage()

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: /URLをコピー/ })
      ).toBeInTheDocument()
    })
  })

  it('受領済み見出しが表示される', async () => {
    renderProjectPage()
    await waitFor(() => {
      expect(screen.getByText(/受領済み/)).toBeInTheDocument()
    })
  })

  it('未受領見出しが表示される', async () => {
    renderProjectPage()
    await waitFor(() => {
      expect(screen.getByText(/未受領/)).toBeInTheDocument()
    })
  })

  it('最新回答を取得ボタンが存在する', async () => {
    renderProjectPage()
    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: '最新回答を取得' })
      ).toBeInTheDocument()
    })
  })

  it('最新回答を取得ボタンクリックでresponsesApi.syncを呼び出す', async () => {
    const user = userEvent.setup()
    renderProjectPage()

    const btn = await screen.findByRole('button', { name: '最新回答を取得' })
    await user.click(btn)

    expect(vi.mocked(api.responsesApi.sync)).toHaveBeenCalledWith(PROJECT_ID)
  })

  it('ルールカスタマイズボタンが存在する', async () => {
    renderProjectPage()
    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: 'ルールカスタマイズ' })
      ).toBeInTheDocument()
    })
  })

  it('面談日程案作成ボタンが存在する', async () => {
    renderProjectPage()
    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: '面談日程案作成' })
      ).toBeInTheDocument()
    })
  })

  it('マウント時にsetIntervalで60秒ポーリングが設定される', () => {
    const spy = vi.spyOn(window, 'setInterval')
    renderProjectPage()
    expect(spy).toHaveBeenCalledWith(expect.any(Function), 60_000)
    spy.mockRestore()
  })

  describe('ステッパーのアクティブノードクリック', () => {
    it('Form未作成時、ステッパーの「Form作成」ノードをクリックするとForm作成セクションへスクロールする', async () => {
      const user = userEvent.setup()
      const scrollIntoViewMock = vi.fn()
      Element.prototype.scrollIntoView = scrollIntoViewMock
      renderProjectPage()

      const stepper = await screen.findByRole('list', { name: '進捗ステップ' })
      const stepNode = within(stepper).getByRole('button', {
        name: /Form作成/,
      })
      await user.click(stepNode)

      expect(scrollIntoViewMock).toHaveBeenCalled()
    })

    it('ドラフト保存済み時、ステッパーの「確認・修正」ノードをクリックすると日程案画面へ遷移する', async () => {
      const user = userEvent.setup()
      vi.mocked(api.projectsApi.get).mockResolvedValue({
        ...MOCK_PROJECT,
        status: 'draft_saved',
      })
      vi.mocked(api.formApi.get).mockResolvedValue(MOCK_FORM_INFO)
      vi.mocked(api.responsesApi.status).mockResolvedValue({
        project_id: PROJECT_ID,
        received: [1, 2, 3, 4, 5],
        pending: [],
      })
      renderProjectPage()

      const stepper = await screen.findByRole('list', { name: '進捗ステップ' })
      const stepNode = within(stepper).getByRole('button', {
        name: /確認・修正/,
      })
      await user.click(stepNode)

      await waitFor(() => {
        expect(screen.getByTestId('schedule-page')).toBeInTheDocument()
      })
    })

    it('未完了のステップノードはボタンとしてクリックできない', async () => {
      renderProjectPage()
      const stepper = await screen.findByRole('list', { name: '進捗ステップ' })

      // 「回答収集」(pending) はクリック不可のため button role を持たない
      expect(
        within(stepper).queryByRole('button', { name: /回答収集/ }),
      ).not.toBeInTheDocument()
    })
  })

  describe('生徒コメント一覧', () => {
    it('コメントが記入された回答は出席番号とともに一覧表示される', async () => {
      vi.mocked(api.responsesApi.list).mockResolvedValue([
        { ...MOCK_RESPONSES[0], comment: '第二子の面談と続けてお願いしたいです' },
        MOCK_RESPONSES[1],
      ])
      renderProjectPage()

      await waitFor(() => {
        expect(screen.getByTestId('student-comments')).toBeInTheDocument()
      })
      const list = screen.getByTestId('student-comments')
      expect(list).toHaveTextContent('出席番号 1')
      expect(list).toHaveTextContent('第二子の面談と続けてお願いしたいです')
    })

    it('コメントが無い回答は一覧に「コメントはありません」と表示される', async () => {
      renderProjectPage()

      await waitFor(() => {
        expect(screen.getByText('コメントはありません。')).toBeInTheDocument()
      })
      expect(screen.queryByTestId('student-comments')).not.toBeInTheDocument()
    })
  })
})
