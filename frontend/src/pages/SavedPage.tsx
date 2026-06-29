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
    <div style={{ padding: '16px' }}>
      <h1>保存完了</h1>
      <p>日程案が保存されました。</p>

      {downloadError != null && (
        <div
          role="alert"
          style={{
            color: '#b91c1c',
            backgroundColor: '#fef2f2',
            border: '1px solid #f87171',
            borderRadius: '4px',
            padding: '8px 12px',
            marginBottom: '12px',
          }}
        >
          エラー: {downloadError}
        </div>
      )}

      {unlockError != null && (
        <div
          role="alert"
          style={{
            color: '#b91c1c',
            backgroundColor: '#fef2f2',
            border: '1px solid #f87171',
            borderRadius: '4px',
            padding: '8px 12px',
            marginBottom: '12px',
          }}
        >
          エラー: {unlockError}
        </div>
      )}

      <div style={{ display: 'flex', gap: '8px', marginTop: '16px' }}>
        <button
          onClick={handleDownloadPdf}
          disabled={downloading}
          style={{
            padding: '10px 24px',
            fontSize: '1rem',
            cursor: downloading ? 'not-allowed' : 'pointer',
            backgroundColor: '#6b7280',
            color: '#fff',
            border: 'none',
            borderRadius: '4px',
            opacity: downloading ? 0.6 : 1,
          }}
        >
          {downloading ? 'ダウンロード中...' : 'PDF出力'}
        </button>
        <button
          onClick={handleReEdit}
          disabled={unlocking}
          style={{
            padding: '10px 24px',
            fontSize: '1rem',
            cursor: unlocking ? 'not-allowed' : 'pointer',
            backgroundColor: '#2563eb',
            color: '#fff',
            border: 'none',
            borderRadius: '4px',
            opacity: unlocking ? 0.6 : 1,
          }}
        >
          {unlocking ? '処理中...' : '再編集'}
        </button>
      </div>
    </div>
  )
}
