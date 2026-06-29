/**
 * SchedulePage のテスト
 * Phase 4.4a - TDD RED フェーズ
 *
 * テスト対象: requirements.md §4.7
 *   - 日付×時間枠マトリクス表示
 *   - スケジューリングAPI のモック呼び出し
 *   - 解なし時の違反制約・未配置リスト表示
 */

import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import SchedulePage from '../src/pages/SchedulePage'
import * as api from '../src/api'

vi.mock('../src/api', () => ({
  scheduleApi: {
    run: vi.fn(),
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

describe('SchedulePage', () => {
  beforeEach(() => {
    vi.resetAllMocks()
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
      // 16:00 が含まれる時間枠ラベルが表示される
      expect(screen.getByText(/16:00/)).toBeInTheDocument()
      // 16:20 が含まれる時間枠ラベルが表示される
      expect(screen.getByText(/16:20/)).toBeInTheDocument()
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
