/**
 * 候補日（"YYYY-MM-DD"）の表示用フォーマットヘルパー。
 * 日付だけでは曜日が分かりづらいため、表示箇所で曜日を付加する。
 */

const WEEKDAY_JA = ['日', '月', '火', '水', '木', '金', '土']

/** "2026-07-15" → "2026-07-15（水）" */
export function formatDateWithWeekday(isoDate: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoDate)
  if (!m) return isoDate
  const [, y, mo, d] = m
  // ローカルの年月日成分から構築する（new Date(isoDate) は UTC 解釈されるため、
  // タイムゾーンによっては日付・曜日が1日ずれる恐れがある）
  const date = new Date(Number(y), Number(mo) - 1, Number(d))
  return `${isoDate}（${WEEKDAY_JA[date.getDay()]}）`
}
