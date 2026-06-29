# PDF生成に関する設計決定（Phase 5.1）

## 1. 1ページ超過時の挙動

### 採用方針: フォントサイズ自動縮小 + 列幅均等調整

列数（候補日数）が増えた場合、以下の優先順位で対応する。

| 列数（候補日数） | セルフォントサイズ | 備考 |
|---|---|---|
| 1〜3 | 9pt | 基本サイズ |
| 4〜5 | 8pt | 小幅縮小 |
| 6〜7 | 7pt | 中幅縮小 |
| 8以上 | max(6pt, 9 - (列数-3)) | 最小 6pt まで縮小 |

列幅はページ内幅（180mm）から時間帯ラベル列幅（22mm）を引いた残りを均等分割する。
これにより最大約 9 列（候補日数）でも 1 ページに収まることを目標とする。

それ以上の列数については、ReportLab Platypus の自動改ページ機能（`repeatRows=1` で
ヘッダ行を各ページ先頭に繰り返す）に委ねる。

### 根拠

- requirements.md §4.8「複数日1ページのマトリクス形式」と明記されているが、
  実際の候補日数（通常 3〜5 日）であれば 1 ページに収まるケースが大半。
- プロトタイプとして「自動縮小で対応可能な範囲で 1 ページに収める」方針が
  実装コストと品質のバランスが最も良い。
- 10 日超など極端に多い場合は複数ページへの折り返しが自然（読みやすさの観点）。
- フォント最小 6pt を下回ると可読性が著しく損なわれるため、それ以上の縮小は行わない。

---

## 2. フォント選定の経緯

### 当初の予定（implementation_prompts_subdivided.md）

IPAex ゴシック（`backend/app/fonts/ipaexg.ttf`）を使用する予定だった。

### ユーザー判断による変更

Noto Sans CJK JP（OFL 1.1 / Google・Adobe）に変更。
配置先は `backend/app/fonts/NotoSansCJKjp-Regular.otf`。

### 実装時の判明事項とその対応

| 項目 | 内容 |
|---|---|
| 当初取得ソース | `https://github.com/notofonts/noto-cjk/raw/main/Sans/OTF/Japanese/NotoSansCJKjp-Regular.otf` |
| 問題点 | noto-cjk の OTF は PostScript (CFF) アウトライン形式。ReportLab の `TTFont` クラスは CFF アウトラインを未サポート（`TTFError: postscript outlines are not supported`） |
| 対処方針 | Google Fonts から提供される Noto Sans JP（TrueType アウトライン版）を取得。同一フォントファミリー・同一 OFL ライセンス |
| 取得ソース（変更後） | `https://fonts.gstatic.com/s/notosansjp/v56/-F6jfjtqLzI2JPCgQBnw7HFyzSD-AsregP8VFBEj75s.ttf`（Google Fonts Static API 経由） |
| ファイル名 | 当初の合意通り `NotoSansCJKjp-Regular.otf`（拡張子は慣習上 .otf のまま。ReportLab はファイル内容で判断） |
| ファイルサイズ | 約 5.3 MB（CFF 版は 16.4 MB） |
| マジックバイト | `00 01 00 00`（TrueType フォント） |
| ライセンス | SIL Open Font License Version 1.1（変更なし） |

---

## 3. PDF 構成

- ページサイズ: A4 縦（210mm × 297mm）
- 余白: 左右各 15mm、上下各 20mm
- タイトル: `{display_name}　面談日程表`（Noto Sans JP, 14pt）
- テーブル: 時間帯ラベル列（22mm）＋日付列（均等幅）
- セル: 出席番号（数字のみ）または空文字
- 未配置生徒: テーブル下部に「未配置: X, Y, Z」形式で表示
- ヘッダ行: repeatRows=1 により複数ページでも先頭に繰り返される
