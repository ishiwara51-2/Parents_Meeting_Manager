# Phase 5.1 引き継ぎメモ

## サマリ

ドラフト JSON から A4 縦・マトリクス形式の PDF を生成する `generate_pdf` サービスを実装した。

TDD（RED commit → 実装 → GREEN）の順序を厳守した。

実装内容：
1. `backend/pyproject.toml` に `reportlab>=4.0` と `pypdf>=4.0` を追加
2. `backend/app/fonts/NotoSansCJKjp-Regular.otf`（TrueType 版）を配置
3. `backend/app/fonts/OFL.txt`（SIL Open Font License v1.1）を配置
4. `backend/app/services/pdf_generator.py` を新規作成
5. `backend/tests/test_pdf_generator.py` を新規作成（4 件）
6. `docs/pdf_decisions.md` を新規作成
7. `docs/samples/sample.pdf` を生成（手動確認用）
8. `README.md` に Noto Sans JP アトリビューション追記

新規テスト 4 件追加。最終テスト総数：**126 件、全 PASS**。

---

## 採用方式の決定事項

### フォント差し替えの経緯と最終構成

| 項目 | 詳細 |
|---|---|
| 当初指定 | `implementation_prompts_subdivided.md` L899 で IPAex ゴシック（`.ttf`） |
| ユーザー変更 | Noto Sans CJK JP（OFL）に差し替え、ファイル名 `NotoSansCJKjp-Regular.otf` |
| 問題 | noto-cjk の OTF は PostScript (CFF) アウトライン形式。ReportLab `TTFont` が未対応（`TTFError: postscript outlines are not supported`） |
| 解決策 | Google Fonts Static API から Noto Sans JP（TrueType アウトライン版）を取得して配置 |
| 最終フォント | Noto Sans JP v56, TrueType アウトライン, ~5.3MB, SIL OFL 1.1（Google/Adobe） |
| ファイル名 | `NotoSansCJKjp-Regular.otf`（合意通り。拡張子は慣習。ReportLab はバイナリ形式で判断） |

### PDF レイアウト

- A4 縦（210mm × 297mm）、余白: 左右 15mm、上下 20mm
- タイトル: `{display_name}　面談日程表`（Noto Sans JP 14pt）
- マトリクス: 行 = 時間帯スロット、列 = 候補日付
- 列幅: 時間帯ラベル列 22mm + 日付列均等分割（残幅 158mm を等分）
- 未配置生徒: テーブル下に「未配置: X, Y, Z」形式で表示

### 1ページ超過時の採用方針

列数（候補日数）に応じてセルフォントサイズを自動縮小（9pt → 最小 6pt）し、
列幅は均等分割で対応。通常の 3〜5 日ならば 1 ページに収まる。
それ以上は ReportLab Platypus の自動改ページに委ねる（`repeatRows=1` でヘッダ行を各ページ先頭に繰り返す）。
詳細は `docs/pdf_decisions.md` 参照。

---

## 最終コミットハッシュ

```
acd25bff70a75991d6b5551732f2ab7ead2f4f47  feat(phase5.1): implement pdf_generator service (GREEN)
5c47fce...  test(phase5.1): add pdf_generator test cases (RED)
e840acd...  chore(phase5.1): add reportlab dep and Noto Sans CJK JP font + OFL
```

タグ `phase5.1-done` は handoff docs 追加後のコミットを指す。

---

## 主要な実装上のパラメータ・決定

| 項目 | 値 | 備考 |
|---|---|---|
| フォント名 | `NotoSansCJKjp` | `pdfmetrics.registerFont` で登録 |
| フォントファイル | `backend/app/fonts/NotoSansCJKjp-Regular.otf` | TrueType アウトライン（実態は .ttf） |
| フォント登録 | モジュールレベルフラグでプロセス内 1 度のみ | `_font_registered` フラグ |
| タイトルフォントサイズ | 14pt | |
| ヘッダ行フォントサイズ | 9pt | |
| セルフォントサイズ | 9〜6pt（列数で自動調整） | 最小 6pt |
| 時間帯ラベル列幅 | 22mm | 固定 |
| 日付列幅 | 均等分割（残り 158mm を等分） | |
| PDF ページサイズ | A4 縦 | 210×297mm |
| テスト総数 | **126 件** | 全 PASS（+4 新規） |

---

## 主要ファイル

### 新規

- `backend/app/services/pdf_generator.py`: `generate_pdf(Project, Draft) -> bytes`
- `backend/tests/test_pdf_generator.py`: 4 件のテスト
- `backend/app/fonts/NotoSansCJKjp-Regular.otf`: Noto Sans JP（TrueType 版）
- `backend/app/fonts/OFL.txt`: SIL OFL 1.1 ライセンス全文
- `docs/pdf_decisions.md`: 1 ページ超過時の決定事項等
- `docs/samples/sample.pdf`: 手動確認用サンプル（3 日×5 コマ）

### 変更

- `backend/pyproject.toml`: `reportlab>=4.0`、`pypdf>=4.0` 追加
- `README.md`: Noto Sans JP のアトリビューション追記

---

## 後続サブステップ（Phase 5.2）への引き継ぎ事項

### Phase 5.2（PDF 出力 API・UI）

`generate_pdf` のシグネチャ:

```python
from app.models import Project
from app.models.draft import Draft
from app.services.pdf_generator import generate_pdf

pdf_bytes: bytes = generate_pdf(project, draft)
```

API 側での利用手順（`GET /api/projects/{id}/pdf`）:

```python
# 1. 最新ドラフトを取得
draft = draft_repo.get_latest(project_id)  # Draft | None

# 2. プロジェクト情報を取得
project = project_repo.get(project_id)     # Project | None

# 3. PDF 生成
pdf_bytes = generate_pdf(project, draft)

# 4. レスポンス（FastAPI）
from fastapi.responses import Response
return Response(
    content=pdf_bytes,
    media_type="application/pdf",
    headers={"Content-Disposition": f'attachment; filename="schedule_{project_id}.pdf"'}
)
```

- ドラフト不在 → 404 を返すこと
- プロジェクト不在 → 404 を返すこと
- `status` を `draft_saved` → `finalized` に遷移させること（requirements.md §3.4 引き継ぎより）

### SavedPage.tsx の handleDownloadPdf（Phase 4.4c スタブ）

- `frontend/src/pages/SavedPage.tsx` の `handleDownloadPdf` 関数を実装に置き換える
- `GET /api/projects/{id}/pdf` を呼び出して Blob ダウンロードを行う

---

## 未解決の課題・要確認事項

- **承認待ち**: Phase 5.1 は承認ポイント（`Check-PhaseDone.ps1` の `$ApprovalPhases` に含まれる）。
  ユーザーによる PDF レイアウトの実機確認と承認が必要。
- **フォント変更の経緯記録**: noto-cjk の OTF (CFF) → Google Fonts の Noto Sans JP (TrueType) に
  差し替えた経緯を `docs/pdf_decisions.md` に記録済み。
  フォントファイルの URL（Google Fonts Static API）は将来変更される可能性がある。
  再取得が必要な場合は `pdf_decisions.md` §2 の手順を参照すること。
- **保留**: `generate_pdf` は現時点でエラーハンドリングを最小限に留めている。
  `draft.assignments` が空の場合は空テーブルが描画される（エラーにはならない）。
  Phase 5.2 で API を実装する際に空ドラフトの扱いを確認すること。
