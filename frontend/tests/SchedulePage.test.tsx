/**
 * SchedulePage のテスト
 * Phase 4.4a - TDD RED フェーズ: マトリクス表示・解なし表示
 * Phase 4.4b - TDD RED フェーズ: DnD と警告ダイアログ
 *
 * テスト対象: requirements.md §4.7
 *   - 日付×時間枠マトリクス表示
 *   - スケジューリングAPI のモック呼び出し
 *   - 解なし時の違反制約・未配置リスト表示
 *   - ドラッグ&ドロップで入れ替え（Phase 4.4b）
 *   - 候補日時外移動の警告ダイアログ（Phase 4.4b）
 */

import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import SchedulePage, {
  applyDrop,
  isInAvailability,
  validateAssignments,
  WarningDialog,
} from '../src/pages/SchedulePage'
import * as api from '../src/api'
import type { Project } from '../src/api/types'

vi.mock('../src/api', () => ({
  scheduleApi: {
    run: vi.fn(),
  },
  projectsApi: {
    get: vi.fn(),
  },
  responsesApi: {
    list: vi.fn(),
  },
  draftsApi: {
    save: vi.fn(),
    getLatest: vi.fn(),
    unlock: vi.fn(),
  },
}))

/** 「既存ドラフトなし」を表すためのエラー（status=404 を持つ） */
const NO_DRAFT_ERROR = Object.assign(new Error('not found'), { status: 404 })

const PROJECT_ID = 'test-project-id'

const MOCK_RESULT_FEASIBLE = {
  assignments: [
    { student_number: 1, date: '2026-07-15', start: '16:00:00', end: '16:20:00' },
    { student_number: 2, date: '2026-07-15', start: '16:20:00', end: '16:40:00' },
    { student_number: 3, date: '2026-07-16', start: '16:00:00', end: '16:20:00' },
  ],
  unassigned_students: [],
  violated_constraints: [],
}

const MOCK_RESULT_INFEASIBLE = {
  assignments: [
    { student_number: 1, date: '2026-07-15', start: '16:00:00', end: '16:20:00' },
  ],
  unassigned_students: [2, 3],
  violated_constraints: [
    '候補日時の制約により開始可能スロットが無い（生徒 2）',
    '他生徒とのスロット競合により配置できない（生徒 3）',
  ],
}

// Phase 4.4b: モックデータ
const MOCK_PROJECT: Project = {
  project_id: 'test-project-id',
  display_name: 'Test Project',
  created_at: '2026-07-01T00:00:00+09:00',
  status: 'in_progress',
  slot_minutes: 20,
  candidate_dates: ['2026-07-15', '2026-07-16'],
  candidate_time_slots: [
    { start: '16:00', end: '16:20' },
    { start: '16:20', end: '16:40' },
  ],
  student_numbers: [1, 2, 3],
}

const MOCK_RESPONSES = [
  {
    project_id: 'test-project-id',
    student_number: 1,
    submitted_at: '2026-07-01T00:00:00+09:00',
    google_form_response_id: 'abc1',
    availability: [
      { date: '2026-07-15', start: '16:00', end: '16:20' },
      { date: '2026-07-15', start: '16:20', end: '16:40' },
      // 2026-07-16 は候補外
    ],
  },
  {
    project_id: 'test-project-id',
    student_number: 2,
    submitted_at: '2026-07-01T00:00:00+09:00',
    google_form_response_id: 'abc2',
    availability: [
      { date: '2026-07-15', start: '16:00', end: '16:20' },
      { date: '2026-07-15', start: '16:20', end: '16:40' },
      { date: '2026-07-16', start: '16:00', end: '16:20' },
    ],
  },
  {
    project_id: 'test-project-id',
    student_number: 3,
    submitted_at: '2026-07-01T00:00:00+09:00',
    google_form_response_id: 'abc3',
    availability: [
      { date: '2026-07-16', start: '16:00', end: '16:20' },
    ],
  },
]

/** projectId パラメータ付きルートで SchedulePage をレンダリングするヘルパー */
function renderSchedulePage(projectId = PROJECT_ID) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/projects/${projectId}/schedule`]}>
        <Routes>
          <Route path="/projects/:projectId/schedule" element={<SchedulePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

// ===== Phase 4.4a テスト（既存）=====

describe('SchedulePage', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    // Phase 4.4b で追加された API呼び出しのデフォルトモック
    vi.mocked(api.projectsApi.get).mockResolvedValue(MOCK_PROJECT)
    vi.mocked(api.responsesApi.list).mockResolvedValue(MOCK_RESPONSES)
    // 既定では既存ドラフトなし（404）
    vi.mocked(api.draftsApi.getLatest).mockRejectedValue(NO_DRAFT_ERROR)
  })

  it('マウント時に scheduleApi.run が正しい projectId で呼ばれる', async () => {
    vi.mocked(api.scheduleApi.run).mockResolvedValue(MOCK_RESULT_FEASIBLE)
    renderSchedulePage()
    await waitFor(() => {
      expect(vi.mocked(api.scheduleApi.run)).toHaveBeenCalledWith(PROJECT_ID)
    })
  })

  it('日付がマトリクスのヘッダとして表示される', async () => {
    vi.mocked(api.scheduleApi.run).mockResolvedValue(MOCK_RESULT_FEASIBLE)
    renderSchedulePage()
    await waitFor(() => {
      // 日程案マトリクスと候補日時集計マトリクスの両方に出現するため getAllByText で確認
      expect(screen.getAllByText('2026-07-15').length).toBeGreaterThan(0)
      expect(screen.getAllByText('2026-07-16').length).toBeGreaterThan(0)
    })
  })

  it('時間枠が行ヘッダとして表示される', async () => {
    vi.mocked(api.scheduleApi.run).mockResolvedValue(MOCK_RESULT_FEASIBLE)
    renderSchedulePage()
    await waitFor(() => {
      // 2 つのマトリクスに同じ時間枠ラベルが出現
      expect(screen.getAllByText(/16:00/).length).toBeGreaterThan(0)
      expect(screen.getAllByText(/16:40/).length).toBeGreaterThan(0)
    })
  })

  it('出席番号がセルに表示される', async () => {
    vi.mocked(api.scheduleApi.run).mockResolvedValue(MOCK_RESULT_FEASIBLE)
    renderSchedulePage()
    await waitFor(() => {
      // 各 student_number がテーブルセルとして表示される
      expect(screen.getAllByText('1').length).toBeGreaterThan(0)
      expect(screen.getAllByText('2').length).toBeGreaterThan(0)
      expect(screen.getAllByText('3').length).toBeGreaterThan(0)
    })
  })

  it('解なし時に違反制約リストが表示される', async () => {
    vi.mocked(api.scheduleApi.run).mockResolvedValue(MOCK_RESULT_INFEASIBLE)
    renderSchedulePage()
    await waitFor(() => {
      // 「違反」または「制約」という文言が画面上部に表示される
      expect(screen.getByText(/違反/)).toBeInTheDocument()
      // 違反制約の内容が表示される
      expect(screen.getByText(/開始可能スロットが無い/)).toBeInTheDocument()
    })
  })

  it('解なし時に未配置生徒リストが表示される', async () => {
    vi.mocked(api.scheduleApi.run).mockResolvedValue(MOCK_RESULT_INFEASIBLE)
    renderSchedulePage()
    await waitFor(() => {
      // 「未配置」という文言は alert 領域に 1 件だけ存在する
      const alert = screen.getByRole('alert')
      expect(alert).toHaveTextContent(/未配置/)
      expect(alert).toHaveTextContent(/2.*3|3.*2/)
    })
  })
})

// ===== Phase 4.4b テスト: DnD と警告 =====

describe('Phase 4.4b: DnD と警告', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.mocked(api.scheduleApi.run).mockResolvedValue(MOCK_RESULT_FEASIBLE)
    vi.mocked(api.projectsApi.get).mockResolvedValue(MOCK_PROJECT)
    vi.mocked(api.responsesApi.list).mockResolvedValue(MOCK_RESPONSES)
    // 既定では既存ドラフトなし（404）
    vi.mocked(api.draftsApi.getLatest).mockRejectedValue(NO_DRAFT_ERROR)
  })

  it('ドラッグ可能な生徒カードが data-testid で識別できる', async () => {
    renderSchedulePage()
    await waitFor(() => {
      // 各生徒番号が draggable-student-N という data-testid で識別できる
      expect(screen.getByTestId('draggable-student-1')).toBeInTheDocument()
      expect(screen.getByTestId('draggable-student-2')).toBeInTheDocument()
      expect(screen.getByTestId('draggable-student-3')).toBeInTheDocument()
    })
  })

  it('applyDrop: 2つの割り当てを入れ替える（スワップ）', () => {
    const assignments = [
      { student_number: 1, date: '2026-07-15', start: '16:00:00', end: '16:20:00' },
      { student_number: 2, date: '2026-07-15', start: '16:20:00', end: '16:40:00' },
    ]
    const result = applyDrop(
      assignments,
      '2026-07-15|16:00',  // from: 生徒1
      '2026-07-15|16:20',  // to: 生徒2
      MOCK_PROJECT.candidate_time_slots
    )
    // スワップ後: スロット位置は固定、生徒番号が入れ替わる
    const slot1 = result.find(a => a.date === '2026-07-15' && a.start.startsWith('16:00'))
    const slot2 = result.find(a => a.date === '2026-07-15' && a.start.startsWith('16:20'))
    expect(slot1?.student_number).toBe(2)
    expect(slot2?.student_number).toBe(1)
  })

  it('isInAvailability: 候補日時外を正しく判定する', () => {
    // 生徒1は 2026-07-16 を候補としていない → false
    expect(isInAvailability(1, '2026-07-16', '16:00', MOCK_RESPONSES)).toBe(false)
    // 生徒1は 2026-07-15 16:00 を候補としている → true
    expect(isInAvailability(1, '2026-07-15', '16:00', MOCK_RESPONSES)).toBe(true)
    // 生徒2は 2026-07-16 16:00 を候補としている → true
    expect(isInAvailability(2, '2026-07-16', '16:00', MOCK_RESPONSES)).toBe(true)
  })

  it('WarningDialog が候補外移動時の情報を表示する', () => {
    render(
      <WarningDialog
        studentNumber={1}
        date="2026-07-16"
        start="16:00"
        onClose={() => {}}
      />
    )
    // 警告ダイアログが表示される
    expect(screen.getByTestId('warning-dialog')).toBeInTheDocument()
    // 生徒番号が含まれる（<strong>1</strong> の exact match）
    expect(screen.getByText('1')).toBeInTheDocument()
    // 日付が含まれる
    expect(screen.getByText(/2026-07-16/)).toBeInTheDocument()
  })
})

// ===== Phase 4.4c テスト: 保存ボタンと SavedPage への遷移 =====

const MOCK_DRAFT = {
  project_id: PROJECT_ID,
  saved_at: '2026-07-15T20:00:00+09:00',
  locked: true,
  assignments: MOCK_RESULT_FEASIBLE.assignments,
  unassigned_students: [],
  violated_constraints: [],
}

describe('Phase 4.4c: 保存ボタン', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.mocked(api.scheduleApi.run).mockResolvedValue(MOCK_RESULT_FEASIBLE)
    vi.mocked(api.projectsApi.get).mockResolvedValue(MOCK_PROJECT)
    vi.mocked(api.responsesApi.list).mockResolvedValue(MOCK_RESPONSES)
    // 既定では既存ドラフトなし（404）
    vi.mocked(api.draftsApi.getLatest).mockRejectedValue(NO_DRAFT_ERROR)
  })

  it('「保存」ボタンが表示される', async () => {
    renderSchedulePage()
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '保存' })).toBeInTheDocument()
    })
  })

  it('「保存」ボタンクリックで draftsApi.save が正しい引数で呼ばれる', async () => {
    vi.mocked(api.draftsApi.save).mockResolvedValue(MOCK_DRAFT)
    renderSchedulePage()
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '保存' })).toBeInTheDocument()
    })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))
    await waitFor(() => {
      expect(vi.mocked(api.draftsApi.save)).toHaveBeenCalledWith(
        PROJECT_ID,
        expect.objectContaining({
          assignments: expect.any(Array),
          unassigned_students: expect.any(Array),
          violated_constraints: expect.any(Array),
        }),
      )
    })
  })

  it('保存成功時に /projects/:projectId/saved へ遷移する', async () => {
    vi.mocked(api.draftsApi.save).mockResolvedValue(MOCK_DRAFT)
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[`/projects/${PROJECT_ID}/schedule`]}>
          <Routes>
            <Route path="/projects/:projectId/schedule" element={<SchedulePage />} />
            <Route path="/projects/:projectId/saved" element={<div>保存完了ページ</div>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    )
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '保存' })).toBeInTheDocument()
    })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))
    await waitFor(() => {
      expect(screen.getByText('保存完了ページ')).toBeInTheDocument()
    })
  })
})

// ===== 既存ドラフトとロックの挙動 =====
//
// ロックは「前回保存済みであること」ではなく「ユーザーがロックボタンで
// 指定したこと」によって決まる（draft.locked_students）。ロックされて
// いない配置は、既存ドラフトに含まれていたかどうかに関わらず、画面を
// 開くたびに毎回自動配置が再計算される。

const EXISTING_DRAFT = {
  project_id: PROJECT_ID,
  saved_at: '2026-07-15T20:00:00+09:00',
  locked: true,
  assignments: [
    { student_number: 1, date: '2026-07-15', start: '16:00:00', end: '16:20:00' },
    { student_number: 2, date: '2026-07-15', start: '16:20:00', end: '16:40:00' },
    { student_number: 3, date: '2026-07-16', start: '16:00:00', end: '16:20:00' },
  ],
  unassigned_students: [],
  violated_constraints: [],
  locked_students: [],
}

describe('既存ドラフトとロックの挙動', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.mocked(api.projectsApi.get).mockResolvedValue(MOCK_PROJECT)
    vi.mocked(api.responsesApi.list).mockResolvedValue(MOCK_RESPONSES)
    vi.mocked(api.scheduleApi.run).mockResolvedValue({
      assignments: [],
      unassigned_students: [],
      violated_constraints: [],
    })
  })

  it('ロック済みの出席番号のみの場合は scheduleApi.run を呼ばずにロック済みの配置を表示', async () => {
    vi.mocked(api.draftsApi.getLatest).mockResolvedValue({
      ...EXISTING_DRAFT,
      locked_students: [1, 2, 3],
    })
    renderSchedulePage()
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '保存' })).toBeInTheDocument()
    })
    // ロック済み以外に自動配置すべき対象がいないので schedule API は呼ばれない
    expect(vi.mocked(api.scheduleApi.run)).not.toHaveBeenCalled()
    // ロック済みの生徒がマトリクスに表示される
    expect(screen.getByTestId('draggable-student-1')).toBeInTheDocument()
    expect(screen.getByTestId('draggable-student-2')).toBeInTheDocument()
    expect(screen.getByTestId('draggable-student-3')).toBeInTheDocument()
  })

  it('ロックされていない出席番号は既存ドラフトに含まれていても毎回再計算される', async () => {
    // locked_students が空の既存ドラフト → 全員が自動配置の対象
    vi.mocked(api.draftsApi.getLatest).mockResolvedValue(EXISTING_DRAFT)
    renderSchedulePage()
    await waitFor(() => {
      expect(vi.mocked(api.scheduleApi.run)).toHaveBeenCalledWith(PROJECT_ID)
    })
  })

  it('ロック済みの出席番号は excluded_students としてスケジュールAPIに渡される', async () => {
    vi.mocked(api.draftsApi.getLatest).mockResolvedValue({
      ...EXISTING_DRAFT,
      locked_students: [1],
    })
    renderSchedulePage()
    await waitFor(() => {
      expect(vi.mocked(api.scheduleApi.run)).toHaveBeenCalled()
    })
    const [, req] = vi.mocked(api.scheduleApi.run).mock.calls[0]
    expect(req).toEqual({ excluded_students: [1] })
  })

  it('保存時に 409 が返ったらアンロックして再保存する', async () => {
    vi.mocked(api.draftsApi.getLatest).mockResolvedValue(EXISTING_DRAFT)
    const lockedError = Object.assign(new Error('locked'), { status: 409 })
    vi.mocked(api.draftsApi.save)
      .mockRejectedValueOnce(lockedError)
      .mockResolvedValueOnce({
        ...EXISTING_DRAFT,
        locked: true,
      })
    vi.mocked(api.draftsApi.unlock).mockResolvedValue({
      ...EXISTING_DRAFT,
      locked: false,
    })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[`/projects/${PROJECT_ID}/schedule`]}>
          <Routes>
            <Route path="/projects/:projectId/schedule" element={<SchedulePage />} />
            <Route path="/projects/:projectId/saved" element={<div>保存完了ページ</div>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '保存' })).toBeInTheDocument()
    })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))
    await waitFor(() => {
      expect(screen.getByText('保存完了ページ')).toBeInTheDocument()
    })
    expect(vi.mocked(api.draftsApi.unlock)).toHaveBeenCalledWith(PROJECT_ID)
    expect(vi.mocked(api.draftsApi.save)).toHaveBeenCalledTimes(2)
  })

  it('保存時に locked_students が含まれる', async () => {
    vi.mocked(api.draftsApi.getLatest).mockResolvedValue({
      ...EXISTING_DRAFT,
      locked_students: [2, 3],
    })
    vi.mocked(api.draftsApi.save).mockResolvedValue(EXISTING_DRAFT)
    renderSchedulePage()
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '保存' })).toBeInTheDocument()
    })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))
    await waitFor(() => {
      expect(vi.mocked(api.draftsApi.save)).toHaveBeenCalledWith(
        PROJECT_ID,
        expect.objectContaining({
          locked_students: expect.arrayContaining([2, 3]),
        }),
      )
    })
  })

  it('ロック中の生徒の最新回答が空になっていたら警告を表示する', async () => {
    // 生徒 1, 2, 3 をロック済みでドラフトから読み込む
    // 生徒 1 の最新回答が空（候補日時ゼロ）になっている
    const responsesWithEmpty1 = [
      {
        project_id: PROJECT_ID,
        student_number: 1,
        submitted_at: '2026-07-02T00:00:00+09:00',
        google_form_response_id: 'r1-new',
        availability: [],
      },
      MOCK_RESPONSES[1],
      MOCK_RESPONSES[2],
    ]
    vi.mocked(api.responsesApi.list).mockResolvedValue(responsesWithEmpty1)
    vi.mocked(api.draftsApi.getLatest).mockResolvedValue({
      ...EXISTING_DRAFT,
      locked_students: [1, 2, 3],
    })

    renderSchedulePage()
    await waitFor(() => {
      expect(screen.getByTestId('availability-issue-alert')).toBeInTheDocument()
    })
    const alert = screen.getByTestId('availability-issue-alert')
    expect(alert).toHaveTextContent(/候補日時がありません/)
    expect(alert).toHaveTextContent(/\b1\b/)
  })

  it('ロックされていない生徒の回答が空でも、毎回再計算されるため警告は出ない', async () => {
    // 生徒 1 の最新回答が空だが、誰もロックしていない場合は
    // 自動配置で未配置（unassigned）として扱われるため、
    // 「配置されたまま矛盾している」警告の対象にはならない
    const responsesWithEmpty1 = [
      {
        project_id: PROJECT_ID,
        student_number: 1,
        submitted_at: '2026-07-02T00:00:00+09:00',
        google_form_response_id: 'r1-new',
        availability: [],
      },
      MOCK_RESPONSES[1],
      MOCK_RESPONSES[2],
    ]
    vi.mocked(api.responsesApi.list).mockResolvedValue(responsesWithEmpty1)
    vi.mocked(api.draftsApi.getLatest).mockResolvedValue(EXISTING_DRAFT)
    vi.mocked(api.scheduleApi.run).mockResolvedValue({
      assignments: [
        { student_number: 2, date: '2026-07-15', start: '16:20:00', end: '16:40:00' },
        { student_number: 3, date: '2026-07-16', start: '16:00:00', end: '16:20:00' },
      ],
      unassigned_students: [1],
      violated_constraints: [],
    })

    renderSchedulePage()
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '保存' })).toBeInTheDocument()
    })
    expect(
      screen.queryByTestId('availability-issue-alert'),
    ).not.toBeInTheDocument()
  })

  it('警告がある場合、「警告対象を再配置する」ボタンが表示される', async () => {
    const responsesWithEmpty1 = [
      {
        project_id: PROJECT_ID,
        student_number: 1,
        submitted_at: '2026-07-02T00:00:00+09:00',
        google_form_response_id: 'r1-new',
        availability: [],
      },
      MOCK_RESPONSES[1],
      MOCK_RESPONSES[2],
    ]
    vi.mocked(api.responsesApi.list).mockResolvedValue(responsesWithEmpty1)
    vi.mocked(api.draftsApi.getLatest).mockResolvedValue({
      ...EXISTING_DRAFT,
      locked_students: [1, 2, 3],
    })

    renderSchedulePage()
    await waitFor(() => {
      expect(
        screen.getByTestId('reorganize-warning-students-button'),
      ).toBeInTheDocument()
    })
  })

  it('警告がない場合、「警告対象を再配置する」ボタンは表示されない', async () => {
    vi.mocked(api.draftsApi.getLatest).mockResolvedValue({
      ...EXISTING_DRAFT,
      locked_students: [1, 2, 3],
    })
    renderSchedulePage()
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '保存' })).toBeInTheDocument()
    })
    expect(
      screen.queryByTestId('reorganize-warning-students-button'),
    ).not.toBeInTheDocument()
  })

  it('「警告対象を再配置する」ボタン押下で警告対象のロックを解除し再計算する', async () => {
    // 生徒 1 の最新回答が空 → 警告対象（1,2,3 は全員ロック済み）
    const responsesWithEmpty1 = [
      {
        project_id: PROJECT_ID,
        student_number: 1,
        submitted_at: '2026-07-02T00:00:00+09:00',
        google_form_response_id: 'r1-new',
        availability: [],
      },
      MOCK_RESPONSES[1],
      MOCK_RESPONSES[2],
    ]
    vi.mocked(api.responsesApi.list).mockResolvedValue(responsesWithEmpty1)
    vi.mocked(api.draftsApi.getLatest).mockResolvedValue({
      ...EXISTING_DRAFT,
      locked_students: [1, 2, 3],
    })
    vi.mocked(api.scheduleApi.run).mockResolvedValue({
      assignments: [],
      unassigned_students: [1],
      violated_constraints: [],
    })

    renderSchedulePage()
    await waitFor(() => {
      expect(
        screen.getByTestId('reorganize-warning-students-button'),
      ).toBeInTheDocument()
    })
    // ロード時点では全員ロック済みのため scheduleApi.run は未呼び出し
    expect(vi.mocked(api.scheduleApi.run)).not.toHaveBeenCalled()

    fireEvent.click(
      screen.getByTestId('reorganize-warning-students-button'),
    )

    await waitFor(() => {
      expect(vi.mocked(api.scheduleApi.run)).toHaveBeenCalled()
    })
    // 警告対象（生徒 1）はロック解除され再計算対象になる
    // それ以外（生徒 2, 3）は引き続きロックされ excluded_students に含まれる
    const [, req] = vi.mocked(api.scheduleApi.run).mock.calls[0]
    expect(req).toEqual({
      excluded_students: expect.arrayContaining([2, 3]),
    })
    expect((req as { excluded_students: number[] }).excluded_students).not.toContain(
      1,
    )
  })

  it('セルのロックボタンでロック状態をトグルできる（cell-locked-* data-testid）', async () => {
    vi.mocked(api.draftsApi.getLatest).mockRejectedValue(NO_DRAFT_ERROR)
    vi.mocked(api.scheduleApi.run).mockResolvedValue(MOCK_RESULT_FEASIBLE)
    renderSchedulePage()
    await waitFor(() => {
      expect(screen.getByTestId('draggable-student-1')).toBeInTheDocument()
    })
    expect(screen.queryByTestId('cell-locked-1')).not.toBeInTheDocument()

    fireEvent.click(screen.getByTestId('cell-lock-button-2026-07-15|16:00'))
    await waitFor(() => {
      expect(screen.getByTestId('cell-locked-1')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByTestId('cell-lock-button-2026-07-15|16:00'))
    await waitFor(() => {
      expect(screen.queryByTestId('cell-locked-1')).not.toBeInTheDocument()
    })
  })

  it('行のロックボタンでその時間枠の全セルを一括ロックできる', async () => {
    vi.mocked(api.draftsApi.getLatest).mockRejectedValue(NO_DRAFT_ERROR)
    vi.mocked(api.scheduleApi.run).mockResolvedValue(MOCK_RESULT_FEASIBLE)
    renderSchedulePage()
    await waitFor(() => {
      expect(screen.getByTestId('draggable-student-1')).toBeInTheDocument()
    })
    // 16:00 の行には生徒 1（07-15）と生徒 3（07-16）が配置されている
    fireEvent.click(screen.getByTestId('row-lock-button-16:00'))
    await waitFor(() => {
      expect(screen.getByTestId('cell-locked-1')).toBeInTheDocument()
    })
    expect(screen.getByTestId('cell-locked-3')).toBeInTheDocument()
    // 16:20 の行（生徒2）はロックされない
    expect(screen.queryByTestId('cell-locked-2')).not.toBeInTheDocument()

    // 再度クリックすると一括解除される（全ロック済みなら解除に切り替わる）
    fireEvent.click(screen.getByTestId('row-lock-button-16:00'))
    await waitFor(() => {
      expect(screen.queryByTestId('cell-locked-1')).not.toBeInTheDocument()
    })
    expect(screen.queryByTestId('cell-locked-3')).not.toBeInTheDocument()
  })

  it('列のロックボタンでその日付の全セルを一括ロックできる', async () => {
    vi.mocked(api.draftsApi.getLatest).mockRejectedValue(NO_DRAFT_ERROR)
    vi.mocked(api.scheduleApi.run).mockResolvedValue(MOCK_RESULT_FEASIBLE)
    renderSchedulePage()
    await waitFor(() => {
      expect(screen.getByTestId('draggable-student-1')).toBeInTheDocument()
    })
    // 2026-07-15 の列には生徒 1, 2 が配置されている
    fireEvent.click(screen.getByTestId('column-lock-button-2026-07-15'))
    await waitFor(() => {
      expect(screen.getByTestId('cell-locked-1')).toBeInTheDocument()
    })
    expect(screen.getByTestId('cell-locked-2')).toBeInTheDocument()
    expect(screen.queryByTestId('cell-locked-3')).not.toBeInTheDocument()
  })

  it('既存ドラフトに含まれる名簿外番号は確認ダイアログから除外される', async () => {
    // 名簿外 (6) と (7) が応答済み、ドラフトには 6 が含まれている → 確認対象は 7 のみ
    const project = { ...MOCK_PROJECT, student_numbers: [1, 2, 3] }
    const responses = [
      ...MOCK_RESPONSES,
      {
        project_id: PROJECT_ID,
        student_number: 6,
        submitted_at: '2026-07-01T00:00:00+09:00',
        google_form_response_id: 'r6',
        availability: [],
      },
      {
        project_id: PROJECT_ID,
        student_number: 7,
        submitted_at: '2026-07-01T00:00:00+09:00',
        google_form_response_id: 'r7',
        availability: [],
      },
    ]
    const draftWith6 = {
      ...EXISTING_DRAFT,
      unassigned_students: [6],
    }
    vi.mocked(api.projectsApi.get).mockResolvedValue(project)
    vi.mocked(api.responsesApi.list).mockResolvedValue(responses)
    vi.mocked(api.draftsApi.getLatest).mockResolvedValue(draftWith6)

    renderSchedulePage()
    await waitFor(() => {
      expect(screen.getByTestId('extras-confirm-dialog')).toBeInTheDocument()
    })
    const dialog = screen.getByTestId('extras-confirm-dialog')
    // 6 は既にドラフトに含まれているため表示されない
    expect(dialog.textContent).not.toMatch(/\b6\b/)
    // 7 は表示される
    expect(dialog.textContent).toMatch(/\b7\b/)
  })
})

// ===== 手動入力と検証エラー =====

describe('validateAssignments', () => {
  it('重複している出席番号を検出する', () => {
    const assignments = [
      { student_number: 1, date: '2026-07-15', start: '16:00:00', end: '16:20:00' },
      { student_number: 1, date: '2026-07-15', start: '16:20:00', end: '16:40:00' },
      { student_number: 2, date: '2026-07-16', start: '16:00:00', end: '16:20:00' },
    ]
    const result = validateAssignments(assignments, [1, 2, 3], [])
    expect(result.duplicates).toEqual([1])
    expect(result.outOfRoster).toEqual([])
  })

  it('名簿外（authorizedExtras にも無い）を検出する', () => {
    const assignments = [
      { student_number: 1, date: '2026-07-15', start: '16:00:00', end: '16:20:00' },
      { student_number: 99, date: '2026-07-15', start: '16:20:00', end: '16:40:00' },
    ]
    const result = validateAssignments(assignments, [1, 2, 3], [])
    expect(result.outOfRoster).toEqual([99])
  })

  it('authorizedExtras に含まれる名簿外番号は警告対象外', () => {
    const assignments = [
      { student_number: 6, date: '2026-07-15', start: '16:00:00', end: '16:20:00' },
    ]
    const result = validateAssignments(assignments, [1, 2, 3], [6])
    expect(result.outOfRoster).toEqual([])
  })

  it('重複と名簿外を同時に検出する', () => {
    const assignments = [
      { student_number: 99, date: '2026-07-15', start: '16:00:00', end: '16:20:00' },
      { student_number: 99, date: '2026-07-15', start: '16:20:00', end: '16:40:00' },
    ]
    const result = validateAssignments(assignments, [1, 2, 3], [])
    expect(result.duplicates).toEqual([99])
    expect(result.outOfRoster).toEqual([99])
  })
})

describe('手動入力 UI', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.mocked(api.scheduleApi.run).mockResolvedValue(MOCK_RESULT_FEASIBLE)
    vi.mocked(api.projectsApi.get).mockResolvedValue(MOCK_PROJECT)
    vi.mocked(api.responsesApi.list).mockResolvedValue(MOCK_RESPONSES)
    vi.mocked(api.draftsApi.getLatest).mockRejectedValue(NO_DRAFT_ERROR)
  })

  it('各セルに編集ボタンが表示される', async () => {
    renderSchedulePage()
    await waitFor(() => {
      // 配置済みセル: ✎ ボタン
      expect(
        screen.getByTestId('cell-edit-button-2026-07-15|16:00'),
      ).toBeInTheDocument()
    })
    // 空きセル: ＋ ボタン
    expect(
      screen.getByTestId('cell-edit-button-2026-07-16|16:20'),
    ).toBeInTheDocument()
  })

  it('編集ボタン押下で入力フィールドが表示され、Enter で値が反映される', async () => {
    renderSchedulePage()
    await waitFor(() => {
      expect(
        screen.getByTestId('cell-edit-button-2026-07-16|16:20'),
      ).toBeInTheDocument()
    })
    fireEvent.click(screen.getByTestId('cell-edit-button-2026-07-16|16:20'))
    const input = (await screen.findByTestId(
      'cell-input-2026-07-16|16:20',
    )) as HTMLInputElement
    fireEvent.change(input, { target: { value: '2' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    fireEvent.blur(input)
    // 配置反映: 生徒 2 が 16:00 と 16:20 の両方に → 重複として検出
    await waitFor(() => {
      expect(screen.getByTestId('validation-alert')).toBeInTheDocument()
    })
  })

  it('名簿外の番号を入力すると validation-alert に表示される', async () => {
    renderSchedulePage()
    await waitFor(() => {
      expect(
        screen.getByTestId('cell-edit-button-2026-07-16|16:20'),
      ).toBeInTheDocument()
    })
    fireEvent.click(screen.getByTestId('cell-edit-button-2026-07-16|16:20'))
    const input = (await screen.findByTestId(
      'cell-input-2026-07-16|16:20',
    )) as HTMLInputElement
    fireEvent.change(input, { target: { value: '99' } })
    fireEvent.blur(input)
    await waitFor(() => {
      const alert = screen.getByTestId('validation-alert')
      expect(alert).toHaveTextContent(/生徒名簿に登録されていません/)
      expect(alert).toHaveTextContent(/99/)
    })
  })

  it('「含める」で認可された名簿外番号は検証エラーにならない', async () => {
    // 名簿外 (6) が応答済み → 確認ダイアログ表示 → 「含める」を選択
    const responses = [
      ...MOCK_RESPONSES,
      {
        project_id: PROJECT_ID,
        student_number: 6,
        submitted_at: '2026-07-01T00:00:00+09:00',
        google_form_response_id: 'r6',
        availability: [
          { date: '2026-07-15', start: '16:00', end: '16:20' },
        ],
      },
    ]
    vi.mocked(api.responsesApi.list).mockResolvedValue(responses)
    vi.mocked(api.scheduleApi.run).mockResolvedValue({
      assignments: [
        { student_number: 6, date: '2026-07-15', start: '16:00:00', end: '16:20:00' },
      ],
      unassigned_students: [],
      violated_constraints: [],
    })
    renderSchedulePage()
    await waitFor(() => {
      expect(screen.getByTestId('extras-confirm-dialog')).toBeInTheDocument()
    })
    fireEvent.click(screen.getByRole('button', { name: '含める' }))
    // スケジュール完了後、検証エラーは表示されない（6 は authorizedExtras）
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '保存' })).toBeInTheDocument()
    })
    expect(screen.queryByTestId('validation-alert')).not.toBeInTheDocument()
  })
})
