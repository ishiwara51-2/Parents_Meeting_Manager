/**
 * ホーム画面
 * requirements.md §4.2
 * - 面談調整開始（新規プロジェクト作成）
 * - 過去プロジェクト一覧（作成日時降順、ステータス表示）
 * - ルール設定ボタン
 * - 認証状態表示
 */

import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { authApi, projectsApi } from '../api'
import type { ProjectStatus } from '../api'

/** ステータス日本語表示 */
const STATUS_LABEL: Record<ProjectStatus, string> = {
  in_progress: '進行中',
  draft_saved: 'ドラフト保存済',
  finalized: '確定済',
}

export default function HomePage() {
  const navigate = useNavigate()

  const { data: authStatus, isLoading: authLoading } = useQuery({
    queryKey: ['auth-status'],
    queryFn: authApi.status,
  })

  const { data: projects = [], isLoading: projectsLoading } = useQuery({
    queryKey: ['projects'],
    queryFn: projectsApi.list,
  })

  return (
    <div className="container">
      <h1>保護者面談調整ツール</h1>

      {/* 認証状態 */}
      <section aria-label="認証状態" style={{ marginBottom: '1rem' }}>
        {authLoading ? (
          <p>認証状態確認中...</p>
        ) : authStatus?.authenticated ? (
          <p>ログイン済み: {authStatus.email}</p>
        ) : (
          <p>
            <button onClick={() => authApi.startGoogle()}>
              Googleでログイン
            </button>
          </p>
        )}
      </section>

      {/* 操作ボタン */}
      <section style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem' }}>
        <button onClick={() => navigate('/projects/new')}>面談調整開始</button>
        <button onClick={() => navigate('/global-rules')}>ルール設定</button>
      </section>

      {/* プロジェクト一覧 */}
      <section>
        <h2>過去のプロジェクト</h2>
        {projectsLoading ? (
          <p>読み込み中...</p>
        ) : projects.length === 0 ? (
          <p>プロジェクトがありません。「面談調整開始」から新規作成してください。</p>
        ) : (
          <ul data-testid="project-list" style={{ listStyle: 'none', padding: 0 }}>
            {projects.map((project) => (
              <li
                key={project.project_id}
                onClick={() => navigate(`/projects/${project.project_id}`)}
                style={{
                  padding: '0.75rem',
                  marginBottom: '0.5rem',
                  border: '1px solid #ccc',
                  borderRadius: '4px',
                  cursor: 'pointer',
                }}
              >
                <strong>{project.display_name}</strong>
                <span style={{ marginLeft: '1rem', color: '#666' }}>
                  {STATUS_LABEL[project.status] ?? project.status}
                </span>
                <span style={{ marginLeft: '1rem', fontSize: '0.875rem', color: '#999' }}>
                  {new Date(project.created_at).toLocaleDateString('ja-JP')}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
