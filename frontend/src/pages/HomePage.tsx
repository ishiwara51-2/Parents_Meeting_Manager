/**
 * ホーム画面
 * requirements.md §4.2
 * - 面談調整開始（新規プロジェクト作成）
 * - 過去プロジェクト一覧（作成日時降順、ステータス表示）
 * - ルール設定ボタン
 * - 認証状態表示
 * - 各プロジェクトの削除（確認ダイアログ付き）
 */

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { authApi, projectsApi } from '../api'
import type { Project, ProjectStatus } from '../api'

/** ステータス日本語表示 */
const STATUS_LABEL: Record<ProjectStatus, string> = {
  in_progress: '進行中',
  draft_saved: 'ドラフト保存済',
  finalized: '確定済',
}

export default function HomePage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data: authStatus, isLoading: authLoading } = useQuery({
    queryKey: ['auth-status'],
    queryFn: authApi.status,
  })

  const { data: projects = [], isLoading: projectsLoading } = useQuery({
    queryKey: ['projects'],
    queryFn: projectsApi.list,
  })

  const [confirmTarget, setConfirmTarget] = useState<Project | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const deleteMutation = useMutation({
    mutationFn: (id: string) => projectsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      setConfirmTarget(null)
      setDeleteError(null)
    },
    onError: (err: Error) => {
      setDeleteError(err.message ?? '削除に失敗しました')
    },
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
                  display: 'flex',
                  alignItems: 'center',
                  gap: '1rem',
                }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <strong>{project.display_name}</strong>
                  <span style={{ marginLeft: '1rem', color: '#666' }}>
                    {STATUS_LABEL[project.status] ?? project.status}
                  </span>
                  <span
                    style={{
                      marginLeft: '1rem',
                      fontSize: '0.875rem',
                      color: '#999',
                    }}
                  >
                    {new Date(project.created_at).toLocaleDateString('ja-JP')}
                  </span>
                </div>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation()
                    setDeleteError(null)
                    setConfirmTarget(project)
                  }}
                  data-testid={`delete-project-button-${project.project_id}`}
                  aria-label={`「${project.display_name}」を削除`}
                  style={{
                    padding: '0.4rem 0.8rem',
                    backgroundColor: '#fff',
                    color: '#b91c1c',
                    border: '1px solid #b91c1c',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    fontSize: '0.875rem',
                  }}
                >
                  削除
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* 削除確認ダイアログ */}
      {confirmTarget && (
        <div
          role="dialog"
          aria-modal="true"
          data-testid="delete-confirm-dialog"
          style={{
            position: 'fixed',
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
            backgroundColor: '#fff',
            border: '2px solid #b91c1c',
            borderRadius: '8px',
            padding: '24px',
            zIndex: 1000,
            boxShadow: '0 4px 16px rgba(0,0,0,0.25)',
            maxWidth: '480px',
            width: '90%',
          }}
        >
          <h2 style={{ color: '#b91c1c', marginTop: 0, fontSize: '1.1rem' }}>
            ⚠ プロジェクトの削除
          </h2>
          <p style={{ margin: '8px 0' }}>
            「<strong>{confirmTarget.display_name}</strong>」を削除します。
          </p>
          <p style={{ margin: '8px 0', color: '#6b7280', fontSize: '0.9rem' }}>
            この操作は取り消せません。プロジェクトの設定・回答・ドラフトがすべて失われます。
          </p>
          {deleteError != null && (
            <div
              role="alert"
              style={{
                color: '#b91c1c',
                backgroundColor: '#fef2f2',
                border: '1px solid #f87171',
                borderRadius: '4px',
                padding: '6px 10px',
                margin: '8px 0',
                fontSize: '0.9rem',
              }}
            >
              エラー: {deleteError}
            </div>
          )}
          <div style={{ display: 'flex', gap: '8px', marginTop: '16px' }}>
            <button
              type="button"
              onClick={() => deleteMutation.mutate(confirmTarget.project_id)}
              disabled={deleteMutation.isPending}
              data-testid="delete-confirm-button"
              style={{
                padding: '8px 20px',
                cursor: deleteMutation.isPending ? 'not-allowed' : 'pointer',
                backgroundColor: '#b91c1c',
                color: '#fff',
                border: 'none',
                borderRadius: '4px',
                opacity: deleteMutation.isPending ? 0.6 : 1,
              }}
            >
              {deleteMutation.isPending ? '削除中...' : '削除する'}
            </button>
            <button
              type="button"
              onClick={() => {
                setConfirmTarget(null)
                setDeleteError(null)
              }}
              disabled={deleteMutation.isPending}
              data-testid="delete-cancel-button"
              style={{
                padding: '8px 20px',
                cursor: deleteMutation.isPending ? 'not-allowed' : 'pointer',
                backgroundColor: '#fff',
                color: '#374151',
                border: '1px solid #d1d5db',
                borderRadius: '4px',
              }}
            >
              キャンセル
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
