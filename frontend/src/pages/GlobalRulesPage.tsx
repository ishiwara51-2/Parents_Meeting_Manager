/**
 * グローバルルール設定画面
 * requirements.md §4.5.1
 * - プロジェクト作成時に既定値として複製されるグローバルルールを設定
 * - global_constraints: max_consecutive_slots, forced_break_slots, max_slots_per_day
 * - teacher_unavailable の管理（Phase 4.2 では基本実装）
 */

import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { rulesApi } from '../api'
import type { Rules } from '../api'

export default function GlobalRulesPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [localRules, setLocalRules] = useState<Rules | null>(null)
  const [saved, setSaved] = useState(false)
  const [apiError, setApiError] = useState('')

  const { data: rules, isLoading } = useQuery({
    queryKey: ['global-rules'],
    queryFn: rulesApi.getGlobal,
  })

  // サーバから取得したルールをローカル状態に反映
  useEffect(() => {
    if (rules) {
      setLocalRules(rules)
    }
  }, [rules])

  const mutation = useMutation({
    mutationFn: (r: Rules) => rulesApi.putGlobal(r),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['global-rules'] })
      setSaved(true)
      setApiError('')
    },
    onError: (err: Error) => {
      setApiError(err.message ?? '保存に失敗しました')
    },
  })

  const handleSave = () => {
    if (!localRules) return
    setSaved(false)
    mutation.mutate(localRules)
  }

  const updateGlobalConstraint = <K extends keyof Rules['global_constraints']>(
    key: K,
    value: Rules['global_constraints'][K]
  ) => {
    setLocalRules((prev) =>
      prev
        ? {
            ...prev,
            global_constraints: { ...prev.global_constraints, [key]: value },
          }
        : null
    )
  }

  if (isLoading || !localRules) {
    return (
      <div className="container">
        <h1>グローバルルール設定</h1>
        <p>読み込み中...</p>
      </div>
    )
  }

  const gc = localRules.global_constraints

  return (
    <div className="container">
      <h1>グローバルルール設定</h1>
      <p>プロジェクト新規作成時にこの設定が既定値として複製されます。</p>

      {/* 保存成功メッセージ */}
      {saved && (
        <p role="status" style={{ color: 'green' }}>
          保存しました
        </p>
      )}

      {/* APIエラー */}
      {apiError && (
        <p role="alert" style={{ color: 'red' }}>
          {apiError}
        </p>
      )}

      <fieldset style={{ marginBottom: '1.5rem' }}>
        <legend>グローバル制約</legend>

        {/* 最大連続コマ数 */}
        <div style={{ marginBottom: '1rem' }}>
          <label htmlFor="max-consecutive-slots">最大連続コマ数</label>
          <br />
          <input
            id="max-consecutive-slots"
            type="number"
            value={gc.max_consecutive_slots}
            onChange={(e) =>
              updateGlobalConstraint(
                'max_consecutive_slots',
                Number(e.target.value)
              )
            }
            min={1}
            max={20}
            style={{ width: '80px' }}
          />
        </div>

        {/* 強制空きコマ数 */}
        <div style={{ marginBottom: '1rem' }}>
          <label htmlFor="forced-break-slots">強制空きコマ数</label>
          <br />
          <input
            id="forced-break-slots"
            type="number"
            value={gc.forced_break_slots}
            onChange={(e) =>
              updateGlobalConstraint('forced_break_slots', Number(e.target.value))
            }
            min={0}
            max={5}
            style={{ width: '80px' }}
          />
        </div>

        {/* 1日あたりコマ数上限 */}
        <div style={{ marginBottom: '1rem' }}>
          <label htmlFor="max-slots-per-day">1日あたりコマ数上限</label>
          <br />
          <input
            id="max-slots-per-day"
            type="number"
            value={gc.max_slots_per_day}
            onChange={(e) =>
              updateGlobalConstraint('max_slots_per_day', Number(e.target.value))
            }
            min={1}
            max={50}
            style={{ width: '80px' }}
          />
        </div>
      </fieldset>

      {/* ボタン */}
      <div style={{ display: 'flex', gap: '0.5rem' }}>
        <button onClick={handleSave} disabled={mutation.isPending}>
          {mutation.isPending ? '保存中...' : '保存'}
        </button>
        <button type="button" onClick={() => navigate('/')}>
          ホームへ戻る
        </button>
      </div>
    </div>
  )
}
