# Phase 2.2 引き継ぎメモ

## サマリ

Phase 2.0 で確定した **matrix 方式**（`QuestionGroupItem` + `Grid.columns.type=CHECKBOX`）で
Google Form を生成する `POST /api/projects/{id}/form` と、生成済みメタ情報を返す
`GET /api/projects/{id}/form` を実装した。

実 Google API 呼び出しは `googleapiclient.discovery.build("forms", "v1", credentials=...)`
を介し、認証は Phase 1.3 の `google_auth.get_valid_credentials()`（期限切れ自動
リフレッシュ）に委譲する。本フェーズでは Google API モック前提の自動テスト 8 件を
TDD（RED → test commit → 実装 → GREEN）で追加し、既存 35 件 + 新規 8 件 = **43 件全 PASS**。

実 Google アカウントでの E2E 確認は本ドキュメントでは未実施（手動 E2E はユーザー作業）。

## 採用方式・決定事項

### Form 構造（matrix）

| 要素 | 採用方式 |
|---|---|
| Form タイトル | `project.display_name` |
| 質問 0（出席番号） | `TextQuestion(paragraph=False)` + `required=True`、`title="出席番号（半角数字）"`、`description="あなたの出席番号を入力してください"` |
| 質問 1（候補日時） | `QuestionGroupItem` + `Grid` |
| Grid.columns.type | `CHECKBOX`（複数選択可） |
| Grid.columns.options | 各時間枠の `HH:MM-HH:MM` ラベル（`TimeSlot.start` / `TimeSlot.end` から `strftime("%H:%M")`） |
| Grid.shuffleQuestions | `false`（候補日順を維持） |
| 各 row | `rowQuestion.title=<候補日 ISO 文字列>`、`required=True` |
| API 呼び出し順序 | `forms.create`（タイトルのみ）→ `forms.batchUpdate`（`createItem` 2 件） |

### `row_question_id_by_date` の解決戦略（リスク (a) への防御）

Phase 2.0 で残された未確認事項：「`batchUpdate` 応答の `createItem.questionId[]` に
matrix 行 questionId が含まれるか」に対し、**両ケース対応の二段構え**を採用：

1. **batchUpdate 応答に行 questionId が揃っていれば**：そのまま候補日順 zip で
   `{date_str: qid}` を構築（`forms.get` は呼ばない）
2. **応答に含まれない（空配列 / 要素不足）場合**：`forms.get(formId)` を 1 回呼び、
   `items[].questionGroupItem.questions[]` を走査して `rowQuestion.title` と
   `questionId` をペアリングし `{date_str: qid}` を構築

判定式（`google_forms.create_form()` 内）::

    row_qids = _extract_row_qids_from_batch(batch_response)
    if len(row_qids) == len(candidate_dates) and all(q for q in row_qids):
        # 省略パス
        row_question_id_by_date = dict(zip(candidate_dates, row_qids))
    else:
        # フォールバック
        row_question_id_by_date = _extract_row_qids_from_form(
            forms_api.get(formId=form_id).execute(),
            candidate_dates=candidate_dates,
        )

両分岐とも自動テストで検証（`test_forms_get_called_to_resolve_row_question_ids` /
`test_forms_get_skipped_when_batch_response_includes_row_question_ids`）。

### `form.json` スキーマ（FormInfo）

`<project_dir>/form.json` の JSON キー命名（**camelCase / snake_case 混在**、
Phase 2.0 引き継ぎに準拠）::

```json
{
  "formId": "FAKE_FORM_ID",
  "responderUri": "https://docs.google.com/forms/d/FAKE_FORM_ID/viewform",
  "editUri": "https://docs.google.com/forms/d/FAKE_FORM_ID/edit",
  "student_number_question_id": "QID_SN",
  "row_question_id_by_date": {
    "2026-07-15": "QID_ROW_0",
    "2026-07-16": "QID_ROW_1"
  },
  "time_slot_labels": ["16:00-16:20", "16:20-16:40"]
}
```

| キー | 型 | 由来 |
|---|---|---|
| `formId` | str | Forms API `create` 応答 |
| `responderUri` | str | Forms API `create` 応答（無ければ空文字） |
| `editUri` | str | **本サービスで構築**（`https://docs.google.com/forms/d/<formId>/edit`）。Forms API は返さない |
| `student_number_question_id` | str | `batchUpdate` 応答 `replies[0].createItem.questionId[0]` |
| `row_question_id_by_date` | `dict[str, str]` | 上記「二段構え」で構築。キーは候補日 ISO 文字列 |
| `time_slot_labels` | `list[str]` | Form 生成時に使った時間枠ラベル列。Phase 2.3 のパースで整合確認に使う |

Pydantic v2 では `populate_by_name=True` + `Field(..., alias="formId")` の組み合わせで、
Python 側 `form_info.form_id` ↔ JSON 側 `"formId"` を両方向で扱う。
保存時は `model_dump(mode="json", by_alias=True)`、読込時は `FormInfo.model_validate(...)`。

### `editUri` の構築

Google Forms API は **edit URL を直接返さない**ことを実装中に確認
（`forms.create` / `forms.get` のレスポンス型 `Form` に edit 系フィールドなし）。
慣例的なパターン `https://docs.google.com/forms/d/<formId>/edit` で組み立てる。
実機 E2E で URL が有効に開けるかは要確認。

### 二重作成防止

`POST /api/projects/{id}/form` は Google API 呼び出し**前**に
`FileProjectRepository.has_form(project_id)` で `form.json` の存在を判定。
既存なら 409 Conflict を返し、Google 側に重複した実 Form を作らない。

### 認証フロー

- `google_forms.create_form()` 内で `google_auth.get_valid_credentials()` を呼ぶ
  （期限切れトークンは自動リフレッシュ＋ディスク再保存）
- トークン未保存 / リフレッシュ失敗時は `GoogleAuthRequiredError` を投げる
- API ハンドラ `create_project_form()` で `GoogleAuthRequiredError` を捕捉し
  401 Unauthorized に変換

### `discovery.build` の `cache_discovery=False`

`build("forms", "v1", credentials=..., cache_discovery=False)` で `discovery.cache` の
ファイル書込みを無効化（プロセス起動毎に小さなオーバーヘッドが発生するが、
書込み先パーミッション問題を回避するための設定）。

## 主要な実装上のパラメータ

| 項目 | 値 | 備考 |
|---|---|---|
| Form タイトル | `project.display_name` | 例：「3年A組 7月面談」 |
| 出席番号質問 title | `"出席番号（半角数字）"` | 日本語 UI 文言は許容（共通指示） |
| 出席番号質問 description | `"あなたの出席番号を入力してください"` | バリデーション補助テキスト |
| matrix タイトル | `"参加可能な日時にチェックを入れてください（複数選択可）"` | |
| 時間枠ラベル形式 | `"%H:%M-%H:%M"` | Phase 2.3 で `label.split("-")` でパース予定 |
| 候補日キー形式 | `date.isoformat()` = `"YYYY-MM-DD"` | `row_question_id_by_date` のキーも同形式 |
| `form.json` パス | `<projects_dir>/<project_id>/form.json` | `FileProjectRepository.FORM_FILE_NAME = "form.json"` |
| テスト総数 | 既存 35 + 新規 8 = 43 件 | 全 PASS |
| Google API モック | `app.services.google_forms.build` + `google_auth.get_valid_credentials` を `unittest.mock.patch` | 実 API 通信なし |

## 主要ファイル

### 新規

- `backend/app/services/google_forms.py`：Form 作成サービス
  - 例外：`GoogleAuthRequiredError`
  - 内部ビルダ：`_format_time_slot_label`, `_build_student_number_item`,
    `_build_matrix_item`, `_build_batch_update_body`
  - 内部パーサ：`_extract_student_number_qid`,
    `_extract_row_qids_from_batch`, `_extract_row_qids_from_form`
  - 内部 URL：`_build_edit_uri`
  - 内部クライアント：`_build_forms_service`
  - 公開：`create_form(project) -> FormInfo`
- `backend/app/api/forms.py`：Form 関連 API ルータ
  - `POST /api/projects/{id}/form` → `create_project_form`
  - `GET  /api/projects/{id}/form` → `get_project_form`
  - DI ヘルパ：`_get_file_project_repository`（`FileProjectRepository` 具象限定）
- `backend/tests/test_google_forms_service.py`：8 テストケース

### 変更

- `backend/app/models/form.py`：Phase 1.2 骨格 → Phase 2.2 用フィールドに差し替え
  （`form_id` / `responder_uri` / `edit_uri` / `student_number_question_id` /
  `row_question_id_by_date` / `time_slot_labels`、JSON は alias で camelCase 維持）
- `backend/app/repositories/file_repository.py`：`FileProjectRepository` に
  `has_form` / `get_form_info` / `save_form_info` と `FORM_FILE_NAME` /
  `_form_json_path` を追加（既存メソッド・他 Repository は無変更）
- `backend/app/main.py`：`forms_router` を `include_router` で登録（2 行追加）

### Phase 1.x / 2.1 からの無変更

- `backend/app/services/google_auth.py`
- `backend/app/repositories/base.py`
- `backend/app/dependencies.py`
- `backend/app/api/auth.py`, `backend/app/api/projects.py`
- `backend/tests/conftest.py`, `test_health.py`, `test_google_auth.py`,
  `test_project_api.py`, `test_repositories.py`
- `scripts/*.ps1`, `backend/pyproject.toml`, `.gitignore`, `.gitattributes`

## コミット履歴

```
e8ad8e6 feat(phase2.2): implement google form creation with matrix questions (GREEN)
9bb3823 test(phase2.2): add google forms creation test cases (RED)
```

最終コミットハッシュ（handoff 追加前、HEAD）：`e8ad8e65e24a4fbe429a99ae7df4b98860557eda`
本ドキュメント追加後の HEAD は `git rev-parse phase2.2-done` で取得可能。

## 後続サブステップへの引き継ぎ事項

### Phase 2.3（回答ポーリング・パース）

- **必読**：`docs/forms_api_research.md` §4 / §5 / §8
- `form.json` 読み出し：`FileProjectRepository.get_form_info(project_id) -> FormInfo | None`
- パース時に使うフィールド：
  - `form_info.form_id` → `forms.responses.list(formId=...)` の引数
  - `form_info.student_number_question_id` → 回答 `answers[<qid>].textAnswers.answers[0].value`
    を `int(...)` でパース
  - `form_info.row_question_id_by_date` → 各候補日について
    `answers[<row_qid>].textAnswers.answers[]` の `value` 配列を「チェックされた時間枠ラベル」として取得
  - 時間枠ラベルは `HH:MM-HH:MM`、`label.split("-")` で `start` / `end` に分解
  - `form_info.time_slot_labels` は Form 生成時のラベル列。回答中に未知のラベルが
    現れたら警告ログ（不整合検知）
- `forms.responses.list` 呼び出し時の credentials も `google_auth.get_valid_credentials()` で取得
- 整数バリデーション失敗（ValueError）時は警告ログ + スキップ（`responses/<sn>/` を作らない）
- 429 リトライは truncated exponential backoff（最低 1 回）

### Phase 4.3（プロジェクト画面とForm連携UI）

- `POST /api/projects/{id}/form` のレスポンススキーマ（成功 201）::

  ```json
  {
    "formId": "1AbCdEf...",
    "responderUri": "https://docs.google.com/forms/d/.../viewform",
    "editUri": "https://docs.google.com/forms/d/.../edit",
    "student_number_question_id": "00000001",
    "row_question_id_by_date": { "2026-07-15": "00000002", ... },
    "time_slot_labels": ["16:00-16:20", ...]
  }
  ```

  フロント側で `responderUri` を **URL 表示 + コピー** UI に流用する。
  `editUri` は教師が後で Form を直接編集する導線として表示しても良い。
- `GET /api/projects/{id}/form` は同じスキーマで 200、未作成なら 404
- 401 を受け取った場合は「認証してください」を案内し `/api/auth/google` へ誘導
- 409 を受け取った場合は「既に Form が作成されています」と GET にフォールバックして
  既存 `responderUri` を表示するのが UX 上自然

### Phase 1.2 系（モデル / Repository）への影響

- `FormInfo` モデルのフィールドを Phase 1.2 骨格から差し替えた。`app/models/__init__.py`
  の `FormInfo` 再エクスポートは維持
- `FileProjectRepository` に Form 関連メソッドを追加したが、`ProjectRepository` 抽象
  には Form メソッドを足していない（将来 DB 化時の互換性のため、現状は具象限定）。
  必要に応じて Phase 3.x で `FormRepository` 抽象を切り出すことを検討

## 未解決の課題・要確認事項

- **要確認（実機 E2E 時）**：`batchUpdate` の応答に matrix 行 `questionId` が
  実際に含まれるかどうか。本実装は両分岐どちらでも動作するが、実機挙動を観測したら
  本ドキュメントを更新する
- **要確認（実機 E2E 時）**：構築した `editUri`（`https://docs.google.com/forms/d/<id>/edit`）
  が実際に編集可能 URL として有効に開けるか。Forms API リファレンスに edit URL の
  公式パターン定義は無いため慣例値を採用している
- **保留**：`forms.responses.list` のページング動作（Phase 2.3 で対応）。
  matrix 列 = チェックボックス時の `textAnswers.answers[]` の順序は **保護者が
  チェックした順**になる可能性があり、`time_slot_labels` の順序と一致しないため
  Phase 2.3 のパースでは順序に依存しない実装が必要
- **保留**：複数候補日に同じ日付が含まれる場合の挙動（現状は最後の qid で上書き）。
  Phase 2.1 のプロジェクト作成側で重複排除すべきかは Phase 4.2 のフォーム UI 設計で再検討
- **保留**：`time_slot_labels` の重複（例：`16:00-16:20` が 2 つ）は Forms API が
  silently 重複行を作るか、エラーを返すかが未確認
- **保留**：Form タイトルの最大長制限（Forms API の上限は未調査）。
  `project.display_name` をそのまま使うが、極端に長い場合は trim 等の処理を
  Phase 4.2 のフォーム UI で行う想定
- **保留**：`GoogleAuthRequiredError` を 401 に変換するハンドリングは
  `app/api/forms.py` 内のみ。Phase 2.3 でも同じパターンが必要になるため、
  共通の例外ハンドラ（`@app.exception_handler(GoogleAuthRequiredError)`）を
  `main.py` に切り出すリファクタを検討

## 手動 E2E 確認手順（参考）

1. Phase 1.3 の手順で OAuth 認証を完了させる（`oauth_token.json` を配置）
2. `pwsh .\scripts\start-dev.ps1` で開発サーバ起動
3. プロジェクト作成（Phase 2.1 引き継ぎ手順を参照）し `project_id` を取得
4. PowerShell から:

   ```powershell
   $pid = "<取得した project_id>"
   $resp = Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/projects/$pid/form"
   $resp | ConvertTo-Json -Depth 5
   ```

5. `%APPDATA%\meeting-scheduler\projects\<project_id>\form.json` が生成され、
   `formId` / `responderUri` / `editUri` / `row_question_id_by_date` を含むこと
6. `$resp.responderUri` をブラウザで開き、出席番号テキストフィールドと
   日付×時間枠 matrix が表示されることを目視確認
7. `$resp.editUri` をブラウザで開き、教師が編集可能な状態で開けることを目視確認
8. もう一度 `POST` を叩いて 409 Conflict が返ること
9. `GET http://localhost:8000/api/projects/$pid/form` で同じ FormInfo が返ること

## 作成ファイル一覧

- `backend/app/services/google_forms.py`（新規）
- `backend/app/api/forms.py`（新規）
- `backend/tests/test_google_forms_service.py`（新規・8 テスト）
- `backend/app/models/form.py`（差し替え）
- `backend/app/repositories/file_repository.py`（拡張）
- `backend/app/main.py`（ルータ登録 2 行追加）
- `docs/handoff_phase2_2.md`（本ドキュメント）
