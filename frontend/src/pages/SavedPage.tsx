/**
 * 保存完了画面
 * requirements.md §4.8
 *
 * Phase 4.4c 実装:
 * - 「PDF出力」ボタン（Phase 5.2 でスタブを実装に置き換え）
 * - 「再編集」ボタン（draftsApi.unlock → SchedulePage へ戻る）
 */

import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { draftsApi } from '../api'

export default function SavedPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()

  const [unlocking, setUnlocking] = useState(false)
  const [unlockError, setUnlockError] = useState<string | null>(null)

  // TODO: Phase 5.2 で実装
  function handleDownloadPdf() {
    console.log('PDF download not yet implemented')
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
          style={{
            padding: '10px 24px',
            fontSize: '1rem',
            cursor: 'pointer',
            backgroundColor: '#6b7280',
            color: '#fff',
            border: 'none',
            borderRadius: '4px',
          }}
        >
          PDF出力
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
