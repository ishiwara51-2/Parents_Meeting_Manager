/**
 * 保存完了画面
 * requirements.md §4.8
 *
 * Phase 4.4c 実装:
 * - 「PDF出力」ボタン（Phase 5.2 で実装完了）
 * - 「再編集」ボタン（draftsApi.unlock → SchedulePage へ戻る）
 *
 * Phase 5.2 実装:
 * - handleDownloadPdf: /api/projects/{id}/pdf を fetch → Blob → a タグ click でダウンロード
 * - downloading / downloadError state 追加
 */

import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { draftsApi } from '../api'
import { Alert, AppShell, Button, Card } from '../components/ui'

export default function SavedPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()

  const [unlocking, setUnlocking] = useState(false)
  const [unlockError, setUnlockError] = useState<string | null>(null)

  const [downloading, setDownloading] = useState(false)
  const [downloadError, setDownloadError] = useState<string | null>(null)

  async function handleDownloadPdf() {
    if (!projectId) return
    setDownloading(true)
    setDownloadError(null)
    try {
      const res = await fetch(`/api/projects/${projectId}/pdf`)
      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: res.statusText }))
        throw new Error(
          typeof body.detail === 'string'
            ? body.detail
            : 'PDFの取得に失敗しました',
        )
      }
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `schedule_${projectId}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      const e = err as Error
      setDownloadError(e.message ?? 'PDFダウンロードに失敗しました')
    } finally {
      setDownloading(false)
    }
  }

  async function handleReEdit() {
    if (!projectId) return
    setUnlocking(true)
    setUnlockError(null)
    try {
      await draftsApi.unlock(projectId)
      navigate(`/projects/${projectId}/schedule`)
    } catch (err) {
      const e = err as Error
      setUnlockError(e.message ?? 'アンロックに失敗しました')
    } finally {
      setUnlocking(false)
    }
  }

  return (
    <AppShell
      title="保存完了"
      breadcrumbs={[
        { label: 'プロジェクト', to: `/projects/${projectId}` },
        { label: '保存完了' },
      ]}
    >
      <div className="flex flex-col gap-4">
        <Card>
          <div className="flex items-start gap-3">
            <span
              aria-hidden="true"
              className="text-2xl text-success-700 leading-none"
            >
              ✓
            </span>
            <div>
              <h2 className="text-lg font-semibold text-fg mb-1">
                日程案が保存されました
              </h2>
              <p className="text-sm text-fg-muted">
                PDF として出力するか、再編集できます。
              </p>
            </div>
          </div>
        </Card>

        {downloadError != null && (
          <Alert variant="error" title="PDF出力エラー">
            {downloadError}
          </Alert>
        )}
        {unlockError != null && (
          <Alert variant="error" title="再編集エラー">
            {unlockError}
          </Alert>
        )}

        <div className="flex flex-wrap gap-2">
          <Button
            variant="primary"
            size="lg"
            onClick={handleDownloadPdf}
            disabled={downloading}
          >
            {downloading ? 'ダウンロード中...' : 'PDF出力'}
          </Button>
          <Button
            variant="secondary"
            size="lg"
            onClick={handleReEdit}
            disabled={unlocking}
          >
            {unlocking ? '処理中...' : '再編集'}
          </Button>
        </div>
      </div>
    </AppShell>
  )
}
