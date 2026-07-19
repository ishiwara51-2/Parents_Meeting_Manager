/**
 * ProjectNewPage のテスト
 * Phase 4.2 - TDD RED フェーズ
 */

import { render, screen, waitFor, within } from '@testing-library/react'
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
  rulesApi: {
    getGlobal: vi.fn(),
    putProject: vi.fn(),
  },
}))

const MOCK_RULES = {
  global_constraints: {
    max_consecutive_slots: 3,
    forced_break_slots: 1,
    max_slots_per_day: 20,
    teacher_unavailable: [],
  },
  student_constraints: [],
}

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
    vi.mocked(api.rulesApi.getGlobal).mockResolvedValue(MOCK_RULES)
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

    // 候補日をカレンダーから選択（任意の日付）
    await waitFor(() => {
      expect(screen.getByTestId('candidate-dates-calendar')).toBeInTheDocument()
    })
    const anyDayButton = screen
      .getAllByTestId(/^calendar-day-/)
      .find((el) => !el.hasAttribute('disabled'))
    expect(anyDayButton).toBeDefined()
    await user.click(anyDayButton!)

    // 出席番号（開始・終了番号で連番指定）
    await user.type(screen.getByLabelText('開始番号'), '1')
    await user.type(screen.getByLabelText('終了番号'), '3')

    // グローバルルールの読み込み完了を待つ
    await screen.findByLabelText('最大連続コマ数')

    // 作成ボタンをクリック
    const submitButton = screen.getByRole('button', { name: '作成' })
    await user.click(submitButton)

    // プロジェクト画面に遷移していることを確認
    await waitFor(() => {
      expect(screen.getByTestId('project-page')).toBeInTheDocument()
    })

    // 作成時のルール設定（グローバルルール初期値）がプロジェクトに保存されている
    expect(api.rulesApi.putProject).toHaveBeenCalledWith(
      'new-project-id',
      MOCK_RULES,
    )
  })

  it('作成時にルール設定（連続コマ数など）を変更できる', async () => {
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

    await user.type(screen.getByLabelText(/プロジェクト名/), 'テスト面談')

    await waitFor(() => {
      expect(screen.getByTestId('candidate-dates-calendar')).toBeInTheDocument()
    })
    const anyDayButton = screen
      .getAllByTestId(/^calendar-day-/)
      .find((el) => !el.hasAttribute('disabled'))
    await user.click(anyDayButton!)

    await user.type(screen.getByLabelText('開始番号'), '1')
    await user.type(screen.getByLabelText('終了番号'), '3')

    const maxConsecutiveInput = await screen.findByLabelText('最大連続コマ数')
    await user.clear(maxConsecutiveInput)
    await user.type(maxConsecutiveInput, '5')

    await user.click(screen.getByRole('button', { name: '作成' }))

    await waitFor(() => {
      expect(screen.getByTestId('project-page')).toBeInTheDocument()
    })

    expect(api.rulesApi.putProject).toHaveBeenCalledWith('new-project-id', {
      ...MOCK_RULES,
      global_constraints: {
        ...MOCK_RULES.global_constraints,
        max_consecutive_slots: 5,
      },
    })
  })

  it('カレンダーから日付をクリックで選択／解除できる', async () => {
    const user = userEvent.setup()
    renderWithProviders(<ProjectNewPage />)

    const calendar = screen.getByTestId('candidate-dates-calendar')
    expect(calendar).toBeInTheDocument()

    const anyDay = screen
      .getAllByTestId(/^calendar-day-/)
      .find((el) => !el.hasAttribute('disabled'))!
    const ymd = anyDay.getAttribute('data-testid')!.replace('calendar-day-', '')

    // 1 度クリックで選択（チップが表示される）
    await user.click(anyDay)
    expect(screen.getByTestId('selected-dates-list')).toHaveTextContent(ymd)

    // もう一度クリックで解除
    await user.click(anyDay)
    expect(screen.queryByTestId('selected-dates-list')).not.toBeInTheDocument()
  })

  it('候補日が未選択でサブミットするとカレンダー指示のエラーを表示する', async () => {
    const user = userEvent.setup()
    renderWithProviders(<ProjectNewPage />)

    // プロジェクト名は入力するが、候補日は未選択
    await user.type(screen.getByLabelText(/プロジェクト名/), 'テスト')
    await user.click(screen.getByRole('button', { name: '作成' }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(
        /カレンダーから.*選択/,
      )
    })
  })

  it('開始番号と終了番号を入力すると連番の出席番号が生成される', async () => {
    const user = userEvent.setup()
    renderWithProviders(<ProjectNewPage />)

    await user.type(screen.getByLabelText('開始番号'), '3')
    await user.type(screen.getByLabelText('終了番号'), '6')

    const preview = await screen.findByTestId('range-numbers-preview')
    expect(preview).toHaveTextContent('生成される出席番号（4 名）')
    for (const n of ['3', '4', '5', '6']) {
      expect(within(preview).getByText(n)).toBeInTheDocument()
    }
  })

  it('終了番号が開始番号より小さいと警告を表示する', async () => {
    const user = userEvent.setup()
    renderWithProviders(<ProjectNewPage />)

    await user.type(screen.getByLabelText('開始番号'), '5')
    await user.type(screen.getByLabelText('終了番号'), '2')

    await waitFor(() => {
      expect(
        screen.getByText(/終了番号は開始番号以上の値にしてください/),
      ).toBeInTheDocument()
    })
  })

  it('連番指定で開始・終了番号が未入力のままサブミットするとエラーを表示する', async () => {
    const user = userEvent.setup()
    renderWithProviders(<ProjectNewPage />)

    await user.type(screen.getByLabelText(/プロジェクト名/), 'テスト')
    await user.click(screen.getByRole('button', { name: '作成' }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(
        /開始番号と終了番号を入力してください/,
      )
    })
  })

  it('「個別に入力」に切り替えるとカンマ区切りテキストで出席番号を指定できる', async () => {
    const user = userEvent.setup()
    renderWithProviders(<ProjectNewPage />)

    await user.click(screen.getByRole('button', { name: '個別に入力' }))
    const textarea = screen.getByLabelText('出席番号一覧')
    await user.type(textarea, '1, 2, 3')

    await waitFor(() => {
      expect(screen.getByText('認識した出席番号')).toBeInTheDocument()
    })
  })

  it('「次の月」ボタンで翌月へ移動する', async () => {
    const user = userEvent.setup()
    renderWithProviders(<ProjectNewPage />)

    const before = screen
      .getByTestId('candidate-dates-calendar')
      .textContent?.match(/(\d{4})年 ?(\d+)月/)
    expect(before).not.toBeNull()
    const [, yStr, mStr] = before!
    const beforeYear = Number(yStr)
    const beforeMonth = Number(mStr)

    await user.click(screen.getByTestId('calendar-next-month'))

    const after = screen
      .getByTestId('candidate-dates-calendar')
      .textContent?.match(/(\d{4})年 ?(\d+)月/)
    const [, yStr2, mStr2] = after!
    const afterYear = Number(yStr2)
    const afterMonth = Number(mStr2)

    // 12月の翌は翌年1月
    if (beforeMonth === 12) {
      expect(afterYear).toBe(beforeYear + 1)
      expect(afterMonth).toBe(1)
    } else {
      expect(afterYear).toBe(beforeYear)
      expect(afterMonth).toBe(beforeMonth + 1)
    }
  })
})
