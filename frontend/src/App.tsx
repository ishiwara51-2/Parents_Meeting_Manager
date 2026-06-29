/**
 * アプリケーションルート
 * requirements.md §4.1 画面遷移に従ったルーティング骨格
 *
 * 各画面の実装は後続フェーズで行う:
 *   Phase 4.2: HomePage, ProjectNewPage, GlobalRulesPage
 *   Phase 4.3: ProjectPage, ProjectRulesPage
 *   Phase 4.4a-c: SchedulePage, SavedPage
 */

import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import HomePage from './pages/HomePage'
import ProjectNewPage from './pages/ProjectNewPage'
import ProjectPage from './pages/ProjectPage'
import ProjectRulesPage from './pages/ProjectRulesPage'
import GlobalRulesPage from './pages/GlobalRulesPage'
import SchedulePage from './pages/SchedulePage'
import SavedPage from './pages/SavedPage'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
    },
  },
})

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          {/* ホーム画面 */}
          <Route path="/" element={<HomePage />} />

          {/* プロジェクト新規作成 */}
          <Route path="/projects/new" element={<ProjectNewPage />} />

          {/* プロジェクト詳細 */}
          <Route path="/projects/:projectId" element={<ProjectPage />} />

          {/* プロジェクトルール設定 */}
          <Route
            path="/projects/:projectId/rules"
            element={<ProjectRulesPage />}
          />

          {/* 日程案表示 */}
          <Route
            path="/projects/:projectId/schedule"
            element={<SchedulePage />}
          />

          {/* 保存完了 */}
          <Route
            path="/projects/:projectId/saved"
            element={<SavedPage />}
          />

          {/* グローバルルール設定 */}
          <Route path="/global-rules" element={<GlobalRulesPage />} />

          {/* 未知パスはホームへリダイレクト */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

export default App
