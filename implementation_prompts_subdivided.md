# Claude Code 実装指示プロンプト（サブ分割版）

本プロンプトは、`requirements.md` に基づき、保護者面談調整ツールのプロトタイプをサブステップ単位で段階実装するためのClaude Codeへの指示書である。

各フェーズを 2〜5 個のサブステップに分割し、Claude Code のセッション単位で完結できる粒度に揃えている。

---

## 共通指示（全サブステップ共通）

以下を**全サブステップで遵守**すること。

### 開始時

- サブステップに着手する前に、`requirements.md` および当該フェーズの先行サブステップで作成された `docs/handoff_*.md` を必ず通読すること
- 「Phase N.M に着手します。requirements.md の §X-Y を参照しました。先行サブステップの handoff: ...」と宣言してから実装を開始する
- 不明点・前提崩れを発見した場合は、実装に進まずユーザーに確認する

### 実装中

- 前サブステップで作成したコードは原則変更しない。変更が必要な場合は理由を明示してから変更する
- データアクセスは Repository パターンで抽象化し、将来DB化できる構造を維持する
- 秘密情報（OAuthトークン、クライアントシークレット等）はリポジトリにコミットしない。`.gitignore` を適切に設定する
- 日本語コメント・日本語UI文言を許容する。エラーメッセージは教師が読んで対処判断できる平易な表現とする

### Git運用

- 各サブステップは独立した作業単位として、適切な粒度で commit を分けること
- **テスト駆動を指示しているサブステップでは、以下の順序を厳守すること**
  1. テストを先に書く
  2. すべてのテストが失敗することを確認する
  3. テストファイルだけを `git commit` する（コミットメッセージ例: `test(phase3.1): add scheduler test cases (RED)`）
  4. 実装に着手し、テストを通す
  5. 実装を `git commit` する（コミットメッセージ例: `feat(phase3.1): implement scheduler hard constraints (GREEN)`）
  6. リファクタリングがあれば別コミット（`refactor(phase3.1): ...`）
- commitメッセージは `<type>(phase<N>.<M>): <summary>` 形式とする
- 各サブステップ完了時にも commit を打ち、完了タグを付ける（例: `git tag phase1.1-done`）

### 完了時

- 当該サブステップで実装した範囲のテストを追加（pytest / vitest）
- 動作確認手順を README または該当ドキュメントに追記
- 「次サブステップへの引き継ぎメモ」を `docs/handoff_phase{N}_{M}.md` に作成
- 「Phase N.M 完了。完了条件チェックリスト: ...」と報告
- 当該サブステップの完了条件をすべて満たさない限り次サブステップに進まない

---

## Phase 1: バックエンド骨組み＋OAuth認証

### Phase 1.1: プロジェクト初期化と FastAPI 骨格

#### 目的

リポジトリの基本構造を整備し、FastAPI が `localhost` で起動できる状態にする。

#### 実装範囲

1. `requirements.md §7` に従ったディレクトリ構成を作成
2. `backend/pyproject.toml` の整備
   - 依存: `fastapi`, `uvicorn`, `pydantic`, `pydantic-settings`, `pytest`
   - 開発依存: `pytest-asyncio`, `httpx`（テスト用）
3. `backend/app/main.py` を FastAPI のエントリポイントとする
4. `backend/app/config.py` で設定管理
   - `APP_DATA_ROOT` を OS別の標準アプリデータディレクトリに解決
     - macOS: `~/Library/Application Support/<アプリ名>/`
     - Linux: `~/.local/share/<アプリ名>/`
     - Windows: `%APPDATA%\<アプリ名>\`
   - 環境変数によるオーバーライドも可能にする（テスト・開発用）
   - 起動時に `<APP_DATA_ROOT>/config/` と `<APP_DATA_ROOT>/projects/` を自動作成
5. ヘルスチェック `GET /api/health` の実装
6. `.gitignore` の整備（`__pycache__`, `.venv`, `.env`, OAuth関連ファイル等）
7. README に「起動方法」セクションを作成

#### 完了条件

- `uvicorn backend.app.main:app --reload` でサーバが起動する
- `curl http://localhost:8000/api/health` が `200 OK` を返す
- 起動時に `<APP_DATA_ROOT>` 配下のディレクトリが自動作成される
- `pytest` でヘルスチェックのテストが通る
- `docs/handoff_phase1_1.md` 作成
- タグ `phase1.1-done`

---

### Phase 1.2: Repository 抽象化の骨格

#### 目的

データアクセス層を抽象化し、将来DB化に備える。本サブステップではメソッドの骨格のみ用意。

#### 実装範囲

1. `backend/app/repositories/base.py` に抽象基底クラスを定義
   - `ProjectRepository` (CRUD)
   - `RuleRepository` (グローバル / プロジェクト)
   - `ResponseRepository` (回答ファイル管理)
   - `DraftRepository` (ドラフト管理)
2. `backend/app/repositories/file_repository.py` にファイルベース実装の骨格
   - 各メソッドは `raise NotImplementedError` でよい
   - 後続フェーズで埋める
3. `backend/app/models/` に Pydantic モデルを定義
   - `requirements.md §3.2` の各JSONに対応するモデルを実装
   - `Project`, `Rules`, `Response`, `Draft` 等
4. DI（依存性注入）の仕組みを整備
   - FastAPI の `Depends` で Repository を注入できるように
5. Repository 骨格のテスト（NotImplementedError が出ることを確認するだけでよい）

#### テスト駆動の指示

本サブステップはテスト駆動の対象外。骨格のみのため、最低限のスモークテストで十分。

#### 完了条件

- `backend/app/repositories/` 配下に抽象基底と骨格実装が揃う
- `backend/app/models/` に Pydantic モデルが揃う
- `pytest` がパスする
- `docs/handoff_phase1_2.md` 作成
- タグ `phase1.2-done`

---

### Phase 1.3: Google OAuth2 認証フロー

#### 目的

教師個人のGoogleアカウントで認証し、トークンを永続化できるようにする。

#### 実装範囲

1. 依存追加: `google-auth`, `google-auth-oauthlib`, `google-api-python-client`
2. `backend/app/services/google_auth.py` の実装
   - 必要スコープは `requirements.md §2.1` 参照
   - 認可URLの生成
   - 認可コードからトークン取得
   - トークンの保存と読み込み（`<APP_DATA_ROOT>/config/oauth_token.json`）
   - リフレッシュトークンによる自動更新
3. APIエンドポイント
   - `GET /api/auth/google` 認証開始（Google認可画面へリダイレクト）
   - `GET /api/auth/google/callback` コールバック処理
   - `GET /api/auth/status` 認証状態確認（認証済み/未認証＋スコープ情報）
4. クライアントID/シークレットの設定
   - 環境変数または `<APP_DATA_ROOT>/config/oauth_client.json` から読み込み
   - README にGCPプロジェクト作成・OAuthクライアント作成・リダイレクトURI設定手順を記載
5. テスト
   - Google APIをモック化した単体テスト
   - トークン保存/読み込みのテスト
   - リフレッシュ処理のテスト

#### テスト駆動の指示

OAuthフローはテスト駆動で実装すること。

1. `backend/tests/test_google_auth.py` に以下のテストケースを書く
   - 認可URL生成が必須スコープを含むこと
   - 認可コードからトークンを取得・保存できること（モック）
   - 既存トークンを読み込めること
   - 期限切れトークンが自動リフレッシュされること
   - 未認証時に `auth/status` が `unauthorized` を返すこと
2. すべてのテストが失敗することを確認
3. テストを `git commit`（`test(phase1.3): add google oauth test cases (RED)`）
4. 実装してテストを通す
5. 実装を `git commit`（`feat(phase1.3): implement google oauth flow (GREEN)`）

#### 完了条件

- ブラウザで `GET /api/auth/google` にアクセスすると Google 認証画面に遷移し、認可後に `oauth_token.json` が作成される
- `GET /api/auth/status` で認証済み/未認証が判定できる
- トークン期限切れ時に自動でリフレッシュされる
- 全テストがパスする
- README にGCPセットアップ手順が記載されている
- `docs/handoff_phase1_3.md` 作成（Phase 2 担当向け）
- タグ `phase1.3-done`

---

## Phase 2: Google Form作成・回答受領

### Phase 2.0: Forms API 仕様調査

#### 目的

実装方針を確定するための事前調査。**このサブステップは調査のみで実装を含まない。**

#### 実装範囲

`docs/forms_api_research.md` に以下を記載すること。

1. チェックボックスグリッド（matrix）形式の質問が API で作成可能か
2. 作成可能な場合のリクエスト構造（サンプルJSON）
3. 作成不可の場合の代替案（日付ごとに複数選択チェックボックス質問を並べる）の実装可能性とサンプル
4. `forms.responses.list` のレスポンス構造、特にマトリクス/複数選択回答のパース方法
5. 整数バリデーション付き短文回答の作成方法
6. ポーリングAPIのクォータ制限（既定60秒間隔で問題ないか）
7. 必要なスコープの最終確認

#### 完了条件

- `docs/forms_api_research.md` が作成され、上記7項目すべてに結論が記載されている
- 調査結果をもとに Phase 2.1 で採用する方式（マトリクス or 代替案）が明示されている
- **ユーザーへの確認**: 調査結果と採用方針を提示し、ユーザーの承認を得てから Phase 2.1 に進む
- タグ `phase2.0-done`

---

### Phase 2.1: プロジェクト管理 API

#### 目的

プロジェクトのCRUD APIを実装し、ファイルベースでプロジェクトを管理できるようにする。

#### 実装範囲

1. `FileProjectRepository` の実装（Phase 1.2 で骨格作成済み）
   - プロジェクトディレクトリの作成・削除
   - `project.json` の読み書き
2. APIエンドポイント
   - `POST /api/projects` プロジェクト作成
     - リクエスト: `display_name`, `candidate_dates`, `candidate_time_slots`, `slot_minutes`, `student_numbers`
     - `project_id` は自動採番（タイムスタンプベース等）
   - `GET /api/projects` 一覧（作成日時降順）
   - `GET /api/projects/{id}` 詳細
   - `PUT /api/projects/{id}` 更新
   - `DELETE /api/projects/{id}` 削除（プロトタイプでは物理削除でよい）
3. プロジェクト作成時に `responses/`, `drafts/`, `output/` サブディレクトリを自動作成
4. プロジェクト作成時にグローバルルールを `rules.json` として複製（グローバルルールが未存在ならデフォルト値）

#### テスト駆動の指示

1. `backend/tests/test_project_api.py` に以下のテストケースを書く
   - プロジェクト作成APIがディレクトリと `project.json` を生成すること
   - 一覧取得が作成日時降順で返ること
   - 詳細取得が正しいスキーマで返ること
   - 更新が反映されること
   - 削除でディレクトリごと消えること
   - 候補日や時間枠のバリデーションが効くこと（不正な日付形式は400）
2. すべて失敗を確認
3. テストを `git commit`（`test(phase2.1): add project crud test cases (RED)`）
4. 実装してテストを通す
5. 実装を `git commit`（`feat(phase2.1): implement project crud api (GREEN)`）

#### 完了条件

- プロジェクトCRUD APIが動作する
- 作成時に必要なサブディレクトリと `rules.json` が生成される
- 全テストパス
- `docs/handoff_phase2_1.md` 作成
- タグ `phase2.1-done`

---

### Phase 2.2: Google Form 作成

#### 目的

プロジェクトの候補日時定義から Google Form を生成する。

#### 実装範囲

1. `backend/app/services/google_forms.py` の実装
   - `create_form(project)` 関数
   - Phase 2.0 で確定した方式に従い質問項目を作成
     - 出席番号（必須・整数バリデーション）
     - 候補日時枠（マトリクス or 日付ごとの複数選択）
   - 作成したForm情報を `form.json` に保存（formId, responderUri, editUri）
2. APIエンドポイント
   - `POST /api/projects/{id}/form` Form作成
     - 既にForm作成済みの場合は400エラー（プロトタイプではFormの再作成は未対応）
   - `GET /api/projects/{id}/form` Form情報取得
3. Google API のレスポンスから生成された Form URL を返す

#### テスト駆動の指示

1. `backend/tests/test_google_forms_service.py` に以下のテストケースを書く（Google APIはモック）
   - 候補日時定義から正しいリクエスト構造が組み立てられること
   - 出席番号質問が必須・整数バリデーション付きで作成されること
   - 候補日時枠が Phase 2.0 で決定した形式で作成されること
   - 作成後に `form.json` が保存されること
   - 既にForm作成済みのプロジェクトに対して再作成APIを呼ぶと400が返ること
2. すべて失敗を確認
3. テストを `git commit`（`test(phase2.2): add form creation test cases (RED)`）
4. 実装してテストを通す
5. 実装を `git commit`（`feat(phase2.2): implement google form creation (GREEN)`）

#### 完了条件

- Phase 1.3 で認証済みのGoogleアカウントに対し、実際にFormが生成される（手動E2E確認）
- 自動テスト全パス
- `docs/handoff_phase2_2.md` 作成
- タグ `phase2.2-done`

---

### Phase 2.3: 回答ポーリングと変換

#### 目的

生成済みFormへの回答を取得し、`requirements.md §3.2` の形式に変換してファイル保存する。

#### 実装範囲

1. `backend/app/services/polling.py` の実装
   - `sync_responses(project_id)` 関数
   - `forms.responses.list` を呼び出し
   - 未取得の `responseId` を抽出（既存ファイルとの突き合わせ）
   - 回答内容を `Response` Pydantic モデルに変換
   - `responses/<出席番号>/<YYYYMMDD_HHMMSS>.json` として保存
   - 同一出席番号からの複数回答はすべて別ファイルとして保存
2. `FileResponseRepository` の実装
   - 出席番号ごとに最新ファイルを返すメソッド
   - 全受領回答の一覧を返すメソッド
   - 未受領出席番号を計算するメソッド（プロジェクトの `student_numbers` との差分）
3. APIエンドポイント
   - `POST /api/projects/{id}/responses/sync` ポーリング実行
   - `GET /api/projects/{id}/responses` 受領済み回答一覧（出席番号ごとに最新）
   - `GET /api/projects/{id}/responses/status` 受領済み/未受領出席番号

#### テスト駆動の指示

1. `backend/tests/test_polling_service.py` に以下のテストケースを書く（Google APIはモック）
   - 新規回答のみが保存されること（既存 responseId は再保存しない）
   - 同一出席番号からの複数回答が別ファイルとして保存されること
   - ファイル名タイムスタンプが受信時刻順になること
   - マトリクス回答が Phase 2.0 で決定したパース方法で正しく変換されること
   - 出席番号が整数でない場合のエラーハンドリング
2. `backend/tests/test_response_repository.py` に以下のテストケースを書く
   - 出席番号ごとに最新ファイルを返すこと
   - 未受領出席番号が正しく計算されること
3. すべて失敗を確認
4. テストを `git commit`（`test(phase2.3): add polling and response repo test cases (RED)`）
5. 実装してテストを通す
6. 実装を `git commit`（`feat(phase2.3): implement polling and response storage (GREEN)`）

#### 完了条件

- 手動でFormに回答後、ポーリングAPI実行で `responses/...json` が保存される（手動E2E確認）
- 受領状況APIが受領済み/未受領出席番号を正しく返す
- 自動テスト全パス
- OAuthトークン期限切れ時の自動リフレッシュが動作する
- `docs/handoff_phase2_3.md` 作成
- タグ `phase2.3-done`

---

## Phase 3: スケジューリングエンジン

### Phase 3.1: ルール管理 API

#### 目的

グローバルルールとプロジェクトルールのCRUDを実装する。

#### 実装範囲

1. `FileRuleRepository` の実装
   - グローバルルール: `<APP_DATA_ROOT>/config/global_rules.json`
   - プロジェクトルール: `<APP_DATA_ROOT>/projects/<id>/rules.json`
2. APIエンドポイント
   - `GET /api/global-rules` グローバルルール取得
   - `PUT /api/global-rules` グローバルルール更新
   - `GET /api/projects/{id}/rules` プロジェクトルール取得
   - `PUT /api/projects/{id}/rules` プロジェクトルール更新
3. プロジェクト作成時にグローバルルールを複製する処理を Phase 2.1 に追加実装（Phase 2.1 で簡易対応していた場合の本対応）
4. Rules モデルのバリデーション
   - `requirements.md §3.2 rules.json` のスキーマに従う
   - ハード制約とソフト制約の区別をモデルに反映
   - 重みは0-10の範囲

#### テスト駆動の指示

1. `backend/tests/test_rules_api.py` に以下のテストケースを書く
   - グローバルルールが初期化時にデフォルト値で生成されること
   - グローバルルール更新が永続化されること
   - プロジェクト作成時にグローバルルールがプロジェクトにコピーされること
   - プロジェクトルール更新が当該プロジェクトのみに影響すること
   - 重みが範囲外の場合バリデーションエラー
   - 不正な制約タイプの場合バリデーションエラー
2. すべて失敗を確認
3. テストを `git commit`（`test(phase3.1): add rules api test cases (RED)`）
4. 実装してテストを通す
5. 実装を `git commit`（`feat(phase3.1): implement rules api (GREEN)`）

#### 完了条件

- ルール管理APIが動作する
- バリデーションが効く
- 自動テスト全パス
- `docs/handoff_phase3_1.md` 作成
- タグ `phase3.1-done`

---

### Phase 3.2: スケジューラ（ハード制約のみ）

#### 目的

OR-Tools CP-SAT モデルでハード制約を満たす解を返す純粋関数を実装する。**ソフト制約は次サブステップで追加。**

#### 実装範囲

1. `backend/app/services/scheduler.py` の骨格と純粋関数化
   - 入力: 受領済み回答リスト、プロジェクト情報、ルール
   - 出力: 割当結果（`assignments`, `unassigned_students`, `violated_constraints`）
   - 副作用なし
2. ハード制約の実装（`requirements.md §4.6.2`）
   - 候補日時範囲内であること（生徒の availability に含まれるスロットにのみ配置）
   - 教師不可時間帯の除外
   - 1コマ1生徒
   - 所要時間倍率（連続コマ確保）
3. 解なし時の処理
   - ハード制約で解なしの場合、緩和せず「解なし」を返す
   - 未配置生徒リスト構築のため、配置可能な生徒だけを段階的に配置するフォールバック戦略を用意（無条件で全員配置を要求するのではなく、各生徒を「配置できれば加点」とする補助モデルを別途構築する案など、実装方針を決めること）
4. 違反制約の特定機構（基本形）
   - どの生徒のどの制約が問題かを `violated_constraints` に記録

#### テスト駆動の指示

1. `backend/tests/test_scheduler_hard.py` に以下のテストケースを書く
   - 正常系
     - 全生徒の候補日時が十分にあり、ハード制約を全充足できるケース
     - 候補日時がぴったりのケース（解は1つだけ）
   - ハード制約検証
     - 教師不可時間帯にどの生徒も配置されないこと
     - 1コマに2人配置されないこと
     - 所要時間倍率2の生徒に連続2コマが確保されること
     - 候補日時範囲外には配置されないこと
   - 解なし系
     - 候補日時が全生徒分まったく足りない場合、`unassigned_students` に出席番号が並ぶ
     - 教師不可時間帯と候補日時が完全に衝突する場合、当該生徒が未配置となる
     - `violated_constraints` に違反制約が記録される
2. すべて失敗を確認
3. テストを `git commit`（`test(phase3.2): add scheduler hard constraint tests (RED)`）
4. 実装してテストを通す
5. 実装を `git commit`（`feat(phase3.2): implement scheduler hard constraints (GREEN)`）

#### 完了条件

- 全テストパス
- スケジューラが純粋関数として実装されている（UIから切り離し）
- CP-SATモデルのコードにコメントが付与され、制約とコードの対応が明示されている
- `docs/handoff_phase3_2.md` 作成
- タグ `phase3.2-done`

---

### Phase 3.3: スケジューラ（ソフト制約追加）と API

#### 目的

ソフト制約を追加し、目的関数として重み付き総和を最小化する。スケジューリングAPIを公開する。

#### 実装範囲

1. ソフト制約の実装（`requirements.md §4.6.2`）
   - 連続コマ数上限・強制空きコマ
   - 1日あたりコマ数上限
   - ペアリング（出席番号同士を連続枠に）
   - 時間帯回避・優先
2. 目的関数
   - ソフト制約違反時のペナルティを重み付きで合算
   - 総ペナルティ最小化
3. スケジューリングAPI
   - `POST /api/projects/{id}/schedule` スケジューリング実行
   - 結果をJSONで返す（この段階ではまだ保存しない）
4. パフォーマンス目標
   - 出席番号30名・候補日5日×時間枠10コマ程度で10秒以内に解を返す

#### テスト駆動の指示

1. `backend/tests/test_scheduler_soft.py` に以下のテストケースを書く
   - ソフト制約検証
     - 連続コマ上限を超える解と超えない解で、後者が選ばれること
     - ペアリング指定された出席番号同士が連続枠になること
     - 時間帯回避指定された生徒が指定時刻以降に配置されないこと（ペナルティ最小化として）
     - 時間帯優先指定された生徒が指定時刻側に寄ること
     - 1日あたりコマ数上限を超える日が極力作られないこと
   - 重み検証
     - 重みが大きい制約が優先されること
     - 重み0の制約は無視されること
   - 統合
     - ハード制約とソフト制約が混在する複雑なケースで妥当な解を返すこと
2. `backend/tests/test_schedule_api.py` に以下のテストケースを書く
   - スケジューリングAPIが正しいレスポンス構造を返すこと
   - 未受領生徒がいる場合の扱い（未受領は対象外として扱う等、Phase 3.2 で決めた方針通り）
3. パフォーマンステストを書く
   - 30名・5日×10コマで10秒以内に解が返ること
4. すべて失敗を確認
5. テストを `git commit`（`test(phase3.3): add scheduler soft constraint and api tests (RED)`）
6. 実装してテストを通す
7. 実装を `git commit`（`feat(phase3.3): implement soft constraints and schedule api (GREEN)`）

#### 完了条件

- 全テストパス（ハード制約のテストも引き続き通ること）
- パフォーマンス目標を満たす
- `docs/handoff_phase3_3.md` 作成
- タグ `phase3.3-done`

---

### Phase 3.4: ドラフト保存・ロック管理

#### 目的

スケジューリング結果をドラフトとして保存し、ロック管理する。

#### 実装範囲

1. `FileDraftRepository` の実装
   - `drafts/draft_<timestamp>.json` として保存
   - ロック状態の管理（JSONの `locked` フィールド）
   - 最新ドラフトの取得
2. APIエンドポイント
   - `POST /api/projects/{id}/drafts` ドラフト保存（保存時に `locked=true` で保存）
   - `POST /api/projects/{id}/drafts/unlock` 既存ドラフトのロック解除
   - `GET /api/projects/{id}/drafts/latest` 最新ドラフト取得
3. ドラフト保存時、プロジェクトの `status` を `draft_saved` に更新
4. ロック解除時、プロジェクトの `status` を `in_progress` に戻す

#### テスト駆動の指示

1. `backend/tests/test_drafts_api.py` に以下のテストケースを書く
   - ドラフト保存で `draft_<timestamp>.json` が作成されること
   - 保存時に `locked=true` になること
   - 保存時にプロジェクトstatusが `draft_saved` になること
   - ロック解除でロックが外れ、statusが `in_progress` に戻ること
   - 最新ドラフト取得でタイムスタンプ最新のものが返ること
   - 過去ドラフトファイルが残置されること
2. すべて失敗を確認
3. テストを `git commit`（`test(phase3.4): add draft repository test cases (RED)`）
4. 実装してテストを通す
5. 実装を `git commit`（`feat(phase3.4): implement draft save and lock (GREEN)`）

#### 完了条件

- ドラフトAPIが動作する
- ロック管理が想定通り動く
- 自動テスト全パス
- `docs/handoff_phase3_4.md` 作成（Phase 4 担当向けに、想定するUIフローも記載）
- タグ `phase3.4-done`

---

## Phase 4: フロントエンド実装

### Phase 4.1: フロントエンド初期化とAPIクライアント

#### 目的

React + TypeScript のプロジェクトを立ち上げ、バックエンドAPIへの型付きクライアントを整備する。

#### 実装範囲

1. `frontend/` を Vite + React + TypeScript で初期化
2. 依存関係のインストール
   - React Router
   - 状態管理: Zustand（軽量目的）または React Query（サーバ状態管理）
   - APIクライアント: `openapi-typescript` 等でバックエンドのOpenAPIスキーマからTypeScript型を自動生成
   - スタイリング: Tailwind CSS（理由を `docs/frontend_decisions.md` に記載）
3. APIクライアント `frontend/src/api/` の実装
   - 自動生成された型を import
   - 各エンドポイントを呼ぶラッパー関数
4. ルーティング骨格（全画面の空コンポーネント配置）
   - `/` ホーム
   - `/projects/new` 新規作成
   - `/projects/:id` プロジェクト
   - `/projects/:id/schedule` 日程案
   - `/projects/:id/saved` 保存完了
   - `/rules/global` グローバルルール
   - `/projects/:id/rules` プロジェクトルール
5. FastAPI から静的ビルドを配信する設定
   - 開発時は Vite dev server、本番は FastAPI から配信
   - CORS設定を開発時のみ有効化

#### テスト駆動の指示

本サブステップは UI 骨格のため、テスト駆動は要求しない。最低限、各画面ルートが404にならないかの smoke test を vitest で書くこと。

#### 完了条件

- `npm run dev` でフロントが起動する
- 各画面ルートにアクセスでき、空画面が表示される
- バックエンドAPIへの型付きクライアントが import 可能
- `npm run build` の成果物が FastAPI から配信される
- `docs/handoff_phase4_1.md` 作成
- タグ `phase4.1-done`

---

### Phase 4.2: ホーム画面とプロジェクト一覧

#### 目的

ホーム画面、プロジェクト一覧、新規作成、グローバルルール設定画面を実装する。

#### 実装範囲

1. ホーム画面
   - 「面談調整開始」ボタン → 新規作成画面
   - 過去プロジェクト一覧（作成日時降順、ステータス表示、クリックで再オープン）
   - 「ルール設定」ボタン → グローバルルール設定画面
   - 認証状態表示（未認証の場合は認証ボタンを表示）
2. 新規プロジェクト作成画面
   - 表示名入力
   - 候補日複数選択（日付ピッカー）
   - 時間枠定義（開始時刻・終了時刻の組を複数）
   - 出席番号リスト入力（カンマ区切り or 範囲指定）
   - 作成ボタン
3. グローバルルール設定画面
   - `requirements.md §4.5.1` のフォームUI
   - プリセット制約を追加・編集・削除
   - 保存ボタン

#### テスト駆動の指示

1. `frontend/tests/home.test.tsx`, `new_project.test.tsx`, `global_rules.test.tsx` を作成
   - 各画面の基本レンダリング
   - フォームバリデーション
   - APIモックを使ったプロジェクト作成成功シナリオ
2. すべて失敗を確認
3. テストを `git commit`（`test(phase4.2): add home and project creation ui tests (RED)`）
4. 実装してテストを通す
5. 実装を `git commit`（`feat(phase4.2): implement home and project creation ui (GREEN)`）

#### 完了条件

- ホーム→新規作成→プロジェクト画面、の遷移が動く
- グローバルルール設定の保存が反映される
- vitest 全パス
- `docs/handoff_phase4_2.md` 作成
- タグ `phase4.2-done`

---

### Phase 4.3: プロジェクト画面とForm連携UI

#### 目的

プロジェクト詳細画面で、Form作成、URLコピー、受領状況表示、ポーリング、ルールカスタマイズを実装する。

#### 実装範囲

1. プロジェクト画面
   - プロジェクトメタ情報表示・編集UI
   - 「Google Form作成」ボタン
   - Form作成後、URL表示＋コピーボタン
   - 受領状況表示
     - 受領済み出席番号リスト
     - 未受領出席番号リスト
   - 「最新回答を取得」手動ボタン
   - 定期ポーリング（60秒間隔、マウント時開始/アンマウント時停止）
   - 「ルールカスタマイズ」ボタン → プロジェクトルール画面
   - 「面談日程案作成」ボタン → 日程案画面（次サブステップで実装）
2. プロジェクトルール設定画面
   - グローバルルールの設定UIをベースに、プロジェクトルール用に拡張
   - `requirements.md §4.5.2`

#### テスト駆動の指示

1. `frontend/tests/project_page.test.tsx`, `project_rules.test.tsx` を作成
   - 各画面のレンダリング
   - Form作成APIモックの呼び出し
   - 受領状況の表示
   - ポーリング起動・停止のテスト（タイマーモック）
2. すべて失敗を確認
3. テストを `git commit`（`test(phase4.3): add project page ui tests (RED)`）
4. 実装してテストを通す
5. 実装を `git commit`（`feat(phase4.3): implement project page and form integration (GREEN)`）

#### 完了条件

- プロジェクト画面からForm作成→URLコピー→（手動でFormに回答）→ポーリングで受領反映、が動作する
- 未受領出席番号がリアルタイムに更新される（最低でも次回ポーリング時には更新）
- ルールカスタマイズが保存される
- vitest 全パス
- `docs/handoff_phase4_3.md` 作成
- タグ `phase4.3-done`

---

### Phase 4.4: 日程案表示画面（ドラッグ&ドロップ）

#### 目的

スケジューリング結果を日付×時間枠マトリクスで表示し、ドラッグで手修正、保存できるようにする。

#### 実装範囲

1. 日程案表示画面
   - 「面談日程案作成」ボタン押下時の API 呼び出し
   - 日付×時間枠マトリクス表示
   - 各セルに割り当てられた出席番号オブジェクト
   - `dnd-kit` でドラッグ&ドロップ実装
   - 移動先が当該生徒の候補日時に含まれない場合、警告ダイアログ（操作自体は許可）
   - 解なし時は違反制約と未配置生徒リストを画面上部に表示
   - 「保存」ボタン → 保存完了画面（ロック付き）
2. 保存完了画面
   - 「PDF出力」ボタン（クリック時は「Phase 5 で実装予定」のメッセージで仮置き）
   - 「再編集」ボタン → ロック解除APIを呼び日程案画面に戻る

#### テスト駆動の指示

1. `frontend/tests/schedule_page.test.tsx`, `saved_page.test.tsx` を作成
   - マトリクスのレンダリング
   - ドラッグでオブジェクトが入れ替わること
   - 移動先が候補日時外の場合に警告が出ること
   - 解なし時に違反制約と未配置リストが表示されること
   - 保存ボタンでドラフトが保存され、保存完了画面に遷移すること
   - 再編集ボタンでロック解除されること
2. すべて失敗を確認
3. テストを `git commit`（`test(phase4.4): add schedule and saved page tests (RED)`）
4. 実装してテストを通す
5. 実装を `git commit`（`feat(phase4.4): implement schedule page with dnd (GREEN)`）

#### 完了条件

- 日程案画面でドラッグ修正→保存→保存完了画面まで動く
- ホーム→新規作成→Form作成→（手動Form回答）→受領→日程案→ドラッグ修正→保存、までのE2Eが通る
- 警告ダイアログが想定通り動く
- vitest 全パス
- `docs/handoff_phase4_4.md` 作成
- タグ `phase4.4-done`

---

## Phase 5: PDF出力

### Phase 5.1: PDF生成サービス

#### 目的

ドラフトJSONからA4縦・マトリクス形式のPDFを生成するサービスを実装する。

#### 実装範囲

1. PDF生成ライブラリの選定
   - ReportLab または WeasyPrint
   - 日本語フォント対応の容易さで判断
   - 選定理由を `docs/pdf_decisions.md` に記載
2. 日本語フォントの埋め込み
   - IPAex 等のオープンフォントを使用
   - フォントファイルをリポジトリに含めるか、初回起動時にダウンロードするかを判断
3. `backend/app/services/pdf_generator.py` の実装
   - 入力: ドラフトJSON
   - 出力: PDFバイト列
   - レイアウト
     - A4縦
     - ヘッダ: プロジェクト表示名、作成日時
     - 本文: 行=時間枠、列=日付、セル=出席番号
     - 空きコマは空欄
     - 複数日1ページ
4. 候補日数が1ページに収まらない場合の挙動を実装し、`docs/pdf_decisions.md` に記載
   - 候補は: 縮小 / 列分割 / 複数ページ化 のいずれか

#### テスト駆動の指示

1. `backend/tests/test_pdf_generator.py` に以下のテストケースを書く
   - 1日のみの簡易ドラフトでPDFが生成されること（バイト列で受け取り、PDFマジックバイト `%PDF` から始まることを確認）
   - 複数日のドラフトで列が複数になること（PDF構造をパースして確認、または可能ならスナップショットテスト）
   - 空きコマが空欄であること
   - 日本語のプロジェクト名が文字化けしないこと（PDFテキスト抽出で確認）
2. すべて失敗を確認
3. テストを `git commit`（`test(phase5.1): add pdf generator tests (RED)`）
4. 実装してテストを通す
5. 実装を `git commit`（`feat(phase5.1): implement pdf generation (GREEN)`）

#### 完了条件

- 全テストパス
- 手動で生成したPDFをPDFビューアで開き、レイアウトが想定通りであることを確認
- `docs/pdf_decisions.md` にレイアウト判断と1ページ超過時の挙動が記載
- `docs/handoff_phase5_1.md` 作成
- タグ `phase5.1-done`

---

### Phase 5.2: PDF出力API・UI

#### 目的

保存完了画面から PDF をダウンロードできるようにする。

#### 実装範囲

1. APIエンドポイント
   - `GET /api/projects/{id}/pdf` 最新ドラフトをPDF化してダウンロード
   - レスポンス: `application/pdf`, `Content-Disposition: attachment; filename="schedule_<project_id>_<timestamp>.pdf"`
2. フロントエンド
   - 保存完了画面の「PDF出力」ボタンを実装
   - クリックで `GET /api/projects/{id}/pdf` を呼び、ブラウザでダウンロード
   - 生成中はローディング表示

#### テスト駆動の指示

1. `backend/tests/test_pdf_api.py`
   - PDF出力APIが正しい Content-Type と Content-Disposition を返すこと
   - ドラフト未保存のプロジェクトに対して呼ぶと404
2. `frontend/tests/saved_page_pdf.test.tsx`
   - PDF出力ボタンクリック時にAPI呼び出しがされること（モック）
   - ローディング表示
3. すべて失敗を確認
4. テストを `git commit`（`test(phase5.2): add pdf api and ui tests (RED)`）
5. 実装してテストを通す
6. 実装を `git commit`（`feat(phase5.2): implement pdf download (GREEN)`）

#### 完了条件

- 保存完了画面の「PDF出力」でA4縦のマトリクスPDFがダウンロードできる
- 日本語が文字化けせず表示される
- 全テストパス
- `docs/handoff_phase5_2.md` 作成
- タグ `phase5.2-done`

---

## Phase 6: 仕上げ・統合テスト

### Phase 6.1: E2E 動作確認とログ整備

#### 目的

エンドツーエンドで動作確認を行い、エラー時のログ・メッセージを整備する。

#### 実装範囲

1. `docs/e2e_test.md` に動作確認手順を作成
   - ホーム→新規作成→Form作成→URLコピー→Form回答→受領→ルール調整→日程案→ドラッグ修正→保存→PDF出力、を網羅
   - 解なしケースの確認
   - 候補日時不足ケースの確認
   - OAuthトークン期限切れ時の挙動確認
2. ロギング整備
   - `backend/app/logging_config.py` の整備
   - エラー時に教師が対処判断できるメッセージ
   - Google API クォータ超過、認証エラー、解なし、ファイルアクセスエラー、等の典型ケース
3. フロントエンドのエラーバウンダリ
   - APIエラー時のユーザー向けメッセージ表示
   - リトライ可能エラーと致命的エラーの区別

#### テスト駆動の指示

ロギング設定とエラーバウンダリは結合テストで担保。新規ユニットテストの追加は最小限でよい。

1. `backend/tests/test_error_messages.py`
   - 各種エラー時のレスポンスメッセージが日本語で意図通り返ることを確認
2. テスト追加分を `git commit`（`test(phase6.1): add error message tests`）
3. 実装を `git commit`（`feat(phase6.1): improve logging and error handling`）

#### 完了条件

- `docs/e2e_test.md` のすべてのケースが実機で成功する
- エラー発生時、教師が対処判断できるメッセージが画面に表示される
- ログがファイルとコンソール両方に出力される
- `docs/handoff_phase6_1.md` 作成
- タグ `phase6.1-done`

---

### Phase 6.2: README とリリース準備

#### 目的

教師がREADMEだけでセットアップから利用までできる状態にする。

#### 実装範囲

1. README を教師視点で書き直し
   - 動作要件（Python版数、Node版数、OS）
   - 初回セットアップ手順
     - GCPプロジェクト作成
     - OAuthクライアント作成
     - リダイレクトURI設定
     - 必要な環境変数の設定
   - 起動方法（理想は1コマンド）
   - 既知の制限事項
2. 起動スクリプトの整備
   - 開発用: `make dev` / 本番用: `make start`
   - フロントエンドのビルド→FastAPI起動の一連を1コマンドで
3. プロトタイプ既知の制限事項を `docs/limitations.md` にまとめ、READMEからリンク
   - 生徒氏名非表示・出席番号運用
   - 学校単位マルチテナント非対応
   - DB化未対応
   - 過去ドラフト履歴比較UI未実装
   - Forms APIクォータ依存
4. ライセンスファイルの追加

#### 完了条件

- 教師が README だけを見てセットアップ→起動→面談調整→PDF出力まで実施できる
- 起動コマンドが1コマンド化されている
- すべてのドキュメントが整合している
- タグ `phase6.2-done` および `v0.1.0-prototype`

---

## サブステップ依存関係まとめ

```
Phase 1: バックエンド骨組み+OAuth
  1.1 プロジェクト初期化・FastAPI骨格
   ↓
  1.2 Repository抽象化骨格
   ↓
  1.3 Google OAuth2 フロー

Phase 2: Form作成・受領
  2.0 Forms API 仕様調査
   ↓
  2.1 プロジェクト管理 API
   ↓
  2.2 Google Form 作成
   ↓
  2.3 回答ポーリングと変換

Phase 3: スケジューリング
  3.1 ルール管理 API
   ↓
  3.2 スケジューラ（ハード制約のみ）
   ↓
  3.3 スケジューラ（ソフト制約追加）+ API
   ↓
  3.4 ドラフト保存・ロック

Phase 4: フロントエンド
  4.1 フロントエンド初期化とAPIクライアント
   ↓
  4.2 ホーム・プロジェクト一覧
   ↓
  4.3 プロジェクト画面・Form連携UI
   ↓
  4.4 日程案表示画面（DnD）

Phase 5: PDF
  5.1 PDF生成サービス
   ↓
  5.2 PDF API・UI

Phase 6: 仕上げ
  6.1 E2E確認・ログ整備
   ↓
  6.2 README・リリース準備
```

## Claude Codeへの起動指示テンプレート

各サブステップ開始時、以下のテンプレートを使う。

```
implementation_prompts_subdivided.md の Phase X.Y を実装してください。

開始前に以下を実施:
1. requirements.md を通読
2. 当該フェーズの先行サブステップの docs/handoff_*.md を通読
3. 「Phase X.Y に着手します」と宣言してから実装開始

テスト駆動の指示があるサブステップでは、
テストファースト→RED確認→test commit→実装→GREEN確認→implementation commit
の順序を厳守してください。
```
