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
import {
  AppShell,
  Alert,
  Badge,
  Button,
  Card,
} from '../components/ui'
import type { BadgeTone } from '../components/ui'

/** ステータス日本語表示 */
const STATUS_LABEL: Record<ProjectStatus, string> = {
  in_progress: '進行中',
  draft_saved: 'ドラフト保存済',
  finalized: '確定済',
}

const STATUS_TONE: Record<ProjectStatus, BadgeTone> = {
  in_progress: 'brand',
  draft_saved: 'warning',
  finalized: 'success',
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

  const headerRight = authLoading ? (
    <span className="text-fg-subtle">認証状態確認中...</span>
  ) : authStatus?.authenticated ? (
    <span className="text-fg-muted">
      <span className="text-fg-subtle">ログイン済み: </span>
      <span className="font-medium text-fg">{authStatus.email}</span>
    </span>
  ) : (
    <Button
      variant="secondary"
      size="sm"
      onClick={() => authApi.startGoogle()}
    >
      Googleでログイン
    </Button>
  )

  return (
    <AppShell
      headerRight={headerRight}
      title="保護者面談調整ツール"
      subtitle="保護者面談の日程を、Google Form を使って効率的に調整します。"
      actions={
        <>
          <Button
            variant="primary"
            size="md"
            onClick={() => navigate('/projects/new')}
          >
            面談調整開始
          </Button>
          <Button
            variant="secondary"
            size="md"
            onClick={() => navigate('/global-rules')}
          >
            ルール設定
          </Button>
        </>
      }
    >
      <section aria-label="過去のプロジェクト">
        <div className="flex items-baseline justify-between mb-3">
          <h2 className="text-base font-semibold text-fg">過去のプロジェクト</h2>
          <span className="text-xs text-fg-subtle">
            {!projectsLoading && projects.length > 0 && `${projects.length} 件`}
          </span>
        </div>

        {projectsLoading ? (
          <Card padding="lg">
            <p className="text-sm text-fg-muted">読み込み中...</p>
          </Card>
        ) : projects.length === 0 ? (
          <Card padding="lg" className="text-center">
            <p className="text-sm text-fg-muted mb-3">
              プロジェクトがありません。
            </p>
            <p className="text-xs text-fg-subtle mb-4">
              「面談調整開始」から新規作成してください。
            </p>
            <Button
              variant="primary"
              size="md"
              onClick={() => navigate('/projects/new')}
            >
              面談調整開始
            </Button>
          </Card>
        ) : (
          <ul
            data-testid="project-list"
            className="list-none p-0 m-0 flex flex-col gap-2"
          >
            {projects.map((project) => (
              <li key={project.project_id}>
                <Card
                  padding="none"
                  className="flex items-center gap-3 p-4 cursor-pointer hover:border-brand-300 hover:shadow-md transition-all"
                  onClick={() => navigate(`/projects/${project.project_id}`)}
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <strong className="text-fg font-medium truncate">
                        {project.display_name}
                      </strong>
                      <Badge tone={STATUS_TONE[project.status] ?? 'neutral'}>
                        {STATUS_LABEL[project.status] ?? project.status}
                      </Badge>
                    </div>
                    <p className="mt-1 text-xs text-fg-subtle">
                      作成: {new Date(project.created_at).toLocaleDateString('ja-JP')}
                    </p>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={(e) => {
                      e.stopPropagation()
                      setDeleteError(null)
                      setConfirmTarget(project)
                    }}
                    data-testid={`delete-project-button-${project.project_id}`}
                    aria-label={`「${project.display_name}」を削除`}
                    className="text-danger-700 hover:bg-danger-50 hover:text-danger-700"
                  >
                    削除
                  </Button>
                </Card>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* 削除確認ダイアログ */}
      {confirmTarget && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
          onClick={() => {
            if (!deleteMutation.isPending) {
              setConfirmTarget(null)
              setDeleteError(null)
            }
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            data-testid="delete-confirm-dialog"
            onClick={(e) => e.stopPropagation()}
            className="bg-surface rounded-lg shadow-popover max-w-md w-full p-6 border border-border"
          >
            <h2 className="text-lg font-semibold text-danger-700 mb-2 flex items-center gap-2">
              <span aria-hidden="true">⚠</span>
              プロジェクトの削除
            </h2>
            <p className="text-sm text-fg mb-2">
              「<strong className="font-semibold">{confirmTarget.display_name}</strong>」を削除します。
            </p>
            <p className="text-xs text-fg-muted mb-4">
              この操作は取り消せません。プロジェクトの設定・回答・ドラフトがすべて失われます。
            </p>
            {deleteError != null && (
              <Alert variant="error" className="mb-4">
                エラー: {deleteError}
              </Alert>
            )}
            <div className="flex gap-2 justify-end">
              <Button
                variant="ghost"
                onClick={() => {
                  setConfirmTarget(null)
                  setDeleteError(null)
                }}
                disabled={deleteMutation.isPending}
                data-testid="delete-cancel-button"
              >
                キャンセル
              </Button>
              <Button
                variant="danger"
                onClick={() => deleteMutation.mutate(confirmTarget.project_id)}
                disabled={deleteMutation.isPending}
                data-testid="delete-confirm-button"
              >
                {deleteMutation.isPending ? '削除中...' : '削除する'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  )
}
