import { describe, expect, it } from 'vitest'
import {
  emptyRow,
  mergeStudentConstraints,
  parseStudentNumbers,
  rowsFromConstraints,
  validateRow,
} from './studentRules'

describe('parseStudentNumbers', () => {
  it('カンマ区切りを数値配列にし、重複を除く', () => {
    expect(parseStudentNumbers('3, 8,12,8')).toEqual({ numbers: [3, 8, 12], invalid: [] })
  })
  it('全角カンマ・読点も許容する', () => {
    expect(parseStudentNumbers('1，2、3').numbers).toEqual([1, 2, 3])
  })
  it('不正な要素を invalid に集める', () => {
    expect(parseStudentNumbers('1,a,0,-2').invalid).toEqual(['a', '0', '-2'])
  })
})

describe('validateRow', () => {
  const ok = { ...emptyRow(), studentsText: '1,2', dateFrom: '2026-07-15', dateTo: '2026-07-16' }
  it('正常な行は null', () => expect(validateRow(ok)).toBeNull())
  it('生徒番号が空ならエラー', () =>
    expect(validateRow({ ...ok, studentsText: ' ' })).toMatch('生徒番号を入力'))
  it('期間未入力ならエラー', () =>
    expect(validateRow({ ...ok, dateTo: '' })).toMatch('開始日と終了日'))
  it('開始日が終了日より後ならエラー', () =>
    expect(validateRow({ ...ok, dateFrom: '2026-07-17' })).toMatch('開始日は終了日以前'))
})

describe('mergeStudentConstraints', () => {
  it('編集対象外の制約を保持し、行を prefer_date_range に変換する', () => {
    const existing = [
      { type: 'pairing' as const, student_numbers: [1, 2], weight: 5 },
      {
        type: 'prefer_date_range' as const,
        student_numbers: [9],
        date_from: '2026-07-01',
        date_to: '2026-07-02',
        weight: 3,
      },
    ]
    const rows = rowsFromConstraints(existing)
    expect(rows).toHaveLength(1)
    expect(rows[0].studentsText).toBe('9')
    const merged = mergeStudentConstraints(existing, rows)
    expect(merged).toEqual([existing[0], existing[1]])
  })
})

describe('validateRow 範囲チェック', () => {
  const row = { ...emptyRow(), studentsText: '1,5', dateFrom: '2026-07-15', dateTo: '2026-07-16' }
  it('範囲外の番号があればエラー', () =>
    expect(validateRow(row, { studentNumbers: [1, 2, 3] })).toBe('このプロジェクトに存在しない生徒番号です: 5'))
  it('すべて範囲内なら null、scope 未指定ならチェックしない', () => {
    expect(validateRow(row, { studentNumbers: [1, 5] })).toBeNull()
    expect(validateRow(row)).toBeNull()
  })
})

describe('validateRow 候補日チェック', () => {
  const scope = { candidateDates: ['2026-07-14', '2026-07-16'] }
  const row = { ...emptyRow(), studentsText: '1', dateFrom: '2026-07-14', dateTo: '2026-07-16' }
  const msg = '優先期間の開始日・終了日は、プロジェクトの候補日から選んでください'
  it('開始日・終了日が候補日なら null（間に候補日でない日があってもよい）', () => {
    expect(validateRow(row, scope)).toBeNull()
  })
  it('開始日または終了日が候補日でなければエラー', () => {
    expect(validateRow({ ...row, dateFrom: '2026-07-15' }, scope)).toBe(msg)
    expect(validateRow({ ...row, dateTo: '2026-07-17' }, scope)).toBe(msg)
  })
})
