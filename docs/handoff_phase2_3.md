# Phase 2.3 引き継ぎメモ

## サマリ

Phase 2.0 で確定した方式に従い、`forms.responses.list` ベースの
**回答ポーリング・パースサービス**と、`FileResponseRepository` の本実装、
および 3 つの受領系 API エンドポイントを追加した。

新規回答は **集合差分（既知 `responseId` 集合）** で抽出し API レスポンスの
並び順に依存しない（リスク (b) 対応）。`HttpError` の `429 / 503` には
**truncated exponential backoff によるリトライ（最大 3 回・初回 1 秒・倍々、
`Retry-After` ヘッダ優先）** を入れ、上限超過時は `PollingRetryExhaustedError`
で API 層が 503 に変換できるようにした（リスク (c) 対応）。

テストは TDD（RED コミット → 11 件全失敗を確認 → 実装 → GREEN）で追加：
- `backend/tests/test_polling.py` 8 件
- `backend/tests/test_responses_api.py` 3 件
- 既存骨格テスト `test_response_repository_methods_raise_not_implemented` は
  実装に置き換わったため削除（Phase 2.1 で `FileProjectRepository` の骨格テストを
  削除したのと同じ扱い）

最終テスト数：**既存 43 - 1 削除 + 新規 11 = 53 件、全 PASS**。

## 採用方式・決定事項

### 1. 全件取得 + 集合差分による未取得検出（リスク (b) 対応）

| 項目 | 採用方針 |
|---|---|
| ページング | `forms.responses.list` を `nextPageToken` が空になるまで反復し**全件取得してから差分処理** |
| 差分検知 | `FileResponseRepository.get_known_form_response_ids(project_id)` が返す既知 `responseId` 集合との `set` 差分 |
| 既知集合の保持 | **インデックスファイルを別途持たず、ディスク上の `responses/<sn>/*.json` を全走査して構築**（プロトタイプ運用で件数が少なく実害なし、状態の二重管理を避ける設計） |
| 順序依存 | **無し**。API が新→古 / 古→新 / シャッフル順 のいずれを返しても結果同一（テスト `test_sync_responses_order_independent_set_diff` で検証） |

### 2. リトライ（リスク (c) 対応）

| パラメータ | 値 | 根拠 |
|---|---|---|
| リトライ対象 | `HttpError.resp.status` が **429** または **503** | `forms_api_research.md` §6（クォータ超過は 429、一時障害は 503） |
| 最大リトライ回数 | `DEFAULT_MAX_RETRIES = 3`（初回含めて最大 4 回呼ぶ） | 60 秒ポーリングで連続 4 回失敗は数分の遅延、ユーザー導線の許容範囲 |
| 初回バックオフ | `INITIAL_BACKOFF_SECONDS = 1.0` 秒 | 1 → 2 → 4 秒の指数 |
| `Retry-After` 優先 | あり（整数秒 or HTTP-date を `_parse_retry_after_header` でパース） | RFC 7231 §7.1.3 準拠 |
| リトライ非対象ステータス | **401 / 403 / 404 / 400 など**はそのまま `HttpError` を再送出 | 認証/権限/構成不備は再試行で解決しない |
| リトライ全消費時 | `PollingRetryExhaustedError`（独自例外）を投げる | API 層で 503 に変換可能、原因切り分けに役立つ |

時間は `time.sleep(...)` で待機。テストでは `patch("app.services.polling.time.sleep")` で待ち無効化。

### 3. 整数バリデーション（API 非対応への対処、Phase 2.0 引き継ぎ）

- 出席番号は `_extract_text_value(answers[student_number_question_id])` で取り出し、
  `int(str(raw_sn).strip())` でパース
- `ValueError` → **当該回答を保存せずスキップし、警告ログ + `skipped_count` カウントアップ**
- 不正回答に対応する `responses/<bad_sn>/` ディレクトリは作られない

### 4. matrix 回答のパース

- `form.json` の `row_question_id_by_date: {date_str: row_qid}` を引き、
  各 `row_qid` に対する `textAnswers.answers[]` の `value`（`HH:MM-HH:MM` 形式）を
  `"-"` で分解して `Availability(date, start, end)` を生成
- `time_slot_labels` との整合確認は本フェーズでは未実装（将来：ラベル不一致を警告ログに）
- `Availability` 構築失敗時は警告ログのみ（その回答全体ではなく該当スロットのみスキップ）

### 5. ファイル名のタイムスタンプ

- **形式**: `<YYYYMMDD_HHMMSS>.json`（requirements.md §3.1 / §4.4 のサンプル準拠）
- **由来**: `Response.submitted_at`（= Forms API の `lastSubmittedTime` → `datetime`）の `strftime("%Y%m%d_%H%M%S")`
- **TZ**: `lastSubmittedTime` は UTC（`Z` 終端の RFC 3339）。本ツールでは UTC のまま
  整形するため、ファイル名は UTC 時刻表記となる。可読性は妥協してログ・トレースの一貫性を優先
- **衝突回避**: 同一秒・同一生徒で複数回答が来た場合は `_NN` の連番サフィックス
  （最大 99 件）。`_MAX_FILENAME_SUFFIX = 99` で安全策

### 6. 生徒名簿モデルの扱い

- **`Project.student_numbers: list[int]` は Phase 1.2 / 2.1 で既に定義済み**
- 拡張不要のため、`FileResponseRepository.get_pending_student_numbers()` は
  `project.json` を `_read_json` で読み出して `Project.model_validate` し、
  `student_numbers` フィールドを直接参照する形で実装
- Repository が他集約のファイルを読む点は Phase 2.1 の `_initialize_project_rules`
  と同じ暫定構造。Phase 3.1 で `RuleRepository` 本実装と合わせてリファクタするか検討予定

### 7. API エンドポイント設計

| メソッド | パス | レスポンスモデル | エラー |
|---|---|---|---|
| POST | `/api/projects/{id}/responses/sync` | `SyncResponsesResult { new_count, skipped_count, errors[] }` | 404（プロジェクト/form.json なし）, 401（認証）, 503（リトライ全消費） |
| GET  | `/api/projects/{id}/responses` | `list[Response]`（出席番号ごとの最新版のみ） | 404 |
| GET  | `/api/projects/{id}/responses/status` | `ResponsesStatusResult { project_id, received[], pending[] }`（昇順ソート） | 404 |

- 例外マッピングは `app/api/responses.py` 内で完結
- 抽象 `ProjectRepository` / `ResponseRepository` を DI（Phase 1.2 方針：差し替え可能性最大化）

## 主要な実装上のパラメータ

| 項目 | 値 | 備考 |
|---|---|---|
| `RETRYABLE_STATUSES` | `{429, 503}` | `app/services/polling.py` |
| `DEFAULT_MAX_RETRIES` | 3 | 初回含め最大 4 回呼び出し |
| `INITIAL_BACKOFF_SECONDS` | 1.0 | 1 → 2 → 4 秒の指数バックオフ |
| ファイル名形式 | `YYYYMMDD_HHMMSS[_NN].json` | UTC 時刻、衝突時 `_NN` 連番 |
| `_MAX_FILENAME_SUFFIX` | 99 | 同一秒・同一生徒で 99 件まで安全 |
| `cache_discovery` | `False` | discovery キャッシュ無効（Phase 2.2 と同じ） |
| テスト総数 | 既存 43 - 1 + 新規 11 = **53 件** | 全 PASS |

## 主要ファイル

### 新規

- **`backend/app/services/polling.py`**（337 行）
  - 例外：`PollingRetryExhaustedError`, `FormNotConfiguredError`
  - 内部ヘルパ：`_parse_retry_after_header`, `_http_error_status`,
    `_http_error_retry_after`, `_list_all_responses`,
    `_extract_text_value`, `_extract_selected_labels`,
    `_parse_availability`, `_parse_response`, `_build_forms_service`
  - 公開：`sync_responses(project_id) -> dict`
- **`backend/app/api/responses.py`**（138 行）
  - `SyncResponsesResult`, `ResponsesStatusResult` Pydantic モデル
  - `sync_project_responses`, `list_project_responses`,
    `get_project_responses_status`
- **`backend/tests/test_polling.py`**（8 件・タイムスタンプ衝突・順序非依存・リトライ網羅）
- **`backend/tests/test_responses_api.py`**（3 件・Repository 直接 + API テスト）

### 変更

- `backend/app/repositories/file_repository.py`
  - `FileResponseRepository` を本実装に置換
    （`save_response` / `list_all` / `list_latest_per_student` /
     `get_received_student_numbers` / `get_pending_student_numbers` /
     `get_known_form_response_ids` の 6 メソッド）
  - `logging.getLogger(__name__)` + 薄いラッパ `logger_warning` を追加
  - `FileProjectRepository` / `FileRuleRepository` / `FileDraftRepository` は無変更
- `backend/app/main.py`
  - `responses_router` を `include_router` で登録（2 行追加）
- `backend/tests/test_repositories.py`
  - `test_response_repository_methods_raise_not_implemented` を削除
  - 削除理由のコメントを追加（Phase 2.1 と同パターン）

### Phase 1.x / 2.1 / 2.2 からの無変更

- `backend/app/models/*`
- `backend/app/repositories/base.py`
- `backend/app/dependencies.py`
- `backend/app/api/auth.py`, `backend/app/api/projects.py`, `backend/app/api/forms.py`
- `backend/app/services/google_auth.py`, `backend/app/services/google_forms.py`
- `backend/app/config.py`
- `backend/tests/conftest.py`, `test_health.py`, `test_google_auth.py`,
  `test_google_forms_service.py`, `test_project_api.py`
- `scripts/*.ps1`, `backend/pyproject.toml`, `.gitignore`, `.gitattributes`

## コミット履歴

```
5f13b6f feat(phase2.3): implement response polling with retry and parsing (GREEN)
f6e7157 test(phase2.3): add response polling and parsing test cases (RED)
```

最終コミットハッシュ（handoff 追加前、HEAD）：`5f13b6fcbab26bb3c01b4af177d25ce25b29b35a`
本ドキュメント追加後の HEAD は `git rev-parse phase2.3-done` で取得可能。

### TDD 厳格検証

RED コミット時点で 11 件全失敗（`ImportError: cannot import name 'polling'`,
`NotImplementedError: Phase 2.3 で実装` 等）を確認した上で test commit を打ち、
その後実装で全 PASS に持ち込んだ。`Check-PhaseDone.ps1` の TDD 厳格検証は
`git checkout f6e7157 && pytest tests/test_polling.py tests/test_responses_api.py`
で実機検証可能。

## 後続サブステップへの引き継ぎ事項

### Phase 3.x（スケジューラ）

- 入力データ取得：`FileResponseRepository.list_latest_per_student(project_id)` で
  各生徒の最新 `Response` を取得し、`response.availability: list[Availability]` を
  CP-SAT モデルの「生徒が可と申告したスロット集合」に変換する
- 未受領生徒（`get_pending_student_numbers`）はスケジューリング対象外とする
  （requirements.md §4.6.1 / Phase 3.3b の API 仕様で除外する想定）
- `Availability` のフィールド：`date: date`, `start: time`, `end: time`
  （Pydantic v2 / `app.models.response.Availability`）

### Phase 4.3（プロジェクト画面と Form 連携 UI）

- ポーリング API は **同期実装**：`POST /api/projects/{id}/responses/sync` は
  最大 4 回 × 数秒待ちで数十秒ブロックする可能性。フロントは
  - ローディング表示
  - タイムアウト 60 秒程度
  - 60 秒ごとの自動ポーリング（requirements.md §4.4）
  を実装する
- レスポンスの `errors[]` は配列でメッセージ列。UI では「不正回答 N 件あり」など
  サマリ表示が望ましい（個別メッセージは debug 表示にとどめる）
- `GET /responses/status` レスポンスは `received[]` / `pending[]` が昇順ソート済み。
  フロント側で追加ソート不要
- 401 受領時は `/api/auth/google` 認証導線へ誘導
- 503 受領時（リトライ全消費）は「Google 側のクォータ超過/一時障害です。しばらく
  待ってから再試行してください」を案内
- 404 + `detail: form.json がありません` → 「先に『Form 作成』ボタンを押してください」を案内

### Phase 6.1（ログ整備）

- `polling.py` は `logging.getLogger(__name__)` を使用済み。`logging_config.py` で
  `RotatingFileHandler` を設定すればそのまま `%APPDATA%\meeting-scheduler\logs\app.log` に流れる
- 警告ログの主な発火箇所：
  - 出席番号パース失敗
  - 行ラベルの `-` セパレータ欠落
  - `Availability` バリデーション失敗
  - `submitted_at` / `responseId` 欠落
  - 壊れた `responses/*.json` ファイル
  - 429/503 リトライ通知

## 未解決の課題・要確認事項

- **要確認**：実機 Forms API で `forms.responses.list` のレスポンス並び順（昇順/降順）
  および `pageSize` の既定値。本実装は順序非依存なため動作は保証されるが、
  Phase 2.0 引き継ぎの「未確認事項」を Phase 2.3 のうちに実機 E2E で観測すべき
- **要確認**：`time_slot_labels` と異なる時間枠ラベルが回答に紛れた場合の挙動。
  現状は `Availability` バリデーションで日付/時刻形式エラーになれば警告ログのみ、
  ラベル不一致はスルー。Phase 4.3 で UI 側に「未知ラベル」警告を出すか検討
- **要確認**：ファイル名の TZ。`lastSubmittedTime` は UTC のため UTC 時刻で保存される。
  日本時間表記とのズレが UI 表示で混乱の元になるなら、Phase 4.3 / Phase 6.1 で
  ローカルタイム表記に変える検討（`Response.submitted_at` 自体は TZ 付きで保存している）
- **保留**：`FileResponseRepository.get_pending_student_numbers` が `project.json` を
  直接読む構造。Phase 3.1 の `FileRuleRepository` 本実装と合わせて、
  「Repository が他集約のファイルを読む」非疎結合性のリファクタを検討
- **保留**：429 リトライ中も同期処理。バックエンドが他の API リクエストを処理しない
  ブロッキング要因にはなる（数秒〜数十秒）。プロトタイプでは許容
- **保留**：複数プロジェクトの並行ポーリング。requirements.md §5.2 では
  「画面表示中のプロジェクトのみ」なので実害なし。フロント側でライフサイクル管理
- **保留**：`PollingRetryExhaustedError` のリトライ回数・初期バックオフは現状ハードコード。
  将来 `Settings` に移すか、環境変数で上書きできるようにするか検討
- **保留**：`save_response` 中のファイル衝突最大 99 件は十分大きいが、極端なバースト
  攻撃 / バグでループ無限化を防ぐ意図。本来は重複そのものを差分検知で防げているため
  実害は無い

## 手動 E2E 確認手順（参考）

1. Phase 1.3 の手順で OAuth 認証完了（`oauth_token.json` を配置）
2. Phase 2.1 でプロジェクト作成、`project_id` を取得
3. Phase 2.2 で `POST /api/projects/{id}/form` を呼んで Form を作成、`responderUri` を取得
4. ブラウザで `responderUri` を開き、出席番号（数字）を入れて 1〜複数の時間枠にチェック → 送信
5. PowerShell で:

   ```powershell
   $pid = "<取得した project_id>"
   Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/projects/$pid/responses/sync"
   # 期待: { new_count = 1, skipped_count = 0, errors = @() }

   Invoke-RestMethod -Uri "http://localhost:8000/api/projects/$pid/responses/status"
   # 期待: received に該当 SN、pending に残り SN

   Invoke-RestMethod -Uri "http://localhost:8000/api/projects/$pid/responses"
   # 期待: 該当 SN の最新 Response 1 件
   ```

6. `%APPDATA%\meeting-scheduler\projects\<project_id>\responses\<出席番号>\*.json` に
   保存され、JSON の `availability` が回答内容と一致すること
7. 同じ出席番号で 2 回目を回答 → 再度 `sync` → `responses/<sn>/` 配下にもう 1 ファイル増えること
   （`list_latest_per_student` 経由の GET レスポンスでは最新版のみ）
8. 不正な出席番号（"abc" など）で回答 → `sync` の `skipped_count` が 1 増え、ログに警告
9. ブラウザで Google アカウントから本ツールの認可を取り消し → `sync` が 401 を返すこと

## 作成ファイル一覧

- `backend/app/services/polling.py`（新規）
- `backend/app/api/responses.py`（新規）
- `backend/tests/test_polling.py`（新規・8 件）
- `backend/tests/test_responses_api.py`（新規・5 件 = 初期 3 件 + idiomatic 化後の回帰 2 件）
- `backend/app/repositories/file_repository.py`（`FileResponseRepository` 本実装）
- `backend/app/main.py`（ルータ登録 2 行追加）
- `backend/tests/test_repositories.py`（骨格テスト 1 件削除）
- `docs/handoff_phase2_3.md`（本ドキュメント）

## 追記：ロガー呼び出しの idiomatic 化と回帰テスト追加

GREEN コミット後、`file_repository.py` 冒頭に置いていた薄いラッパ関数

```python
_logger = logging.getLogger(__name__)

def logger_warning(msg: str) -> None:
    _logger.warning(msg)
```

を削除し、`polling.py` と同じ流儀

```python
logger = logging.getLogger(__name__)
# 呼び出し側は logger.warning("...", arg) を直接使う（lazy formatting）
```

に揃えた。置換箇所：`list_all` 内 2 箇所 + `get_pending_student_numbers` 内 1 箇所、計 3 箇所。

### 経緯

コーディネータ経由で「Pyright が `logger_warning` を未定義として検出している
（NameError リスク）」との指摘を受けた。**ただし `logger_warning` は実際には
`_logger.warning(msg)` を呼ぶ helper 関数として定義済み**であり、Pyright が
それを undefined と判定する状況は通常発生しない（タスク指示にも「Pyright は
`.venv` 未検出による偽陽性が出る」と明記されている）。

したがって NameError は実機では発生しない（GREEN 時点の 53 テストは全 PASS で
あったし、防御パスを通る人工再現テストを追加した後も同じ）。だが指摘の根本である
「ラッパ helper は不要、`logger.warning(...)` を直接呼ぶのが Python 慣習」は
妥当なため、cleanup として idiomatic 化を実施した。あわせて防御パス（
非整数ディレクトリ名・壊れた JSON）の回帰テストを `test_responses_api.py` に
2 件追加し、当該パスが exercise されることを保証した。

### 追加テスト

- `test_list_all_skips_non_integer_student_dir`：`responses/garbage/dummy.json`
  混入時に `list_all` が落ちず、有効回答のみ返すこと
- `test_list_all_skips_broken_json_files`：整数ディレクトリ配下に
  パース不能 JSON を置いても `list_all` がスキップして処理継続すること

これにより防御パス（元コードでも分岐としては存在したが exercise されていなかった）
が回帰テストでカバーされる。テスト総数：**53 + 2 = 55 件、全 PASS**。

タグ `phase2.3-done` は本 cleanup コミット後の HEAD に force 移動済み
（`git tag -f phase2.3-done HEAD`）。

## 追記2：テストファイル名の規約合わせ（リネーム）

Check-PhaseDone.ps1:374 が `backend\tests\test_polling_service.py` を期待していたため、
初期コミット時に作成した `backend\tests\test_polling.py` を `git mv` でリネームした
（履歴追跡保持）。中身・テスト件数（8 件）は無変更。pytest はファイル名で自動収集する
ため、`test_polling_service.py` でも引き続き全件 PASS。`phase2.3-done` タグも本
リネームコミットに force 移動済み。
