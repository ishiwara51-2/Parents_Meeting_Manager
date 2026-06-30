/**
 * グローバルルール設定画面
 * requirements.md §4.5.1
 * - プロジェクト作成時に既定値として複製されるグローバルルールを設定
 * - global_constraints: max_consecutive_slots, forced_break_slots, max_slots_per_day
 * - teacher_unavailable の管理（Phase 4.2 では基本実装）
 */

import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { rulesApi } from '../api'
import type { Rules } from '../api'
import {
  Alert,
  AppShell,
  Button,
  Card,
  CardHeader,
  FormField,
  Input,
} from '../components/ui'

export default function GlobalRulesPage() {
  const queryClient = useQueryClient()

  const [localRules, setLocalRules] = useState<Rules | null>(null)
  const [saved, setSaved] = useState(false)
  const [apiError, setApiError] = useState('')

  const { data: rules, isLoading } = useQuery({
    queryKey: ['global-rules'],
    queryFn: rulesApi.getGlobal,
  })

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
    value: Rules['global_constraints'][K],
  ) => {
    setLocalRules((prev) =>
      prev
        ? {
            ...prev,
            global_constraints: { ...prev.global_constraints, [key]: value },
          }
        : null,
    )
  }

  if (isLoading || !localRules) {
    return (
      <AppShell
        title="グローバルルール設定"
        breadcrumbs={[{ label: 'グローバルルール設定' }]}
      >
        <Card>
          <p className="text-sm text-fg-muted">読み込み中...</p>
        </Card>
      </AppShell>
    )
  }

  const gc = localRules.global_constraints

  return (
    <AppShell
      title="グローバルルール設定"
      subtitle="プロジェクト新規作成時にこの設定が既定値として複製されます。"
      breadcrumbs={[{ label: 'グローバルルール設定' }]}
    >
      <div className="flex flex-col gap-5">
        {saved && (
          <Alert variant="success" role="status">
            保存しました
          </Alert>
        )}
        {apiError && <Alert variant="error">{apiError}</Alert>}

        <Card>
          <CardHeader
            title="グローバル制約"
            description="スケジューリング時に守られる制約のデフォルト値です。"
          />

          <FormField
            label="最大連続コマ数"
            htmlFor="max-consecutive-slots"
            hint="この数を超えた連続面談は許可されません。"
          >
            <Input
              id="max-consecutive-slots"
              type="number"
              value={gc.max_consecutive_slots}
              onChange={(e) =>
                updateGlobalConstraint(
                  'max_consecutive_slots',
                  Number(e.target.value),
                )
              }
              min={1}
              max={20}
              className="w-24"
            />
          </FormField>

          <FormField
            label="強制空きコマ数"
            htmlFor="forced-break-slots"
            hint="連続上限に達した後、必ず空けるコマの数です。"
          >
            <Input
              id="forced-break-slots"
              type="number"
              value={gc.forced_break_slots}
              onChange={(e) =>
                updateGlobalConstraint(
                  'forced_break_slots',
                  Number(e.target.value),
                )
              }
              min={0}
              max={5}
              className="w-24"
            />
          </FormField>

          <FormField
            label="1日あたりコマ数上限"
            htmlFor="max-slots-per-day"
            hint="1日に割り当てる面談コマの上限です。"
          >
            <Input
              id="max-slots-per-day"
              type="number"
              value={gc.max_slots_per_day}
              onChange={(e) =>
                updateGlobalConstraint(
                  'max_slots_per_day',
                  Number(e.target.value),
                )
              }
              min={1}
              max={50}
              className="w-24"
            />
          </FormField>
        </Card>

        <div className="flex gap-2 sticky bottom-0 bg-surface-muted py-3 -mx-6 px-6 border-t border-border">
          <Button
            variant="primary"
            size="lg"
            onClick={handleSave}
            disabled={mutation.isPending}
          >
            {mutation.isPending ? '保存中...' : '保存'}
          </Button>
        </div>
      </div>
    </AppShell>
  )
}
