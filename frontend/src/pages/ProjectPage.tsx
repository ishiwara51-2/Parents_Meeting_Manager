/**
 * プロジェクト詳細画面
 * requirements.md §4.3
 *
 * 機能:
 *   - プロジェクトメタ情報の表示
 *   - 候補日程聴取用 Google Form 作成 / URL コピー
 *   - 受領状況（受領済み / 未受領 出席番号）表示
 *   - 最新回答を取得ボタン（手動ポーリング）
 *   - 自動ポーリング（60 秒間隔、setInterval）
 *   - ルールカスタマイズ / 面談日程案作成 ボタン
 */

import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, formApi, responsesApi } from '../api'
import type { FormInfo } from '../api'
import {
  Alert,
  AppShell,
  Button,
  Card,
  CardHeader,
  Stepper,
} from '../components/ui'
import type { Step, StepState } from '../components/ui'

/** 自動ポーリング間隔（ミリ秒）。requirements.md §4.4 の既定 60 秒 */
const POLLING_INTERVAL_MS = 60_000

/**
 * sessionStorage キー：OAuth 認証から戻った後、Form 作成を自動再開するための
 * 「意図」フラグ。プロジェクト ID 単位で分離する。
 */
const formIntentKey = (projectId: string) => `pendingFormCreate:${projectId}`

const STATUS_LABEL: Record<string, string> = {
  in_progress: '進行中',
  draft_saved: 'ドラフト保存済',
  finalized: '確定済',
}

export default function ProjectPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [formError, setFormError] = useState('')
  const [syncError, setSyncError] = useState('')
  const [copySuccess, setCopySuccess] = useState(false)
  const autoFormTriggeredRef = useRef(false)

  const { data: project, isLoading: projectLoading } = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => projectsApi.get(projectId!),
  })

  const {
    data: formInfo,
    isLoading: formLoading,
  } = useQuery({
    queryKey: ['form', projectId],
    queryFn: () => formApi.get(projectId!),
    retry: false,
  })

  const { data: responseStatus } = useQuery({
    queryKey: ['responses-status', projectId],
    queryFn: () => responsesApi.status(projectId!),
  })

  const createFormMutation = useMutation({
    mutationFn: () => formApi.create(projectId!),
    onSuccess: () => {
      if (projectId) sessionStorage.removeItem(formIntentKey(projectId))
      queryClient.invalidateQueries({ queryKey: ['form', projectId] })
      setFormError('')
    },
    onError: (err: Error & { status?: number }) => {
      if (err.status === 401) {
        if (autoFormTriggeredRef.current) {
          if (projectId) sessionStorage.removeItem(formIntentKey(projectId))
          setFormError(
            'Google 認証が完了しませんでした。再度「候補日程聴取用Google Form作成」ボタンを押してください。',
          )
          return
        }
        if (projectId) sessionStorage.setItem(formIntentKey(projectId), '1')
        const next = encodeURIComponent(
          `${window.location.origin}/projects/${projectId}`,
        )
        window.location.href = `/api/auth/google?next=${next}`
        return
      }
      if (projectId) sessionStorage.removeItem(formIntentKey(projectId))
      setFormError(err.message ?? 'Form の作成に失敗しました')
    },
  })

  const syncMutation = useMutation({
    mutationFn: () => responsesApi.sync(projectId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['responses-status', projectId] })
      setSyncError('')
    },
    onError: (err: Error) => {
      setSyncError(err.message ?? '回答の取得に失敗しました')
    },
  })

  useEffect(() => {
    if (!projectId) return
    const id = setInterval(() => {
      responsesApi
        .sync(projectId)
        .then(() => {
          queryClient.invalidateQueries({
            queryKey: ['responses-status', projectId],
          })
        })
        .catch(() => {
          // バックグラウンドポーリングのエラーはサイレント
        })
    }, POLLING_INTERVAL_MS)
    return () => clearInterval(id)
  }, [projectId, queryClient])

  const handleCopyUrl = async (url: string) => {
    try {
      await navigator.clipboard.writeText(url)
      setCopySuccess(true)
      setTimeout(() => setCopySuccess(false), 2000)
    } catch {
      // clipboard API が使えない環境ではサイレント失敗
    }
  }

  const currentFormInfo: FormInfo | undefined =
    formInfo ?? createFormMutation.data

  useEffect(() => {
    if (!projectId) return
    if (autoFormTriggeredRef.current) return
    if (formLoading) return
    if (currentFormInfo) {
      sessionStorage.removeItem(formIntentKey(projectId))
      return
    }
    if (sessionStorage.getItem(formIntentKey(projectId)) !== '1') return
    autoFormTriggeredRef.current = true
    createFormMutation.mutate()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, formLoading, currentFormInfo])

  if (projectLoading || !project) {
    return (
      <AppShell title="プロジェクト" breadcrumbs={[{ label: '読み込み中...' }]}>
        <Card>
          <p className="text-sm text-fg-muted">読み込み中...</p>
        </Card>
      </AppShell>
    )
  }

  const totalStudents = project.student_numbers.length
  const receivedCount = responseStatus?.received.length ?? 0
  const progressPct = totalStudents > 0 ? Math.round((receivedCount / totalStudents) * 100) : 0

  // ===== ワークフロー進捗の判定 =====
  // 1. Form作成: currentFormInfo の有無
  // 2. 回答収集: 受領 / 総数
  // 3. 日程案作成: project.status が draft_saved / finalized なら完了
  // 4. 保存: draft_saved / finalized で完了
  const formDone = currentFormInfo != null
  const allResponsesIn = totalStudents > 0 && receivedCount === totalStudents
  const draftSaved =
    project.status === 'draft_saved' || project.status === 'finalized'

  function stateOf(stepIdx: number): StepState {
    // 完了判定（後ろから優先的に判定）
    if (stepIdx === 0) return formDone ? 'done' : 'active'
    if (stepIdx === 1) {
      if (allResponsesIn) return 'done'
      if (formDone) return 'active'
      return 'pending'
    }
    if (stepIdx === 2) {
      // ドラフト保存後も「確認・修正」は常に未完了扱い（再修正の余地があるため）
      if (draftSaved) return 'active'
      if (allResponsesIn || receivedCount > 0) return 'active'
      return 'pending'
    }
    if (stepIdx === 3) {
      return draftSaved ? 'done' : 'pending'
    }
    return 'pending'
  }

  const steps: Step[] = [
    {
      key: 'form',
      label: 'Form作成',
      state: stateOf(0),
    },
    {
      key: 'collect',
      label: '回答収集',
      hint:
        totalStudents > 0 ? `${receivedCount} / ${totalStudents}` : undefined,
      state: stateOf(1),
    },
    {
      key: 'schedule',
      label: draftSaved ? '確認・修正' : '日程案作成',
      state: stateOf(2),
    },
    {
      key: 'save',
      label: '保存',
      state: stateOf(3),
    },
  ]

  // 次のアクションを判定（ラベル＋クリック先）
  //  - 同ページ内のセクションは id でスクロール
  //  - 別ページ（日程案画面）はルーティングで遷移
  type NextStepTarget =
    | { kind: 'scroll'; elementId: string }
    | { kind: 'navigate'; to: string }
  const nextAction: { label: string; target: NextStepTarget } = !formDone
    ? {
        label: 'Google Formを作成する',
        target: { kind: 'scroll', elementId: 'form-section' },
      }
    : !allResponsesIn && receivedCount === 0
      ? {
          label: '保護者の回答を待っています',
          target: { kind: 'scroll', elementId: 'responses-section' },
        }
      : draftSaved
        ? {
            label: '現在のドラフトを確認・修正する',
            target: {
              kind: 'navigate',
              to: `/projects/${projectId}/schedule`,
            },
          }
        : {
            label: '面談日程案を作成する',
            target: {
              kind: 'navigate',
              to: `/projects/${projectId}/schedule`,
            },
          }
  const nextActionDisabled = !formDone || (!allResponsesIn && receivedCount === 0)

  const handleNextStepClick = () => {
    if (nextAction.target.kind === 'navigate') {
      navigate(nextAction.target.to)
      return
    }
    const el = document.getElementById(nextAction.target.elementId)
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <AppShell
      breadcrumbs={[{ label: 'プロジェクト' }]}
      title={project.display_name}
      subtitle={STATUS_LABEL[project.status] ?? project.status}
    >
      <div className="flex flex-col gap-5">
        {/* ステッパー：ワークフロー進捗 */}
        <Card padding="md">
          <Stepper steps={steps} />
          <div className="mt-3 pt-3 border-t border-border text-sm text-fg-muted text-center">
            次のステップ:{' '}
            <button
              type="button"
              onClick={handleNextStepClick}
              className="font-semibold text-brand-700 hover:text-brand-900 hover:underline transition-colors"
            >
              {nextAction.label}
            </button>
          </div>
        </Card>

        {/* プロジェクト概要 */}
        <Card>
          <CardHeader title="プロジェクト概要" />
          <dl className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
            <div>
              <dt className="text-xs font-medium text-fg-subtle uppercase tracking-wider mb-1">
                候補日
              </dt>
              <dd className="text-fg">{project.candidate_dates.join(', ')}</dd>
            </div>
            <div>
              <dt className="text-xs font-medium text-fg-subtle uppercase tracking-wider mb-1">
                1コマの長さ
              </dt>
              <dd className="text-fg">{project.slot_minutes} 分</dd>
            </div>
            <div>
              <dt className="text-xs font-medium text-fg-subtle uppercase tracking-wider mb-1">
                出席番号
              </dt>
              <dd className="text-fg break-all">
                {project.student_numbers.join(', ')}
              </dd>
            </div>
          </dl>
        </Card>

        {/* Google Form セクション */}
        <Card id="form-section">
          <CardHeader
            title="候補日程聴取用 Google Form"
            description="保護者に候補日程を聞くための Google Form を作成・共有します。"
          />

          {formLoading ? (
            <p className="text-sm text-fg-muted">読み込み中...</p>
          ) : currentFormInfo ? (
            <div className="flex flex-col gap-3">
              <div className="rounded-md border border-border bg-surface-sunken px-3 py-2">
                <p className="text-xs font-medium text-fg-subtle mb-1">
                  保護者向け回答 URL
                </p>
                <a
                  href={currentFormInfo.responderUri}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-brand-700 hover:text-brand-900 underline break-all"
                >
                  {currentFormInfo.responderUri}
                </a>
              </div>
              <div className="flex items-center gap-3">
                <Button
                  variant="primary"
                  size="md"
                  onClick={() => handleCopyUrl(currentFormInfo.responderUri)}
                >
                  URLをコピー
                </Button>
                {copySuccess && (
                  <span className="text-sm text-success-700 font-medium">
                    ✓ コピーしました！
                  </span>
                )}
              </div>
              {currentFormInfo.editUri && (
                <a
                  href={currentFormInfo.editUri}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-fg-muted hover:text-brand-700 underline"
                >
                  Form を編集（教師用）
                </a>
              )}
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              {autoFormTriggeredRef.current && createFormMutation.isPending && (
                <Alert variant="success">
                  Google 認証が完了しました。Form を作成しています...
                </Alert>
              )}
              <p className="text-sm text-fg-muted">
                ボタンを押すと Google Form が自動生成されます。
                初回はブラウザで Google アカウント認証が必要です。
              </p>
              <div>
                <Button
                  variant="primary"
                  size="md"
                  onClick={() => createFormMutation.mutate()}
                  disabled={createFormMutation.isPending}
                >
                  {createFormMutation.isPending
                    ? '作成中...'
                    : '候補日程聴取用Google Form作成'}
                </Button>
              </div>
              {formError && <Alert variant="error">{formError}</Alert>}
            </div>
          )}
        </Card>

        {/* 受領状況 */}
        <Card id="responses-section">
          <CardHeader
            title="受領状況"
            description="保護者からの回答状況です。自動で 60 秒ごとに更新されます。"
            actions={
              <Button
                variant="secondary"
                size="sm"
                onClick={() => syncMutation.mutate()}
                disabled={syncMutation.isPending}
              >
                {syncMutation.isPending ? '取得中...' : '最新回答を取得'}
              </Button>
            }
          />

          {/* プログレスバー */}
          {totalStudents > 0 && (
            <div className="mb-4">
              <div className="flex items-baseline justify-between mb-1.5">
                <span className="text-xs font-medium text-fg-subtle uppercase tracking-wider">
                  受領進捗
                </span>
                <span className="text-sm">
                  <span className="font-semibold text-fg">{receivedCount}</span>
                  <span className="text-fg-muted"> / {totalStudents} 件</span>
                  <span className="ml-2 text-fg-subtle">({progressPct}%)</span>
                </span>
              </div>
              <div className="h-2 rounded-full bg-surface-sunken overflow-hidden">
                <div
                  className="h-full bg-brand-500 transition-all"
                  style={{ width: `${progressPct}%` }}
                />
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="rounded-md border border-success-200 bg-success-50 px-3 py-2">
              <h3 className="text-xs font-semibold text-success-700 uppercase tracking-wider mb-1">
                受領済み
              </h3>
              <p className="text-sm text-fg">
                {responseStatus && responseStatus.received.length > 0
                  ? responseStatus.received.join(', ')
                  : '（なし）'}
              </p>
            </div>
            <div className="rounded-md border border-border bg-surface-sunken px-3 py-2">
              <h3 className="text-xs font-semibold text-fg-muted uppercase tracking-wider mb-1">
                未受領
              </h3>
              <p className="text-sm text-fg">
                {responseStatus && responseStatus.pending.length > 0
                  ? responseStatus.pending.join(', ')
                  : '（なし）'}
              </p>
            </div>
          </div>

          {syncError && (
            <Alert variant="error" className="mt-3">
              {syncError}
            </Alert>
          )}
        </Card>

        {/* ナビゲーション */}
        <div className="sticky bottom-0 bg-surface-muted py-3 -mx-6 px-6 border-t border-border">
          {nextActionDisabled && (
            <p className="text-xs text-fg-muted mb-2">
              {!formDone
                ? '上の「候補日程聴取用Google Form作成」を先に行ってください。'
                : '少なくとも 1 件以上の回答が必要です。「最新回答を取得」を押してください。'}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <Button
              variant="primary"
              size="lg"
              onClick={() => navigate(`/projects/${projectId}/schedule`)}
              disabled={nextActionDisabled}
            >
              {draftSaved ? '確認・修正' : '面談日程案作成'}
            </Button>
            <Button
              variant="secondary"
              size="lg"
              onClick={() => navigate(`/projects/${projectId}/rules`)}
            >
              ルールカスタマイズ
            </Button>
          </div>
        </div>
      </div>
    </AppShell>
  )
}
