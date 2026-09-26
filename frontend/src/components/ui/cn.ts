/**
 * className を結合する簡易ユーティリティ（clsx の最小版）。
 * false/null/undefined は無視され、残った文字列を空白区切りで連結する。
 * 条件付きクラス名を `cn(base, condition && 'extra-class')` のように書ける。
 */
export function cn(
  ...parts: Array<string | false | null | undefined>
): string {
  return parts.filter(Boolean).join(' ')
}
