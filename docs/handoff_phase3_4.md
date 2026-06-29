# Phase 3.4 引き継ぎメモ

## サマリ

ドラフト保存・ロック管理の本実装を行った。具体的には以下の 3 点。

1. **`FileDraftRepository` 本実装** — Phase 1.2 で骨格として定義していた
   `save_draft` / `get_latest` / `unlock_latest` / `list_all` を
   ファイルベースで実装（スレッドセーフ）。

2. **`Draft.violated_constraints` 型整合** — Phase 1.2 のプレースホルダ
   `list[dict[str, Any]]` を `list[str]` に変更し、
   `SchedulingResult.violated_constraints: list[str]` と型を揃えた。

3. **ドラフト API 3 エンドポイント実装**（`backend/app/api/drafts.py`）
   - `POST /api/projects/{id}/drafts` — 保存・ロック・status 遷移
   - `POST /api/projects/{id}/drafts/unlock` — アンロック・status 復帰
   - `GET  /api/projects/{id}/drafts/latest` — 最新ドラフト取得

TDD (RED commit → 実装 → GREEN) の順序で進めた。
新規テスト 18 件追加（`tests/test_draft_api.py`）、
骨格テスト 1 件削除（`test_draft_repository_methods_raise_not_implemented`）。
最終テスト総数：**122 件、全 PASS**。

---

## 採用方式の決定事項

### ドラフトファイル構造

```
<projects_dir>/<project_id>/drafts/draft_<YYYYMMDD_HHMMSS>.json
```

- ファイル名のタイムスタンプは `draft.saved_at.strftime("%Y%m%d_%H%M%S")`
- 同一秒に複数保存が来た場合は `draft_<YYYYMMDD_HHMMSS>_<NN>.json` で連番回避
  （`_MAX_FILENAME_SUFFIX = 99`）
- ファイル内容は `Draft.model_dump(mode="json")`（UTF-8、BOM なし、`ensure_ascii=False`）

### ロック実装方式

`FileDraftRepository._write_lock = threading.Lock()` をクラス変数として保持し、
`save_draft` と `unlock_latest` の書き込み操作をシリアライズする。

- シングルプロセス・マルチスレッド（uvicorn デフォルト）環境を想定
- プロセス間排他は行わない（プロトタイプ運用で複数プロセス起動は想定外）
- `get_latest` / `list_all` は読み取りのみのため Lock 不要（非クリティカルセクション）

### status 遷移の不変条件

requirements.md §3.2 の3ステータス（`in_progress` / `draft_saved` / `finalized`）に沿う。

| 操作 | 事前 status | 遷移後 | 不正時 |
|---|---|---|---|
| `POST /drafts` | `in_progress` | `draft_saved` | `draft_saved` → 409 |
| `POST /drafts/unlock` | 任意 | `in_progress` | ドラフト不在 → 404 |
| `GET /drafts/latest` | 任意 | 変化なし | ドラフト不在 → 404 |

`finalized` への遷移は Phase 5.x（PDF 出力）の責務（本フェーズでは設定しない）。

### `violated_constraints` 型整合の決定

**`Draft.violated_constraints: list[str]` に統一（Phase 1.2 の `list[dict]` から変更）**

- 決定理由：`SchedulingResult.violated_constraints: list[str]`（Phase 3.2 で確定）
  と揃えることで `SchedulingResult → Draft` の変換が無損失かつ型安全に行える
- `dict` 形式はプレースホルダであり要件上の意味的損失なし
- API ハンドラ層での変換責務：`DraftSaveRequest` は `violated_constraints: list[str]` で
  受け取り、そのまま `Draft` に詰める（変換なし）

### 変換責務の配置

`SchedulingResult → Draft` への変換は **API ハンドラ層**（`drafts.py` の `save_draft`）
で行う。

- サービス層は純粋関数（`solve`）のまま維持（Phase 3.3b の設計方針）
- フロントエンドが `POST /schedule` レスポンスを `POST /drafts` に転送する
  フローを想定（同一スキーマ構造 `DraftSaveRequest` を採用）

### latest 取得時のソート基準

`saved_at` 降順（= `Draft.saved_at` の最大値が latest）。
ファイル名タイムスタンプと `saved_at` は同一値由来だが、JSON 内の `saved_at` を
ソートキーとすることでファイル名の順序依存を排除している。

---

## 最終コミットハッシュ

```
ba0939c7dc6d18a7c3c2d1bd3f02a25437b3b2c3  feat(phase3.4): implement draft save and lock management (GREEN)
badf473...  test(phase3.4): add draft save and lock management tests (RED)
```

---

## 主要な実装上のパラメータ・決定

| 項目 | 値 | 備考 |
|---|---|---|
| ドラフトファイル命名 | `draft_<YYYYMMDD_HHMMSS>.json` | requirements.md §3.1 準拠 |
| 同一秒連番 | `_<NN>` サフィックス（01〜99） | `_MAX_FILENAME_SUFFIX = 99` |
| スレッドセーフ機構 | `threading.Lock`（クラス変数） | シングルプロセス想定 |
| latest 判定基準 | `saved_at` 降順先頭 | ファイル名ではなく JSON フィールド基準 |
| 不正遷移レスポンス | 409 Conflict | status=`draft_saved` での再保存 |
| ドラフト不在レスポンス | 404 Not Found | unlock / latest 取得時 |
| `violated_constraints` 型 | `list[str]` | Phase 1.2 の `list[dict]` から変更 |
| テスト総数 | **122 件** | 全 PASS（+18 新規 / -1 削除） |

---

## 主要ファイル

### 新規

- **`backend/app/api/drafts.py`**（ドラフト API ルータ）
  - `DraftSaveRequest`（リクエストモデル）
  - `save_draft` / `unlock_draft` / `get_latest_draft`（ハンドラ）
- **`backend/tests/test_draft_api.py`**（18 件）

### 変更

- **`backend/app/models/draft.py`**
  - `Draft.violated_constraints` 型を `list[dict[str, Any]]` → `list[str]` に変更
  - `typing.Any` import を削除
- **`backend/app/repositories/file_repository.py`**
  - `FileDraftRepository` を本実装（`save_draft` / `get_latest` / `unlock_latest` / `list_all` / `_load_all_with_paths`）
  - `import threading` を追加
- **`backend/app/main.py`**
  - `drafts_router` を `include_router` で登録（2 行追加）
- **`backend/tests/test_repositories.py`**
  - `test_draft_repository_methods_raise_not_implemented` を削除
  - コメントを Phase 3.4 対応に更新

---

## 後続サブステップへの引き継ぎ事項

### Phase 4.4c（日程案保存と保存完了画面）

フロントエンドの保存フローは以下の通り：

```
POST /api/projects/{id}/schedule  →  SchedulingResult を画面に表示
    ↓（ユーザが「保存」ボタンをクリック）
POST /api/projects/{id}/drafts    →  DraftSaveRequest（同一構造） で保存
    ↓ 成功 → SavedPage へ遷移
POST /api/projects/{id}/drafts/unlock  →  再編集時（「再編集」ボタン）
```

- リクエストボディ `DraftSaveRequest` は `SchedulingResult` と同一フィールド構造なので、
  フロントは `POST /schedule` レスポンスを `POST /drafts` にそのまま転送できる
- 保存成功時のレスポンスは `Draft`（201 Created）

### Phase 5.2（PDF 出力 API・UI）

`GET /api/projects/{id}/drafts/latest` を呼び出して最新ドラフトを取得し、
`Draft.assignments` からマトリクスを構築して PDF を生成する。

- `Draft.assignments: list[Assignment]` の構造：
  `{"student_number": int, "date": "YYYY-MM-DD", "start": "HH:MM:SS", "end": "HH:MM:SS"}`
- Pydantic v2 の `time` シリアライズは `"HH:MM:SS"` 形式（`"HH:MM"` ではない点に注意）

### Phase 4.4a（日程案表示画面）

- `POST /schedule` レスポンスは `SchedulingResult`（ドラフト保存前の一時データ）
- 画面上のドラッグ編集結果を `POST /drafts` で永続化する責務はフロント側

### 全般

- プロジェクト status の `"finalized"` への遷移は Phase 5.x で実装
  （`POST /api/projects/{id}/pdf` の成功時に `draft_saved` → `finalized`）

---

## 未解決の課題・要確認事項

- **保留**：`unlock_latest` はプロジェクト status を無条件に `in_progress` に戻す。
  status が `finalized`（PDF 出力済み）の場合も unlock できてしまう。
  プロトタイプ運用では問題ないが、Phase 5.x 実装時に `finalized` からの
  unlock を禁止するかどうか確認が必要。
- **保留**：`threading.Lock` はクラスレベルなので、すべての `FileDraftRepository`
  インスタンスが同一 Lock を共有する。複数インスタンスが同時に使われる
  ケース（将来のマルチテナント等）では per-instance Lock への変更が必要。
  現プロトタイプはシングルテナントなので問題なし。
- **保留**：過去ドラフトの版は全てファイル残置（requirements.md §4.9）。
  プロジェクトが増えると `drafts/` に大量のファイルが蓄積する可能性。
  Phase 6.2 でクリーンアップ方針を検討すること。
- **保留**：`DraftSaveRequest.save_draft_when_status_draft_saved_returns_409` の
  挙動について、フロントエンドが 409 を受け取った際の UX（「先にアンロックしてください」
  などのメッセージ表示）は Phase 4.4c で実装する際に確認。

---

## 追記：テストファイル名の規約合わせ（リネーム）

Check-PhaseDone.ps1 が backend\tests\test_drafts_api.py（複数形）を期待していたため、
初期コミット時に作成した test_draft_api.py を git mv でリネームした（履歴追跡保持）。
中身・テスト件数（18 件）は無変更。pytest はファイル名で自動収集するため、
test_drafts_api.py でも引き続き全件 PASS。phase3.4-done タグも本リネームコミットに
force 移動済み。
