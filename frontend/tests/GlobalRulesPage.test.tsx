/**
 * GlobalRulesPage のテスト
 * Phase 4.2 - TDD RED フェーズ
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import type { ReactElement } from 'react'
import GlobalRulesPage from '../src/pages/GlobalRulesPage'
import * as api from '../src/api'

const DEFAULT_RULES = {
  global_constraints: {
    max_consecutive_slots: 4,
    forced_break_slots: 1,
    max_slots_per_day: 20,
    teacher_unavailable: [],
  },
  student_constraints: [],
}

vi.mock('../src/api', () => ({
  rulesApi: {
    getGlobal: vi.fn(),
    putGlobal: vi.fn(),
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

describe('GlobalRulesPage', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.mocked(api.rulesApi.getGlobal).mockResolvedValue(DEFAULT_RULES)
    vi.mocked(api.rulesApi.putGlobal).mockResolvedValue(DEFAULT_RULES)
  })

  it('ルール設定フォームが表示される', async () => {
    renderWithProviders(<GlobalRulesPage />)

    // フォームが読み込み完了するまで待つ
    await waitFor(() => {
      expect(screen.getByLabelText(/最大連続コマ数/)).toBeInTheDocument()
    })
  })

  it('保存ボタンが存在する', async () => {
    renderWithProviders(<GlobalRulesPage />)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: '保存' })).toBeInTheDocument()
    })
  })

  it('保存成功時にメッセージを表示する', async () => {
    const user = userEvent.setup()
    renderWithProviders(<GlobalRulesPage />)

    // フォームが読み込まれるまで待つ
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '保存' })).toBeInTheDocument()
    })

    const saveButton = screen.getByRole('button', { name: '保存' })
    await user.click(saveButton)

    await waitFor(() => {
      expect(screen.getByRole('status')).toBeInTheDocument()
    })
  })
})
