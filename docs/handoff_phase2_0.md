# Phase 2.0 引き継ぎメモ

## サマリ

Phase 2.1 / 2.2 / 2.3 着手前の Google Forms API 仕様調査を実施。
`docs\forms_api_research.md` に **matrix / 代替 / responses.list / 整数 / クォータ / scope / 採用方式** の 7 観点で調査結果を整理した。
**本サブステップは調査のみで実装は含まない。**ユーザー承認を経て Phase 2.1 へ進む。

## 採用方式の決定事項

### 結論

**`QuestionGroupItem` + `Grid(columns.type=CHECKBOX)` 形式（= matrix 方式）を採用する。**

| 質問 | 採用方式 |
|---|---|
| 出席番号 | `TextQuestion(paragraph=False)` + `required=True`。**API には整数バリデーション機能が無いため**、サーバ側（Phase 2.3 の `polling.sync_responses()`）で `int(value.strip())` パースする |
| 候補日 × 時間枠 | `QuestionGroupItem` の `Grid.columns.type=CHECKBOX`。行 = 候補日、列 = 時間枠ラベル（例 `"16:00-16:20"`） |
| Form 生成 API シーケンス | `forms.create`（タイトルのみ）→ `forms.batchUpdate`（`createItem` で質問 2 件追加） |

### 採用根拠

1. Google Forms API v1 リファレンスで `Grid.columns` の `CHECKBOX` が公式サポートされている
2. API 呼び出し効率：候補日が N 日でも `createItem` 1 件で済む
3. UX：保護者・生徒は 1 画面でチェック可能
4. レスポンスパースが明確：`QuestionGroupItem` の各 row は別々の `questionId` を持ち、`textAnswers.answers[]` が「チェックされた列値」の配列になる
5. 代替案（日付ごとに `CHECKBOX` ChoiceQuestion を並列）への切り替えは `form.json` の構造を保てば容易

### 副次決定

| 項目 | 値 |
|---|---|
| ポーリング間隔 | **既定 60 秒**（requirements.md §4.4 のまま）。クォータ 180/min/user の 0.56% しか使わず安全 |
| 必要 scope | `forms.body` / `forms.responses.readonly` / `drive.file` の 3 つ（**Phase 1.3 で既に取得済み・変更不要**） |
| 差分検知方式 | `forms.responses.list` 全件取得 → 既知 `responseId` 集合との差分 |
| 整数バリデーション失敗時 | 不正回答としてスキップし、警告ログ出力（ファイルは保存しない） |

## 最終コミットハッシュ

```
e6341941587ae75a6cf1b64e8cb0dc2fc58c28c2  docs(phase2.0): add forms api research document
```

タグ `phase2.0-done` がこのコミットを指す（本ドキュメント追加後の HEAD は `git rev-parse phase2.0-done` で取得）。

## 主要な調査結果サマリ

### 1. matrix（チェックボックスグリッド）：作成可能

- `QuestionGroupItem.grid.columns.type = "CHECKBOX"` で実装可
- グループ内の `questions[]` はすべて `rowQuestion` 型に限定
- `Grid.columns` は全行で共通（時間枠が日付ごとに異なるなら matrix を分割するか代替案を採用）

### 2. 代替案：実装可能だが不要

- 日付ごとに `CHECKBOX` ChoiceQuestion を並べる方式
- matrix が将来制限されたときのフォールバックとして `forms_api_research.md` §3 にサンプル JSON を保存
- 本フェーズでは matrix を採用するため実装は行わない

### 3. `forms.responses.list` レスポンス構造

- 最上位：`{formId, responseId, createTime, lastSubmittedTime, answers: {<qid>: Answer}}`
- 各 `Answer`：`{questionId, textAnswers: {answers: [{value}]}}` （CHECKBOX は `answers[]` に複数値）
- **`QuestionGroupItem` は行ごとに別 `questionId` を割り当てる**ため、`form.json` に `row_question_id_by_date: { "2026-07-15": "<qid>", ...}` のマッピングを保存しておく必要あり
- 時間フィルタは API 側に無い → 全件取得 + クライアント側で差分処理

### 4. 整数バリデーション：API 非対応

- `TextQuestion` のフィールドは `paragraph: boolean` のみ
- `validation` / `textValidation` は v1 リファレンスに存在しない（Issue Tracker でも未実装）
- → **サーバ側で `int(value.strip())` を行い、失敗時はその回答を保存しない**方針

### 5. クォータ：60 秒間隔は十分安全

- `forms.responses.list` は「Expensive read」分類
- 制限：450/min/project, **180/min/user/project**
- 60 秒間隔ポーリング = 1/min/user → 制限の 0.56%
- 429 受領時は truncated exponential backoff（max 32〜64 秒）でリトライ

### 6. scope：変更なし

- `forms.body`（Form 作成・`batchUpdate`）
- `forms.responses.readonly`（回答取得）
- `drive.file`（アプリ作成 Form のみアクセスの最小権限）
- Phase 1.3 で 3 つすべて取得済み

### 7. 採用方式まとめ

| Phase | 採用方式 |
|---|---|
| 2.2 Form 作成 | matrix（`QuestionGroupItem` + `Grid` + CHECKBOX） |
| 2.2 出席番号 | `TextQuestion(paragraph=False)`、API バリデーションなし |
| 2.3 ポーリング | 60 秒間隔・全件取得 + 差分検知・429 リトライ |
| 2.3 整数チェック | サーバ側で `int()` パース |

## 後続サブステップへの引き継ぎ事項

### Phase 2.1（プロジェクト管理 API）

- 直接 Forms API を触らないが、`project.json` の `candidate_dates` / `candidate_time_slots` / `student_numbers` は **Phase 2.2 で Form 生成のパラメータとして使う**
- `candidate_time_slots` の `start` / `end` は `TimeSlot` モデル（Phase 1.2 で定義済み）。Form の選択肢ラベルは `f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}"` の形を想定
- プロジェクト作成時のサブディレクトリ（`responses/`, `drafts/`, `output/`）作成は Phase 1.2 引き継ぎどおり `FileProjectRepository.create()` の責務

### Phase 2.2（Google Form 作成）

- **必読**：`docs\forms_api_research.md` §2 / §5 / §8
- 採用方式：matrix（`QuestionGroupItem` + `Grid` + CHECKBOX）
- API シーケンス：`forms.create(body={"info":{"title":...}})` → `forms.batchUpdate(formId, body={"requests":[...]})`
- `form.json` への保存必須項目（Phase 2.3 のパースに必要）：
  - `formId` / `responderUri` / `editUri`（Form 作成レスポンスから）
  - `student_number_question_id`（出席番号質問の `questionId`）
  - `row_question_id_by_date: dict[str, str]`（候補日 → 行 `questionId`）
  - `time_slot_labels: list[str]`（生成時に使ったラベル列、パース時の整合確認用）
- `batchUpdate` レスポンスから `questionGroupItem.questions[].questionId` が取れない場合は `forms.get(formId)` を 1 回追加コールしてマッピング表を構築する（**実機で要確認**）
- 認証は `google_auth.get_valid_credentials()` を使用（自動リフレッシュ込み）
- 二重作成防止：`form.json` が既に存在すれば 409 Conflict 等を返す

### Phase 2.3（回答ポーリング・変換）

- **必読**：`docs\forms_api_research.md` §4 / §5 / §6 / §8
- `forms.responses.list(formId)` を全件取得 → `FileResponseRepository.get_known_form_response_ids()` との差分で新規分のみ処理
- パース疑似コードは `forms_api_research.md` §4 を参照
- 整数バリデーションは `int(value.strip())` で行い、`ValueError` は警告ログ + スキップ
- 保存先：`responses/<出席番号>/<YYYYMMDD_HHMMSS>.json`（タイムスタンプは受信時刻のローカル時間）
- 429 受領時は truncated exponential backoff で最低 1 回リトライ

### 共通

- Form 作成・回答取得時には `app.services.google_auth.get_valid_credentials()` を呼ぶ
- `googleapiclient.discovery.build("forms", "v1", credentials=creds)` でクライアントを構築
- 認証エラー時（`oauth_token.json` 不在・リフレッシュ失敗）は HTTP 401 を返してフロントに認証導線を示す

## 未解決の課題・要確認事項

- **要確認**：`batchUpdate` レスポンスで `questionGroupItem.questions[].questionId` が返るかどうか（公式リファレンスに明記なし）。Phase 2.2 の実装中に実機で確認し、返らない場合は `forms.get` 追加コールにフォールバックする
- **要確認**：`forms.responses.list` のレスポンスの並び順（`createTime` 昇順か降順か）。差分検知ロジックが順序に依存しないことは保証するが、ページング時の挙動を Phase 2.3 で実機確認する
- **要確認**：401 / 403 / 429 の実機挙動とエラーメッセージ。Phase 2.3 のログ整備時に再確認
- **保留**：整数バリデーション失敗時のユーザー通知方法（ログのみ vs. UI で「不正回答あり」を表示）。Phase 2.3 / Phase 4.3 で UX を再検討
- **保留**：複数プロジェクトを同時オープン時のポーリング合計クォータ管理。本ツールは「画面表示中のプロジェクトのみポーリング」（requirements.md §5.2）であり実害は無いが、念のため Phase 4.3 のフロント実装でポーリング起動・停止のライフサイクル管理を厳密にする

## 承認ポイントとしての確認事項

本サブステップは **承認ポイント**であり、Check-PhaseDone.ps1 が PASS してもユーザー承認が別途必要。
ユーザーに以下を確認してもらうこと：

1. **matrix 方式の採用に同意するか**（代替案を採用したい場合は方針変更可能）
2. **整数バリデーションをサーバ側のみで行う方針に同意するか**（より厳格にしたい場合は `DROP_DOWN` ChoiceQuestion を採用する選択肢もある。requirements.md §5.1 の文言改訂が必要）
3. **ポーリング 60 秒の既定値で進めて良いか**（変更したい場合は requirements.md §4.4 と合わせて改訂）

承認後、`check_results/approvals/` 配下に承認ファイルが作成され Phase 2.1 へ進む。

## 作成ファイル

- `docs/forms_api_research.md`（新規・448 行）
- `docs/handoff_phase2_0.md`（本ドキュメント）

## コミット履歴

```
e634194 docs(phase2.0): add forms api research document
（本ドキュメントを追加するコミットが続く）
```

最終コミットハッシュ（handoff コミット後）は `git rev-parse phase2.0-done` で取得可能。
