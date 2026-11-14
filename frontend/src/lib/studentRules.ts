/**
 * 生徒別ルール設定の純粋ロジック（画面の行 ⇔ API の student_constraints の変換と検証）。
 *
 * 画面では 1 行 = 「生徒番号（カンマ区切り）｜ルール種別｜ルールごとの詳細設定」。
 * 現在選べるルールは「期間優先（prefer_date_range）」のみ。
 * ルールを増やすときは STUDENT_RULE_OPTIONS・StudentRuleRow・変換/検証の各分岐に追加する。
 */

import type { StudentConstraint } from '../api/types'

/** 生徒別に設定できるルールの種別（プルダウンの value）。 */
export type StudentRuleType = 'prefer_date_range'

export const STUDENT_RULE_OPTIONS: { value: StudentRuleType; label: string }[] = [
  {
    value: 'prefer_date_range',
    label: '指定期間の日に優先して割り当てる',
  },
]

/** 期間優先ルールの重み。画面から重みは設定しないので固定値（0〜10）を使う。 */
export const DEFAULT_STUDENT_RULE_WEIGHT = 5

export interface StudentRuleRow {
  /** 画面上の行識別子（React の key 用。API には送らない） */
  id: string
  /** 生徒番号の入力文字列（"," 区切り） */
  studentsText: string
  ruleType: StudentRuleType
  /** 詳細設定（prefer_date_range）：優先する期間 "YYYY-MM-DD" */
  dateFrom: string
  dateTo: string
  weight: number
}

let rowSeq = 0
export function newRowId(): string {
  rowSeq += 1
  return `student-rule-${rowSeq}`
}

export function emptyRow(): StudentRuleRow {
  return {
    id: newRowId(),
    studentsText: '',
    ruleType: 'prefer_date_range',
    dateFrom: '',
    dateTo: '',
    weight: DEFAULT_STUDENT_RULE_WEIGHT,
  }
}

/** この画面で編集できる制約か（それ以外の制約は編集せずそのまま保持する）。 */
export function isEditableConstraint(c: StudentConstraint): boolean {
  return c.type === 'prefer_date_range'
}

/** 保存済みの student_constraints から画面の行を作る。 */
export function rowsFromConstraints(constraints: StudentConstraint[]): StudentRuleRow[] {
  return constraints.filter(isEditableConstraint).map((c) => ({
    id: newRowId(),
    studentsText: (c.student_numbers ?? []).join(','),
    ruleType: 'prefer_date_range' as const,
    dateFrom: c.date_from ?? '',
    dateTo: c.date_to ?? '',
    weight: c.weight ?? DEFAULT_STUDENT_RULE_WEIGHT,
  }))
}

/**
 * "," 区切りの生徒番号文字列を数値配列にする（全角のカンマ・読点も区切りとして許容）。
 * 不正な要素があれば invalid にその文字列を入れる。重複は取り除く。
 */
export function parseStudentNumbers(text: string): { numbers: number[]; invalid: string[] } {
  const parts = text
    .split(/[,，、]/)
    .map((p) => p.trim())
    .filter((p) => p !== '')
  const numbers: number[] = []
  const invalid: string[] = []
  for (const p of parts) {
    if (/^\d+$/.test(p) && Number(p) >= 1) {
      const n = Number(p)
      if (!numbers.includes(n)) numbers.push(n)
    } else {
      invalid.push(p)
    }
  }
  return { numbers, invalid }
}

/** 入力値をプロジェクトの内容と照らすための情報（未指定の項目はチェックしない）。 */
export interface ProjectScope {
  /** プロジェクトの生徒番号 */
  studentNumbers?: number[]
  /** プロジェクトの候補日 "YYYY-MM-DD"[]（期間の開始日・終了日はこの中から選ぶ） */
  candidateDates?: string[]
}

/**
 * 行ごとの入力エラーメッセージ（問題なければ null）。
 * scope を渡すと、プロジェクトに存在しない生徒番号や、候補日以外の日付もエラーにする。
 */
export function validateRow(row: StudentRuleRow, scope: ProjectScope = {}): string | null {
  const allowedNumbers = scope.studentNumbers
  const { numbers, invalid } = parseStudentNumbers(row.studentsText)
  if (invalid.length > 0) {
    return `生徒番号は 1 以上の整数を "," 区切りで入力してください（不正な値: ${invalid.join(' ')}）`
  }
  if (numbers.length === 0) return '生徒番号を入力してください'
  if (allowedNumbers) {
    const outOfRange = numbers.filter((n) => !allowedNumbers.includes(n))
    if (outOfRange.length > 0) {
      return `このプロジェクトに存在しない生徒番号です: ${outOfRange.join(',')}`
    }
  }
  if (row.ruleType === 'prefer_date_range') {
    if (!row.dateFrom || !row.dateTo) return '優先する期間の開始日と終了日を指定してください'
    if (row.dateFrom > row.dateTo) return '期間の開始日は終了日以前にしてください'
    const dates = scope.candidateDates
    if (dates && dates.length > 0) {
      if (!dates.includes(row.dateFrom) || !dates.includes(row.dateTo)) {
        return '優先期間の開始日・終了日は、プロジェクトの候補日から選んでください'
      }
    }
  }
  return null
}

/** 全行を検証し、{行 id: エラー} を返す（エラーのある行だけ含む）。 */
export function validateRows(
  rows: StudentRuleRow[],
  scope: ProjectScope = {},
): Record<string, string> {
  const errors: Record<string, string> = {}
  for (const row of rows) {
    const e = validateRow(row, scope)
    if (e) errors[row.id] = e
  }
  return errors
}

/**
 * 画面の行を API 用の制約に変換し、画面で編集できない既存制約（existing）はそのまま残して結合する。
 * 行は事前に validateRows で検証済みである前提。
 */
export function mergeStudentConstraints(
  existing: StudentConstraint[],
  rows: StudentRuleRow[],
): StudentConstraint[] {
  const kept = existing.filter((c) => !isEditableConstraint(c))
  const fromRows: StudentConstraint[] = rows.map((row) => ({
    type: 'prefer_date_range',
    student_numbers: parseStudentNumbers(row.studentsText).numbers,
    date_from: row.dateFrom,
    date_to: row.dateTo,
    weight: row.weight,
  }))
  return [...kept, ...fromRows]
}
