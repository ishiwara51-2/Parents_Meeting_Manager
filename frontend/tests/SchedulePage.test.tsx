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
  },
}))

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
      expect(screen.getByText('2026-07-15')).toBeInTheDocument()
      expect(screen.getByText('2026-07-16')).toBeInTheDocument()
    })
  })

  it('時間枠が行ヘッダとして表示される', async () => {
    vi.mocked(api.scheduleApi.run).mockResolvedValue(MOCK_RESULT_FEASIBLE)
    renderSchedulePage()
    await waitFor(() => {
      // "16:00 - 16:20" は "16:00" を含む唯一の行ラベル
      expect(screen.getByText(/16:00/)).toBeInTheDocument()
      // "16:20 - 16:40" は "16:40" を含む唯一の行ラベル（"16:20" は2行にまたがるため16:40で一意を確認）
      expect(screen.getByText(/16:40/)).toBeInTheDocument()
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
      // 「未配置」という文言が表示される
      expect(screen.getByText(/未配置/)).toBeInTheDocument()
      // 未配置生徒の出席番号が表示される（"2, 3" or similar）
      expect(screen.getByText(/2.*3|3.*2/)).toBeInTheDocument()
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
