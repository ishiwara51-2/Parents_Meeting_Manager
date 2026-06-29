/**
 * プロジェクトルール設定画面
 * requirements.md §4.5.2
 *
 * グローバルルールを複製した状態から開始し、このプロジェクト固有のルールを設定する。
 * 制約種別: 連続コマ数上限 / 強制空きコマ数 / 1日あたりコマ数上限 （グローバル系）
 * Phase 4.3 では global_constraints のみ実装（student_constraints は将来対応）
 */

import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { rulesApi } from '../api'
import type { Rules } from '../api'

export default function ProjectRulesPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [localRules, setLocalRules] = useState<Rules | null>(null)
  const [saved, setSaved] = useState(false)
  const [apiError, setApiError] = useState('')

  // プロジェクトルール取得
  const { data: rules, isLoading } = useQuery({
    queryKey: ['project-rules', projectId],
    queryFn: () => rulesApi.getProject(projectId!),
  })

  // サーバから取得したルールをローカル状態に反映
  useEffect(() => {
    if (rules) {
      setLocalRules(rules)
    }
  }, [rules])

  // プロジェクトルール保存 mutation
  const mutation = useMutation({
    mutationFn: (r: Rules) => rulesApi.putProject(projectId!, r),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project-rules', projectId] })
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

  /** global_constraints の各フィールドを更新するヘルパー */
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

  // ローディング中
  if (isLoading || !localRules) {
    return (
      <div>
        <h1>プロジェクトルール設定</h1>
        <p>読み込み中...</p>
      </div>
    )
  }

  const gc = localRules.global_constraints

  return (
    <div>
      <h1>プロジェクトルール設定</h1>
      <p>このプロジェクト固有のルールを設定します。</p>

      {/* 保存成功メッセージ */}
      {saved && (
        <p role="status" style={{ color: 'green' }}>
          保存しました
        </p>
      )}

      {/* API エラー */}
      {apiError && (
        <p role="alert" style={{ color: 'red' }}>
          {apiError}
        </p>
      )}

      {/* ===== グローバル制約フォーム ===== */}
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
              updateGlobalConstraint(
                'forced_break_slots',
                Number(e.target.value)
              )
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
              updateGlobalConstraint(
                'max_slots_per_day',
                Number(e.target.value)
              )
            }
            min={1}
            max={50}
            style={{ width: '80px' }}
          />
        </div>
      </fieldset>

      {/* ===== ボタン ===== */}
      <div style={{ display: 'flex', gap: '0.5rem' }}>
        <button onClick={handleSave} disabled={mutation.isPending}>
          {mutation.isPending ? '保存中...' : '保存'}
        </button>
        <button
          type="button"
          onClick={() => navigate(`/projects/${projectId}`)}
        >
          プロジェクトへ戻る
        </button>
      </div>
    </div>
  )
}
