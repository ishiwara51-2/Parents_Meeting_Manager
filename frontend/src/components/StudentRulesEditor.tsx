/**
 * 生徒別ルール設定エディタ。
 * 1 行 = 生徒番号（"," 区切りのテキストボックス）｜ルール選択プルダウン｜ルールごとの詳細設定。
 */
import { Button, Input, Select } from './ui'
import { emptyRow, STUDENT_RULE_OPTIONS } from '../lib/studentRules'
import type { StudentRuleRow, StudentRuleType } from '../lib/studentRules'

interface Props {
  rows: StudentRuleRow[]
  onChange: (rows: StudentRuleRow[]) => void
  /** 行 id → エラーメッセージ（保存時の検証結果） */
  errors: Record<string, string>
}

/** ルール種別ごとの詳細設定ボックス。ルールを増やすときはここに分岐を足す。 */
function RuleDetail({
  row,
  index,
  onPatch,
}: {
  row: StudentRuleRow
  index: number
  onPatch: (patch: Partial<StudentRuleRow>) => void
}) {
  switch (row.ruleType) {
    case 'prefer_date_range':
      return (
        <div className="flex items-center gap-2 rounded-md border border-border bg-surface-muted px-3 py-1.5">
          <Input
            type="date"
            aria-label={`${index + 1}行目 優先期間の開始日`}
            value={row.dateFrom}
            onChange={(e) => onPatch({ dateFrom: e.target.value })}
            className="w-40"
          />
          <span className="text-sm text-fg-muted">〜</span>
          <Input
            type="date"
            aria-label={`${index + 1}行目 優先期間の終了日`}
            value={row.dateTo}
            onChange={(e) => onPatch({ dateTo: e.target.value })}
            className="w-40"
          />
        </div>
      )
  }
}

export default function StudentRulesEditor({ rows, onChange, errors }: Props) {
  const patchRow = (id: string, patch: Partial<StudentRuleRow>) =>
    onChange(rows.map((r) => (r.id === id ? { ...r, ...patch } : r)))

  return (
    <div className="flex flex-col gap-4">
      {rows.length === 0 && (
        <p className="text-sm text-fg-muted">生徒別のルールはまだありません。</p>
      )}

      {rows.map((row, i) => (
        <div key={row.id} className="flex flex-col gap-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <Input
              aria-label={`${i + 1}行目 生徒番号（カンマ区切り）`}
              placeholder="生徒番号（例: 3,8,12）"
              value={row.studentsText}
              onChange={(e) => patchRow(row.id, { studentsText: e.target.value })}
              className="w-56"
            />
            <Select
              aria-label={`${i + 1}行目 ルール`}
              value={row.ruleType}
              onChange={(e) =>
                patchRow(row.id, { ruleType: e.target.value as StudentRuleType })
              }
              className="w-auto min-w-64"
            >
              {STUDENT_RULE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </Select>
            <RuleDetail row={row} index={i} onPatch={(p) => patchRow(row.id, p)} />
            <Button
              variant="secondary"
              size="sm"
              onClick={() => onChange(rows.filter((r) => r.id !== row.id))}
              aria-label={`${i + 1}行目を削除`}
            >
              削除
            </Button>
          </div>
          {errors[row.id] && (
            <p role="alert" className="text-sm text-danger-600">
              {errors[row.id]}
            </p>
          )}
        </div>
      ))}

      <div>
        <Button variant="secondary" size="sm" onClick={() => onChange([...rows, emptyRow()])}>
          ＋ 生徒別ルールを追加
        </Button>
      </div>
    </div>
  )
}
