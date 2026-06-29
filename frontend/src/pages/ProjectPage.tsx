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

import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, formApi, responsesApi } from '../api'
import type { FormInfo } from '../api'

/** 自動ポーリング間隔（ミリ秒）。requirements.md §4.4 の既定 60 秒 */
const POLLING_INTERVAL_MS = 60_000

export default function ProjectPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [formError, setFormError] = useState('')
  const [syncError, setSyncError] = useState('')
  const [copySuccess, setCopySuccess] = useState(false)

  // ----- データ取得 -----

  /** プロジェクト詳細 */
  const { data: project, isLoading: projectLoading } = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => projectsApi.get(projectId!),
  })

  /**
   * Form 情報（未作成の場合は 404 → isError=true）
   * retry:false で即座に isError を確定させ "Form 作成" ボタンを表示する
   */
  const {
    data: formInfo,
    isLoading: formLoading,
    isError: formNotCreated,
  } = useQuery({
    queryKey: ['form', projectId],
    queryFn: () => formApi.get(projectId!),
    retry: false,
  })

  /** 受領状況（受領済み / 未受領 出席番号） */
  const { data: responseStatus } = useQuery({
    queryKey: ['responses-status', projectId],
    queryFn: () => responsesApi.status(projectId!),
  })

  // ----- Mutation -----

  /** Form 作成 */
  const createFormMutation = useMutation({
    mutationFn: () => formApi.create(projectId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['form', projectId] })
      setFormError('')
    },
    onError: (err: Error) => {
      setFormError(err.message ?? 'Form の作成に失敗しました')
    },
  })

  /** 手動回答同期（最新回答を取得ボタン） */
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

  // ----- 自動ポーリング（60 秒間隔）-----

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
          // 手動ボタンからの明示的エラーは syncError で通知する
        })
    }, POLLING_INTERVAL_MS)
    return () => clearInterval(id)
  }, [projectId, queryClient])

  // ----- イベントハンドラ -----

  const handleCopyUrl = async (url: string) => {
    try {
      await navigator.clipboard.writeText(url)
      setCopySuccess(true)
      setTimeout(() => setCopySuccess(false), 2000)
    } catch {
      // clipboard API が使えない環境（HTTP など）ではサイレント失敗
    }
  }

  // ----- Form 情報（作成直後は mutation data を優先） -----
  const currentFormInfo: FormInfo | undefined =
    formInfo ?? createFormMutation.data

  // ----- ローディング -----

  if (projectLoading || !project) {
    return (
      <div>
        <h1>プロジェクト</h1>
        <p>読み込み中...</p>
      </div>
    )
  }

  // ----- レンダリング -----

  return (
    <div>
      <h1>{project.display_name}</h1>
      <p>ステータス: {project.status}</p>
      <p>
        候補日: {project.candidate_dates.join(', ')}　/　コマ: {project.slot_minutes}分
      </p>
      <p>出席番号: {project.student_numbers.join(', ')}</p>

      {/* ===== Form セクション ===== */}
      <section style={{ marginTop: '1.5rem', marginBottom: '1.5rem' }}>
        <h2>候補日程聴取用 Google Form</h2>

        {formLoading ? (
          <p>読み込み中...</p>
        ) : currentFormInfo ? (
          <div>
            <p>Form URL:</p>
            <a
              href={currentFormInfo.responderUri}
              target="_blank"
              rel="noopener noreferrer"
            >
              {currentFormInfo.responderUri}
            </a>
            <div style={{ marginTop: '0.5rem' }}>
              <button
                type="button"
                onClick={() => handleCopyUrl(currentFormInfo.responderUri)}
              >
                URLをコピー
              </button>
              {copySuccess && (
                <span style={{ marginLeft: '0.5rem', color: 'green' }}>
                  コピーしました！
                </span>
              )}
            </div>
            {currentFormInfo.editUri && (
              <p style={{ marginTop: '0.25rem' }}>
                <a
                  href={currentFormInfo.editUri}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ fontSize: '0.875rem' }}
                >
                  Form を編集（教師用）
                </a>
              </p>
            )}
          </div>
        ) : (
          <div>
            <button
              type="button"
              onClick={() => createFormMutation.mutate()}
              disabled={createFormMutation.isPending}
            >
              {createFormMutation.isPending
                ? '作成中...'
                : '候補日程聴取用Google Form作成'}
            </button>
            {formError && (
              <p role="alert" style={{ color: 'red', marginTop: '0.5rem' }}>
                {formError}
              </p>
            )}
          </div>
        )}
      </section>

      {/* ===== 受領状況 ===== */}
      <section style={{ marginBottom: '1.5rem' }}>
        <h2>受領状況</h2>

        <div style={{ display: 'flex', gap: '2rem', marginBottom: '0.75rem' }}>
          <div>
            <h3>受領済み</h3>
            <p>
              {responseStatus && responseStatus.received.length > 0
                ? responseStatus.received.join(', ')
                : '（なし）'}
            </p>
          </div>
          <div>
            <h3>未受領</h3>
            <p>
              {responseStatus && responseStatus.pending.length > 0
                ? responseStatus.pending.join(', ')
                : '（なし）'}
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={() => syncMutation.mutate()}
          disabled={syncMutation.isPending}
        >
          {syncMutation.isPending ? '取得中...' : '最新回答を取得'}
        </button>

        {syncError && (
          <p role="alert" style={{ color: 'red', marginTop: '0.5rem' }}>
            {syncError}
          </p>
        )}
      </section>

      {/* ===== ナビゲーション ===== */}
      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
        <button
          type="button"
          onClick={() => navigate(`/projects/${projectId}/rules`)}
        >
          ルールカスタマイズ
        </button>
        <button
          type="button"
          onClick={() => navigate(`/projects/${projectId}/schedule`)}
        >
          面談日程案作成
        </button>
        <button type="button" onClick={() => navigate('/')}>
          ホームへ戻る
        </button>
      </div>
    </div>
  )
}
