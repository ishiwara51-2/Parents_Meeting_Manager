# Phase 2.1 引き継ぎメモ

## サマリ

`FileProjectRepository` を本実装に置き換え、`POST/GET/PUT/DELETE /api/projects`
の CRUD を Pydantic v2 + FastAPI で実装した。
プロジェクト作成時は以下を 1 リクエストで完結させる：

- `<projects_dir>/<project_id>/` ディレクトリ作成
- サブディレクトリ `responses/`, `drafts/`, `output/` 作成
- `project.json` 書き出し
- `rules.json` 初期化（グローバルルールがあれば複製、無ければ既定値）

テストは新規 9 件追加し、TDD（RED → 6 件失敗を確認 → test commit →
実装 → GREEN）の順序で進めた。既存 Phase 1.2 のスモーク
`test_project_repository_methods_raise_not_implemented` は本実装に置き換わったため削除。

## 採用方式・決定事項

### `project_id` 採番方式

**UUID4 16 進無印形式（`uuid.uuid4().hex`、32 文字）を採用。**

| 観点 | 判断 |
|---|---|
| 衝突可能性 | 実質ゼロ。複数同時作成でもロック不要 |
| ディレクトリ名安全性 | ハイフン無しの英数のみ。Windows パス制約と相性が良い |
| URL 安全性 | エスケープ不要、ASCII のみ |
| 視認性 | UUID なので人間には覚えづらいが、フロント側で `display_name` を主表示にする想定（requirements.md §4.2） |
| 連番案の検討 | ファイルシステム上のグローバルカウンタが必要となり、複数プロセス／同時操作で衝突管理が必要なため不採用 |

実装場所：`backend/app/api/projects.py` の `_generate_project_id()`。

### `created_at` の生成

サーバ側で `datetime.now(timezone.utc).astimezone()` を呼び、
ローカルタイムゾーン付き `datetime` として `Project.created_at` に格納する
（requirements.md §3.2 の「TZ 付き ISO 8601」要件を満たす）。

### デフォルト `rules.json` の構造

Phase 2.1 暫定実装（Phase 3.1 でグローバルルール管理 API を実装した時に
`FileRuleRepository.get_global_rules()` 側の初期化に移管予定）：

```python
Rules(
    global_constraints=GlobalConstraints(
        max_consecutive_slots=4,
        forced_break_slots=1,
        max_slots_per_day=20,
        teacher_unavailable=[],
    ),
    student_constraints=[],
)
```

既存の `Rules` / `GlobalConstraints` モデル（Phase 1.2 で定義）の必須フィールドを
全て埋める形で既定値を設定。タスク指示にあった
`{duration_minutes_default, slot_minutes, duration_multipliers}` というフィールド名は
既存モデルに存在しないため不採用（モデル変更は Phase 1.2 の方針を踏襲し最小限）。

書き出し時：
- グローバルルール `<config_dir>/global_rules.json` が存在すれば
  `Rules.model_validate()` を通してから複製
- 存在しなければ上記既定値で初期化
- 文字エンコード：UTF-8 (BOM なし)、`ensure_ascii=False`、`indent=2`

### API リクエスト/レスポンス設計

| メソッド | パス | リクエスト | レスポンス |
|---|---|---|---|
| POST | `/api/projects` | `ProjectCreateRequest`（`project_id`/`created_at` 不要） | 201 + `Project` 全フィールド |
| GET | `/api/projects` | – | 200 + `list[Project]` 作成日時降順 |
| GET | `/api/projects/{id}` | – | 200 + `Project` / 404 |
| PUT | `/api/projects/{id}` | `ProjectUpdateRequest`（`project_id`/`created_at` 不要） | 200 + `Project` 更新後 / 404 |
| DELETE | `/api/projects/{id}` | – | 204 No Content / 404 |

- `project_id` と `created_at` は不変。PUT で受け取っても無視。`Project` モデル
  自体は `extra="forbid"` のため、リクエストモデルを `Project` から
  分離する形で実装（`ProjectCreateRequest` / `ProjectUpdateRequest`）
- 422 はバリデーション失敗時に Pydantic v2 が自動応答（FastAPI 標準）
- 404 は本ハンドラで `HTTPException(404, ...)` を明示送出
- `Response` クラスを 204 で使う場合、FastAPI で `response_class=Response` を
  併用しないと `response_model` 推論で body 整形が走るため明示している

### Repository の例外仕様

| メソッド | 例外 | API ハンドラ側での扱い |
|---|---|---|
| `create()` | 既存 `project_id` で `FileExistsError` | UUID 自動採番のため理論上発生しない |
| `update()` | 不在で `FileNotFoundError` | API 側で先に `get()` で 404 判定するため到達しない |
| `delete()` | 不在で `FileNotFoundError` | API 側で先に `get()` で 404 判定するため到達しない |

## 主要な実装上のパラメータ

| 項目 | 値 | 備考 |
|---|---|---|
| project_id 形式 | UUID4 16 進無印（32 文字） | `uuid.uuid4().hex` |
| created_at 形式 | TZ 付き `datetime` | `datetime.now(timezone.utc).astimezone()` |
| 既定 status | `"in_progress"` | `ProjectCreateRequest.status` のデフォルト |
| 既定 ルール | `max_consecutive_slots=4, forced_break_slots=1, max_slots_per_day=20, teacher_unavailable=[]` | Phase 2.1 暫定。Phase 3.1 で API 化 |
| サブディレクトリ | `responses/`, `drafts/`, `output/` | `FileProjectRepository.SUBDIR_NAMES` |
| JSON 書式 | UTF-8 (BOM なし) / `ensure_ascii=False` / `indent=2` | `_write_json` ヘルパ |
| 一覧ソート | `created_at` 降順 | `FileProjectRepository.list_all()` |
| テスト総数 | 既存 27 - 1 削除 + 新規 9 = 35 件 | 全 PASS |

## 主要ファイル

### 新規

- `backend/app/api/projects.py`：プロジェクト管理ルータ
  - `ProjectCreateRequest`, `ProjectUpdateRequest`
  - `create_project / list_projects / get_project / update_project / delete_project`
  - `_generate_project_id`, `_now_local_aware`
- `backend/tests/test_project_api.py`：API テスト 9 件

### 変更

- `backend/app/repositories/file_repository.py`
  - `FileProjectRepository` を本実装に（`list_all / get / create / update / delete / get_project_dir`）
  - サブディレクトリ自動作成と `rules.json` 初期化を `create()` 内で実施
  - `_DEFAULT_RULES` 定数、`_write_json` / `_read_json` ヘルパを追加
  - `FileRuleRepository / FileResponseRepository / FileDraftRepository` は骨格維持
- `backend/app/main.py`：`projects_router` を `include_router` で登録
- `backend/tests/test_repositories.py`：Phase 1.2 のスモーク
  `test_project_repository_methods_raise_not_implemented` を削除（本実装に置き換わったため）

### Phase 1.x からの無変更ファイル

- `backend/app/models/*`（モデル変更なし）
- `backend/app/config.py`
- `backend/app/dependencies.py`
- `backend/app/api/auth.py` / `backend/app/services/google_auth.py`
- `backend/tests/conftest.py` / `test_health.py` / `test_google_auth.py`
- `scripts/*`, `.gitignore`, `.gitattributes`, `backend/pyproject.toml`

## コミット履歴

```
3ee4d0e feat(phase2.1): implement project crud api (GREEN)
c54f542 test(phase2.1): add project crud api test cases (RED)
```

RED コミット時点では新規 9 件のうち 6 件が失敗（404 = ルータ未登録による）、
3 件（存在しない id への GET/PUT/DELETE）は FastAPI が 404 を返すため
偶発的に PASS したが、pytest 全体としては exit code 1 のため
`Check-PhaseDone.ps1` の TDD 厳格検証 (`tdd_strict_red`) は PASS 判定となる想定。

最終コミットハッシュ（handoff 追加前）：`3ee4d0e8b635f3d5624d1723dc09e3373d38799d`
本ドキュメント追加後の HEAD は `git rev-parse phase2.1-done` で取得可能。

## 後続サブステップへの引き継ぎ事項

### Phase 2.2（Google Form 作成）

- `POST /api/projects/{id}/form` のハンドラは Phase 2.1 で確立した
  `Depends(get_project_repository)` パターンを踏襲する
- `repo.get(project_id)` で 404 ガード → `Project.candidate_dates` /
  `candidate_time_slots` / `student_numbers` を Forms API リクエストに変換
- `form.json` の保存先は `<project_dir>/form.json`（`FileProjectRepository.get_project_dir(project_id)` で取得可能）
- 認証は `google_auth.get_valid_credentials()` を使い、未認証は 401

### Phase 2.3（回答ポーリング）

- `responses/` サブディレクトリは Phase 2.1 でプロジェクト作成時に作っているため
  `FileResponseRepository.save_response()` 側は出席番号サブディレクトリの
  `mkdir(parents=True, exist_ok=True)` だけ気にすればよい
- `FileResponseRepository` 自体はまだ骨格のまま（Phase 2.3 で実装）

### Phase 3.1（ルール管理 API）

- **重要**：本フェーズで `FileProjectRepository._initialize_project_rules()` が
  `<config_dir>/global_rules.json` を直接読んでいる。Phase 3.1 で
  `FileRuleRepository.copy_global_to_project()` が本実装になったら、
  API ハンドラ（`create_project`）側でプロジェクト作成成功後に
  `rule_repo.copy_global_to_project(project_id)` を呼ぶ形に置き換え、
  `_initialize_project_rules()` は削除または `RuleRepository` への委譲に縮退させる
- グローバルルール既定値（`_DEFAULT_RULES`）は本フェーズで `file_repository.py` 内に
  ハードコードされているが、Phase 3.1 では `FileRuleRepository.get_global_rules()` の
  初期化フォールバックに移管する想定。`Rules` モデルの必須フィールドは Phase 1.2 のまま

### Phase 3.4（ドラフト保存）

- `drafts/` サブディレクトリは Phase 2.1 で作成済み。`FileDraftRepository.save_draft()` は
  そのディレクトリ配下に `draft_<YYYYMMDD_HHMMSS>.json` を書き出すだけでよい

### Phase 4.x（フロントエンド）

- プロジェクト作成リクエスト JSON 構造は `ProjectCreateRequest`：
  ```json
  {
    "display_name": "3年A組 7月面談",
    "slot_minutes": 20,
    "candidate_dates": ["2026-07-15"],
    "candidate_time_slots": [{"start": "16:00", "end": "16:20"}],
    "student_numbers": [1, 2, 3]
  }
  ```
  `status` は省略可（既定 `"in_progress"`）
- 一覧 API は作成日時降順なので、フロントは追加ソート不要
- 削除は 204 No Content（レスポンスボディなし）

## 未解決の課題・要確認事項

- **要確認**：プロジェクト ID が UUID4 で人間に覚えづらい点は、フロントで
  `display_name` を主表示にすれば実用上問題ない。万一「URL を共有して
  プロジェクトを開きたい」ユースケースが追加されたら、`project_id` に
  人間可読な suffix を追加するか別途検討（Phase 4.2 で UX 要件を確認）
- **保留**：`copy_global_to_project` の呼び出し責務は Phase 3.1 で
  `FileProjectRepository` から API 層 → `RuleRepository` に移す予定。
  現状の Phase 2.1 暫定実装（Repository が `config_dir` を直接読む）は
  「Repository が他の集約のファイルを参照する」点で疎結合とは言いがたい。
  Phase 3.1 でリファクタする旨を本ドキュメントに明記する
- **保留**：`Project.candidate_time_slots` / `student_numbers` の妥当性
  （例：時間枠が重複しないこと、出席番号が正整数であること）は
  Pydantic 標準バリデーションのみで、業務的な交差検証は未実装。
  Phase 4.2 のフォーム UI 実装時か Phase 3.2 のスケジューラ実装時に再検討
- **保留**：プロジェクト数が増えた場合の `list_all()` 性能。
  全 `project.json` を毎回 Pydantic でパースするため、数百件オーダーで
  遅延が出る可能性。プロトタイプ運用（1 教師 / 数十件）では問題なし

## 動作確認手順

```powershell
# 開発サーバ起動
pwsh .\scripts\start-dev.ps1

# プロジェクト作成
$body = '{"display_name":"3年A組 7月面談","slot_minutes":20,"candidate_dates":["2026-07-15"],"candidate_time_slots":[{"start":"16:00","end":"16:20"}],"student_numbers":[1,2,3]}'
$resp = Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/projects -Body $body -ContentType "application/json"
$resp.project_id

# 一覧取得
Invoke-RestMethod -Uri http://localhost:8000/api/projects

# 詳細取得
Invoke-RestMethod -Uri "http://localhost:8000/api/projects/$($resp.project_id)"

# 更新
$update = '{"display_name":"3年A組 7月面談（更新）","slot_minutes":30,"candidate_dates":["2026-07-15"],"candidate_time_slots":[{"start":"16:00","end":"16:30"}],"student_numbers":[1,2,3],"status":"in_progress"}'
Invoke-RestMethod -Method Put -Uri "http://localhost:8000/api/projects/$($resp.project_id)" -Body $update -ContentType "application/json"

# 削除
Invoke-RestMethod -Method Delete -Uri "http://localhost:8000/api/projects/$($resp.project_id)"

# 自動テスト
.\backend\.venv\Scripts\python.exe -m pytest backend\tests -v
```

`%APPDATA%\meeting-scheduler\projects\<UUID>\` 配下に
`project.json` / `rules.json` / `responses/` / `drafts/` / `output/` が
作られていれば成功。
