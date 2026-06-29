# Claude Code 実装指示プロンプト（Windows版・サブ分割・v3.3）

本プロンプトは、`requirements.md`（Windows版）に基づき、保護者面談調整ツールのプロトタイプをサブステップ単位で段階実装するためのClaude Codeへの指示書である。

**動作環境前提：Windows 10/11、PowerShell 5.1+、Python 3.11+、Node.js 18+、Git for Windows**

**v3 変更点**：Phase 3.3 を 3.3a/3.3b に分割、Phase 4.4 を 4.4a/4.4b/4.4c に分割。全22サブステップ。

**v3.1 変更点（v3 から）**：原則4「Check-PhaseDone.ps1 と check_results\ への絶対禁止事項」を境界明確化。

**v3.2 変更点（v3.1 から）**：原則4を「絶対禁止」から「原則禁止・承認制で許可」に変更。ユーザー承認を経た修正は `fix(check):` プレフィックスで許可。

**v3.3 変更点（v3.2 から）**：各サブステップに使用モデル（Sonnet/Opus）を明示。Opus 使用は Phase 2.0、3.2、3.3a、3.3b の4つのみ、残りは Sonnet。

---

## 共通指示（全サブステップ共通）

### 開始時

- サブステップに着手する前に、`requirements.md` および当該フェーズの先行サブステップで作成された `docs\handoff_*.md` を必ず通読すること
- 「Phase N.M に着手します。requirements.md の §X-Y を参照しました」と宣言してから実装を開始する
- 不明点・前提崩れを発見した場合は、実装に進まずユーザーに確認する
- **作業着手前に必ず `git diff HEAD -- check_results\ Check-PhaseDone.ps1` を実行し、差分がないことを確認**。差分があれば作業を中止し報告する

### 実装中

- 前サブステップで作成したコードは原則変更しない。変更が必要な場合は理由を明示する
  - **例外**：`scripts\` 配下の起動スクリプト（`start-dev.ps1` 等）は、Phase 4.1 等で意図的に拡張されることが要件で定められている。当該 Phase の説明に「拡張」と明記されている場合のみ変更可
- データアクセスは Repository パターンで抽象化する
- 秘密情報はリポジトリにコミットしない。`.gitignore` を適切に設定する
- 日本語コメント・日本語UI文言を許容する
- **パスは Python では `pathlib.Path` を使用し、文字列リテラルで `\` や `/` を直書きしない**
- **PowerShell スクリプトは CRLF 改行 + UTF-8 BOM 付き、それ以外は LF 改行 + UTF-8 BOMなし**

### Check-PhaseDone.ps1 と check_results\ への変更（原則禁止、承認制で許可）

`Check-PhaseDone.ps1` および `check_results\` 配下のファイルに対する変更は、**原則として禁止**である。ただし以下のフローを踏んだ場合に限り許可される。

#### 許可される修正フロー

1. **問題発見時、まず修正せず修正方針を提示する**：
   - 問題のあるファイルと箇所(行番号含む)
   - 問題の症状
   - 問題の原因の分析
   - 推奨される修正方法(diff または patch 形式)

2. **メインエージェント経由でユーザーに伝え、明示的な承認を待つ**

3. **承認後、最小限の修正を実施**

4. **`fix(check):` プレフィックスでコミット**：
   ```bash
   git commit -m "fix(check): <修正内容の要約>"
   ```

#### 許可される修正範囲

- 構文エラーの修正
- エンコーディング修正(BOM の付け外し)
- 改行コード変換
- 軽微なバグ修正

#### ユーザー承認があっても禁止

- 新規ロジックの追加(チェック項目の追加など)
- 関数定義の大幅な書き換え
- 結果ファイル(`check_results\*.json`)の編集・削除
- 詳細ログファイル(`*.pytest.log` 等)の編集・削除
- 承認ファイル(`check_results\approvals\*.approved`)の作成・編集・削除

#### 絶対禁止

- ユーザー承認を経ない自己判断による変更
- 「機能を変えない変更ならOK」という解釈での変更

テストが通らない場合は、テスト対象の実装側を修正すること(Check-PhaseDone.ps1 やテストファイルを書き換えて通そうとしないこと)。

### その他

- **完了条件チェック(Check-PhaseDone.ps1)を自分で実行してはならない**。実行はメインエージェントの責務である

### Git運用

- 各サブステップは独立した作業単位として、適切な粒度で commit を分ける
- **テスト駆動を指示しているサブステップでは、以下の順序を厳守する**
  1. テストを先に書く
  2. すべてのテストが失敗することを確認
  3. テストファイルだけを `git commit`（例：`test(phase3.1): add scheduler test cases (RED)`）
  4. 実装に着手し、テストを通す
  5. 実装を `git commit`（例：`feat(phase3.1): implement scheduler hard constraints (GREEN)`）
  6. リファクタリングがあれば別コミット
- commitメッセージは `<type>(phase<N>.<M>): <summary>` 形式
- 各サブステップ完了時に commit を打ち、完了タグを付ける（例：`git tag phase1.1-done`）
- **TDD 厳格検証**：`Check-PhaseDone.ps1` は test commit 時点でテストが失敗していたことを `git checkout` + `pytest` で実機検証する。テストと実装を同時にコミットすることや、test commit 時点で既に通るテストを書くことは検知される

### 完了時

- 当該サブステップで実装した範囲のテストを追加（pytest / vitest）
- 動作確認手順を README または該当ドキュメントに追記
- **「次サブステップへの引き継ぎメモ」を `docs\handoff_phase{N}_{M}.md` に作成**。記載必須項目：
  - 採用方式の決定事項（該当する場合）
  - 最終コミットハッシュ（`git rev-parse HEAD` の結果）
  - 主要な実装上のパラメータ・決定
  - 後続サブステップへの引き継ぎ事項
  - 未解決の課題・要確認事項（あれば「未確定」「要確認」「保留」のいずれかの語を明記）
- 「Phase N.M 完了。最終コミット: <hash>」とメインエージェントに報告
- 当該サブステップの完了条件をすべて満たさない限り次サブステップに進まない

---

## Phase 1: バックエンド骨組み＋OAuth認証

### Phase 1.1: プロジェクト初期化と FastAPI 骨格

**使用モデル**: Sonnet

#### 目的

リポジトリの基本構造を整備し、FastAPI が `localhost:8000` で起動できる状態にする。

#### 実装範囲

1. `requirements.md §7` に従ったディレクトリ構成を作成
2. `backend\pyproject.toml` の整備
   - 依存：`fastapi`, `uvicorn[standard]`, `pydantic>=2`, `pydantic-settings`, `pytest`, `httpx`
   - Python バージョン要件：`>=3.11`
3. `backend\app\main.py` を FastAPI エントリポイント
4. `backend\app\config.py` で設定管理
   - `APP_DATA_ROOT = Path(os.getenv("APPDATA")) / "meeting-scheduler"` で解決
   - 環境変数 `MEETING_SCHEDULER_DATA_ROOT` でオーバーライド可能（テスト用）
   - 起動時に `APP_DATA_ROOT\config\` と `APP_DATA_ROOT\projects\` を自動作成
   - ポート番号は環境変数 `MEETING_SCHEDULER_PORT`（既定8000）
5. ヘルスチェック `GET /api/health` の実装（`{"status": "ok"}` を返す）
6. `.gitignore` の整備
   - `__pycache__/`, `*.pyc`, `.venv/`, `venv/`, `.env`
   - OAuth関連：`oauth_token.json`, `oauth_client.json`
   - Windows固有：`Thumbs.db`, `desktop.ini`
   - エディタ：`.vscode/`, `.idea/`
7. `.gitattributes` で改行コード設定
   ```
   * text=auto eol=lf
   *.ps1 text eol=crlf
   *.bat text eol=crlf
   ```
8. `scripts\start-dev.ps1` の作成（**Phase 4.1 で拡張予定であることをコメントで明記**）
   - 仮想環境のアクティベート（存在しない場合は作成）
   - 依存インストール（初回または `pyproject.toml` 変更時）
   - `uvicorn app.main:app --reload --port $env:MEETING_SCHEDULER_PORT` で起動
9. `scripts\setup.ps1` の作成
   - Python のバージョンチェック（3.11+）
   - 仮想環境作成 `python -m venv backend\.venv`
   - 依存インストール `backend\.venv\Scripts\pip install -e backend`
10. ヘルスチェックのテスト `backend\tests\test_health.py`
11. README に「セットアップ」「起動方法」セクションを作成

#### テスト

- `pytest backend/tests/test_health.py` で `/api/health` が200を返すことを確認

#### 完了条件

- `scripts\setup.ps1` を実行すると仮想環境と依存インストールが完了する
- `scripts\start-dev.ps1` でサーバが起動する
- ブラウザまたは `Invoke-WebRequest http://localhost:8000/api/health` で200応答
- 起動時に `%APPDATA%\meeting-scheduler\config\` と `%APPDATA%\meeting-scheduler\projects\` が自動作成される
- `pytest` でテストが通る
- `docs\handoff_phase1_1.md` 作成（仮想環境の場所、起動コマンド、デバッグ方法を記載）
- タグ `phase1.1-done`

**注：`Check-PhaseDone.ps1` は uvicorn を別ポート(18000)で起動して `/api/health` を実機検証するため、起動スクリプトが正常動作しないと完了条件未達となる。**

#### 注意事項

- フロントエンドは本フェーズではまだ作成しない
- PowerShell スクリプトは UTF-8 BOM 付きで保存
- 「v3 で `scripts\start-dev.ps1` は Phase 4.1 で拡張される」旨を `start-dev.ps1` のヘッダコメントに記載

---

### Phase 1.2: Repository 抽象化の骨格

**使用モデル**: Sonnet

#### 目的

データアクセス層を抽象化し、将来DB化に備える。本サブステップではメソッドの骨格のみ用意。

#### 実装範囲

1. `backend\app\repositories\base.py` に抽象基底クラス
   - `ProjectRepository`
   - `RuleRepository`
   - `ResponseRepository`
   - `DraftRepository`
2. `backend\app\repositories\file_repository.py` にファイルベース実装の骨格
   - 各メソッドは `raise NotImplementedError`
3. `backend\app\models\` に Pydantic モデル
   - `requirements.md §3.2` 準拠
   - `Project`, `Rules`, `Response`, `Draft` 等
   - `pathlib.Path` を扱うフィールドは `str` ではなく `Path` 型で保持
4. DIの仕組み整備
5. Repository 骨格のスモークテスト

#### テスト駆動

本サブステップは対象外（骨格のみ）。

#### 完了条件

- `backend\app\repositories\` 配下に抽象基底と骨格実装
- `backend\app\models\` に Pydantic モデル
- `pytest` パス（最低限 Phase 1.1 のテスト数を維持）
- `docs\handoff_phase1_2.md` 作成
- タグ `phase1.2-done`

---

### Phase 1.3: Google OAuth2 認証フロー

**使用モデル**: Sonnet

#### 目的

教師個人のGoogleアカウントで認証し、トークンを永続化できるようにする。**CSRF対策の state パラメータ実装を含む。**

#### 事前確認事項

メインエージェントは Phase 1.3 着手前に、`%APPDATA%\meeting-scheduler\config\oauth_client.json` の配置をユーザーに確認する。未配置なら配置完了まで待つ。

#### 実装範囲

1. 依存追加：`google-auth`, `google-auth-oauthlib`, `google-api-python-client`
2. `backend\app\services\google_auth.py`
   - 必要スコープは `requirements.md §2.1`
   - 認可URLの生成（**CSRF対策の state パラメータを含めること**）
   - 認可コードからトークン取得
   - トークン保存：`%APPDATA%\meeting-scheduler\config\oauth_token.json`
   - クライアント認証情報読込：`%APPDATA%\meeting-scheduler\config\oauth_client.json`
   - リフレッシュトークンによる自動更新
3. **CSRF対策の state パラメータ**（requirements.md §2.1 必須）
   - 認可開始時にランダムな state（例：`secrets.token_urlsafe(32)`）を生成
   - サーバ側セッション（`itsdangerous` 等のシンプルな仕組み、または `starlette.middleware.sessions`）に保存
   - コールバック時に受信した state がセッション保存値と一致するか検証
   - 不一致の場合は HTTP 400 を返す
4. APIエンドポイント
   - `GET /api/auth/google` 認証開始（state 生成）
   - `GET /api/auth/google/callback` コールバック処理（state 検証）
   - `GET /api/auth/status` 認証状態確認
5. README に GCP セットアップ手順を記載
   - GCPプロジェクト作成
   - Forms API / Drive API 有効化
   - OAuth同意画面（External / Testing モード / テストユーザー登録）
   - OAuthクライアントID発行（Webアプリケーション）
   - リダイレクトURI：`http://localhost:8000/api/auth/google/callback`
   - `oauth_client.json` のダウンロードと配置場所
6. テスト（**state パラメータ検証も含めること**）
   - 認可URL生成が必須スコープと state を含むこと
   - 認可コードからトークンを取得・保存できること（モック）
   - 既存トークンを読み込めること
   - 期限切れトークンが自動リフレッシュされること
   - 未認証時に `auth/status` が `unauthorized` を返すこと
   - **state 不一致時にコールバックが 400 を返すこと**
   - **state がセッションに保存されていない場合にも 400 を返すこと**

#### テスト駆動の指示

OAuthフローはテスト駆動で実装。

1. `backend\tests\test_google_auth.py` にテストケース（上記6項目）を書く
2. すべてのテストが失敗することを確認
3. テストを `git commit`（`test(phase1.3): add google oauth test cases including state validation (RED)`）
4. 実装してテストを通す
5. 実装を `git commit`（`feat(phase1.3): implement google oauth flow with CSRF state (GREEN)`）

#### 完了条件

- ブラウザで `http://localhost:8000/api/auth/google` にアクセスすると Google 認証画面に遷移
- 認可後に `%APPDATA%\meeting-scheduler\config\oauth_token.json` が作成される
- `GET /api/auth/status` で認証済み/未認証が判定できる
- トークン期限切れ時に自動でリフレッシュされる
- **state 不一致時にコールバックが 400 を返す**
- 全テストがパスする
- README にGCPセットアップ手順が記載されている
- `docs\handoff_phase1_3.md` 作成
- タグ `phase1.3-done`

---

## Phase 2: Google Form作成・回答受領

### Phase 2.0: Forms API 仕様調査【承認ポイント】

**使用モデル**: **Opus**

#### 目的

実装方針を確定するための事前調査。**このサブステップは調査のみで実装を含まない。**

#### 実装範囲

`docs\forms_api_research.md` に以下を**必須項目**として記載すること。`Check-PhaseDone.ps1` はキーワード grep で記載確認する：

1. **matrix**：チェックボックスグリッド（matrix）形式の質問が API で作成可能か（可否と根拠）
2. **代替**：作成不可の場合の代替案（日付ごとに複数選択チェックボックス質問を並べる）の実装可能性とサンプル
3. **responses.list**：`forms.responses.list` のレスポンス構造、特にマトリクス/複数選択回答のパース方法
4. **整数**：整数バリデーション付き短文回答の作成方法
5. **クォータ**：ポーリングAPIのクォータ制限（既定60秒間隔で問題ないか）
6. **scope**：必要なスコープの最終確認
7. **採用方式**：上記調査を踏まえ、Phase 2.1 で採用する実装方式（matrix or 代替案）を明記

#### 完了条件

- `docs\forms_api_research.md` が作成され、上記7キーワード全てが含まれる
- 機械的キーワード grep で確認される（実装の質は人間レビューで確認）
- **承認ポイント**：調査結果と採用方針をユーザーが確認し、承認ファイル作成
- タグ `phase2.0-done`

---

### Phase 2.1: プロジェクト管理 API

**使用モデル**: Sonnet

#### 目的

プロジェクトのCRUD APIを実装する。

#### 実装範囲

1. `FileProjectRepository` の実装
   - プロジェクトディレクトリの作成・削除（`pathlib.Path` 経由）
   - `project.json` の読み書き
2. APIエンドポイント
   - `POST /api/projects` 作成（`project_id` 自動採番）
   - `GET /api/projects` 一覧（作成日時降順）
   - `GET /api/projects/{id}` 詳細
   - `PUT /api/projects/{id}` 更新
   - `DELETE /api/projects/{id}` 削除
3. プロジェクト作成時に `responses\`, `drafts\`, `output\` サブディレクトリを自動作成
4. プロジェクト作成時にグローバルルールを `rules.json` として複製

#### テスト駆動

1. `backend\tests\test_project_api.py` にテストケース
   - プロジェクト作成APIがディレクトリと `project.json` を生成
   - 一覧取得が作成日時降順
   - 詳細取得が正しいスキーマ
   - 更新が反映される
   - 削除でディレクトリごと消える
   - バリデーション
2. RED確認 → `test(phase2.1): ... (RED)` でcommit
3. 実装 → GREEN確認 → `feat(phase2.1): ... (GREEN)` でcommit

#### 完了条件

- プロジェクトCRUD APIが動作
- 作成時に必要なサブディレクトリと `rules.json` が生成
- 全テストパス
- `docs\handoff_phase2_1.md` 作成
- タグ `phase2.1-done`

---

### Phase 2.2: Google Form 作成

**使用モデル**: Sonnet

#### 目的

プロジェクトの候補日時定義から Google Form を生成する。

#### 実装範囲

1. `backend\app\services\google_forms.py`
   - `create_form(project)` 関数
   - Phase 2.0 で確定した方式に従い質問項目を作成
   - `form.json` に保存（formId, responderUri, editUri）
2. APIエンドポイント
   - `POST /api/projects/{id}/form`
   - `GET /api/projects/{id}/form`

#### テスト駆動

1. `backend\tests\test_google_forms_service.py`（Google APIモック）
   - リクエスト構造の検証
   - 必須・整数バリデーション
   - 候補日時枠の形式
   - `form.json` 保存
   - 二重作成の防止
2. RED → test commit → 実装 → GREEN → feat commit

#### 完了条件

- Phase 1.3 で認証済みのGoogleアカウントで実Formが生成（手動E2E確認）
- 自動テスト全パス
- `docs\handoff_phase2_2.md` 作成
- タグ `phase2.2-done`

---

### Phase 2.3: 回答ポーリングと変換

**使用モデル**: Sonnet

#### 目的

生成済みFormへの回答を取得しファイル保存する。**本サブステップ完了時、メインエージェントにセッション再起動を推奨。**

#### 実装範囲

1. `backend\app\services\polling.py`
   - `sync_responses(project_id)` 関数
   - `forms.responses.list` 呼び出し
   - 未取得の `responseId` 抽出
   - `responses\<出席番号>\<YYYYMMDD_HHMMSS>.json` 保存
2. `FileResponseRepository` の実装
   - 出席番号ごとの最新ファイル取得
   - 受領回答一覧
   - 未受領出席番号計算
3. APIエンドポイント
   - `POST /api/projects/{id}/responses/sync`
   - `GET /api/projects/{id}/responses`
   - `GET /api/projects/{id}/responses/status`

#### テスト駆動

1. テストケース
   - 新規回答のみ保存
   - 同一出席番号からの複数回答が別ファイル保存
   - タイムスタンプ順
   - マトリクス回答のパース
   - 整数バリデーション
   - Repository の最新ファイル取得
   - 未受領計算
2. RED → test commit → 実装 → GREEN → feat commit

#### 完了条件

- 手動FormへのE2E確認で `responses\...json` が保存される
- 受領状況API動作
- 自動テスト全パス
- OAuthトークン自動リフレッシュ動作
- `docs\handoff_phase2_3.md` 作成
- タグ `phase2.3-done`

---

## Phase 3: スケジューリングエンジン

### Phase 3.1: ルール管理 API

**使用モデル**: Sonnet

#### 目的

グローバルルール、プロジェクトルールのCRUDを実装。

#### 実装範囲

1. `FileRuleRepository`
2. APIエンドポイント（GET/PUT for global-rules and project rules）
3. プロジェクト作成時のグローバルルール複製を本実装に
4. Rules モデルのバリデーション

#### テスト駆動

1. テストケース
   - グローバルルールの初期化
   - 更新の永続化
   - プロジェクト作成時のコピー
   - プロジェクトルール更新の独立性
   - 重み範囲外バリデーション
   - 不正な制約タイプバリデーション
2. RED → test commit → 実装 → GREEN → feat commit

#### 完了条件

- ルール管理API動作、バリデーション動作
- 自動テスト全パス
- `docs\handoff_phase3_1.md` 作成
- タグ `phase3.1-done`

---

### Phase 3.2: スケジューラ（ハード制約のみ）

**使用モデル**: **Opus**

#### 目的

OR-Tools CP-SAT モデルでハード制約を満たす解を返す純粋関数を実装。

#### 実装範囲

1. 依存追加：`ortools`
2. `backend\app\services\scheduler.py`
   - 入力：受領済み回答リスト、プロジェクト情報、ルール
   - 出力：割当結果（`assignments`, `unassigned_students`, `violated_constraints`）
   - 副作用なし
3. ハード制約（候補日時範囲内、教師不可時間帯除外、1コマ1生徒、所要時間倍率）
4. 解なし時：違反制約の特定と未配置生徒リスト

#### テスト駆動

1. `backend\tests\test_scheduler_hard.py`
   - 正常系（十分な候補、ぴったりの候補）
   - 教師不可時間帯
   - 1コマ1生徒
   - 所要時間倍率
   - 範囲外配置の禁止
   - 解なし系
2. RED → test commit → 実装 → GREEN → feat commit

#### 完了条件

- 全テストパス
- 純粋関数として実装
- CP-SATコードにコメント
- `docs\handoff_phase3_2.md` 作成
- タグ `phase3.2-done`

---

### Phase 3.3a: スケジューラ（ソフト制約モデル）

**使用モデル**: **Opus**

**v3 で Phase 3.3 を分割。3.3a はソフト制約モデルとテストのみ、API統合は 3.3b。**

#### 目的

ソフト制約モデルを scheduler.py に追加し、目的関数を重み付き総和最小化として実装する。

#### 実装範囲

1. ソフト制約の実装
   - 連続コマ数上限・強制空きコマ
   - 1日あたりコマ数上限
   - ペアリング
   - 時間帯回避
   - 時間帯優先
2. 目的関数：重み付きペナルティ最小化
3. ソフト制約パラメータの受け取りと変換

#### テスト駆動

1. `backend\tests\test_scheduler_soft.py`
   - 各ソフト制約の挙動検証（5種類）
   - 重み挙動（重みが大きい制約が優先される）
   - 重み0の制約は無視される
   - ハード/ソフト混在ケースで妥当な解
2. RED → test commit → 実装 → GREEN → feat commit

#### 完了条件

- 全テストパス（ハード制約のテストも引き続き通る）
- `docs\handoff_phase3_3a.md` 作成
- タグ `phase3.3a-done`

---

### Phase 3.3b: スケジューラ API 統合とパフォーマンステスト【承認ポイント】

**使用モデル**: **Opus**

**v3 で Phase 3.3 を分割。3.3b は API 統合とパフォーマンス検証。**

#### 目的

3.3a までで実装したスケジューラを API として公開し、パフォーマンス目標を達成する。

#### 実装範囲

1. APIエンドポイント
   - `POST /api/projects/{id}/schedule`
2. パフォーマンス目標
   - 30名・5日×10コマで10秒以内
   - パフォーマンステスト：`backend\tests\test_schedule_perf.py`（pytest mark で slow とし、通常実行から分離可能に）
3. パフォーマンス測定結果を `docs\handoff_phase3_3b.md` に記載

#### テスト駆動

1. `backend\tests\test_schedule_api.py`
   - APIレスポンス構造
   - 未受領生徒の扱い（除外）
   - エラー応答
2. パフォーマンステストは別ファイル `test_schedule_perf.py`
3. RED → test commit → 実装 → GREEN → feat commit

#### 完了条件

- 全テストパス
- パフォーマンス目標達成（30名・5日×10コマで10秒以内）
- `docs\handoff_phase3_3b.md` 作成（パフォーマンス測定値含む）
- タグ `phase3.3b-done`
- **承認ポイント**：ユーザーがスケジューラ挙動とパフォーマンスを確認し承認

---

### Phase 3.4: ドラフト保存・ロック管理

**使用モデル**: Sonnet

#### 目的

スケジューリング結果のドラフト保存とロック管理。**本サブステップ完了時、メインエージェントにセッション再起動を推奨。**

#### 実装範囲

1. `FileDraftRepository`
2. APIエンドポイント
   - `POST /api/projects/{id}/drafts`
   - `POST /api/projects/{id}/drafts/unlock`
   - `GET /api/projects/{id}/drafts/latest`
3. プロジェクトstatus連動

#### テスト駆動

1. テストケース
2. RED → test commit → 実装 → GREEN → feat commit

#### 完了条件

- 全API動作、自動テスト全パス
- `docs\handoff_phase3_4.md` 作成
- タグ `phase3.4-done`

---

## Phase 4: フロントエンド実装

### Phase 4.1: フロントエンド初期化とAPIクライアント

**使用モデル**: Sonnet

#### 目的

React + TypeScript のプロジェクトを立ち上げ、APIクライアント整備。**vitest を確実にセットアップする。**

#### 実装範囲

1. `frontend\` を Vite + React + TypeScript で初期化
2. 依存追加
   - React Router
   - 状態管理：Zustand + React Query
   - Tailwind CSS
   - APIクライアント：`openapi-typescript` で型自動生成
3. **vitest セットアップ（必須）**
   - `npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom`
   - `package.json` の `scripts.test` を `"vitest"` に
   - `vite.config.ts` の test 設定（jsdom 環境、setupFiles）
   - smoke test 1個（`expect(true).toBe(true)` レベル）を `frontend\tests\smoke.test.ts` に
4. `frontend\src\api\` に型付きAPIクライアント
5. ルーティング骨格（全画面の空コンポーネント配置）
6. FastAPIから静的ビルド配信設定
7. **`scripts\start-dev.ps1` の拡張（共通指示の例外規定に該当）**
   - 既存のバックエンド起動ロジックは保持
   - フロントエンド起動（`npm run dev`）を追加
   - 引数で backend のみ / frontend のみ / 両方 を切り替えられる構造
8. `scripts\start.ps1` を新規作成
   - フロントのビルド（`npm run build`）
   - FastAPI 起動

#### 完了条件

- `scripts\start-dev.ps1` でフロント・バックが両方起動
- ブラウザで `http://localhost:5173`（Vite dev）または `http://localhost:8000`（本番モード）にアクセス
- 各画面ルートが404にならない
- 型付きAPIクライアントが import 可能
- **vitest が `npm test -- --run` で実行でき、smoke test が PASS**
- `package.json` に `vitest` 依存と `scripts.test` が含まれる
- `docs\handoff_phase4_1.md` 作成
- タグ `phase4.1-done`

#### 注意事項

- PowerShell から `npm` を呼び出す際、PowerShell 実行ポリシーが `Restricted` だと npm 関連スクリプトがエラーになる
- 「`Check-PhaseDone.ps1` は `package.json` に `vitest` と `test` の文字列が含まれるかチェックする」ことを念頭に置く

---

### Phase 4.2: ホーム画面とプロジェクト一覧

**使用モデル**: Sonnet

#### 目的

ホーム、プロジェクト一覧、新規作成、グローバルルール画面を実装。

#### 実装範囲

**実コンポーネントファイルを必ず作成する：**
- `frontend\src\pages\HomePage.tsx`：プロジェクト一覧 + 新規作成 + ルール設定 + 認証状態
- `frontend\src\pages\ProjectNewPage.tsx`：新規プロジェクト作成画面
- `frontend\src\pages\GlobalRulesPage.tsx`：グローバルルール設定画面

#### テスト駆動

1. `frontend\tests\` 配下にテスト（最低3ファイル）
   - `HomePage.test.tsx`：レンダリング、プロジェクト一覧表示、認証状態表示
   - `ProjectNewPage.test.tsx`：フォームバリデーション、APIモックでの作成成功
   - `GlobalRulesPage.test.tsx`：ルール設定の保存
2. RED → test commit → 実装 → GREEN → feat commit

#### 完了条件

- 3つの実コンポーネントファイルが存在
- ホーム→新規作成→プロジェクト画面遷移
- グローバルルール設定保存
- vitest 全パス（最低 6 test 程度）
- `docs\handoff_phase4_2.md` 作成
- タグ `phase4.2-done`

---

### Phase 4.3: プロジェクト画面とForm連携UI

**使用モデル**: Sonnet

#### 目的

プロジェクト詳細画面でForm作成・URLコピー・受領状況・ポーリング・ルールカスタマイズ。

#### 実装範囲

**実コンポーネントファイル：**
- `frontend\src\pages\ProjectPage.tsx`
- `frontend\src\pages\ProjectRulesPage.tsx`

機能：
1. プロジェクト画面：メタ情報編集、Form作成、URLコピー、受領状況、ポーリング（60秒）、ルールカスタマイズ、面談日程案作成ボタン
2. プロジェクトルール画面

#### テスト駆動

1. テストケース
   - 各画面レンダリング
   - Form作成APIモック
   - 受領状況表示
   - ポーリング起動・停止
2. RED → test commit → 実装 → GREEN → feat commit

#### 完了条件

- 2つの実コンポーネントファイルが存在
- Form作成→URLコピー→（手動回答）→ポーリングで受領反映
- 未受領表示の更新
- ルールカスタマイズ保存
- vitest 全パス
- `docs\handoff_phase4_3.md` 作成
- タグ `phase4.3-done`

---

### Phase 4.4a: 日程案表示画面（マトリクス表示と解なし表示）

**使用モデル**: Sonnet

**v3 で Phase 4.4 を3分割。4.4a はマトリクス表示と解なし時の情報表示まで。DnDは 4.4b、保存は 4.4c。**

#### 目的

スケジューリング結果を日付×時間枠マトリクスで表示する画面の骨格を作る。

#### 実装範囲

**実コンポーネントファイル：**
- `frontend\src\pages\SchedulePage.tsx`

機能：
1. 日程案作成API呼び出し
2. 日付×時間枠マトリクス表示
3. 各セルに割り当てられた出席番号（read-only、まだドラッグ不可）
4. 解なし時は違反制約と未配置生徒リストを画面上部に表示

#### テスト駆動

1. テストケース
   - マトリクスのレンダリング
   - スケジュールAPI のモック呼び出し
   - 解なし時の違反制約・未配置リスト表示
2. RED → test commit → 実装 → GREEN → feat commit

#### 完了条件

- `SchedulePage.tsx` が存在し、マトリクス表示が動作
- 解なしケースの表示が動作
- vitest 全パス
- `docs\handoff_phase4_4a.md` 作成
- タグ `phase4.4a-done`

---

### Phase 4.4b: 日程案表示画面（DnD と警告）

**使用モデル**: Sonnet

**v3 で Phase 4.4 を3分割。4.4b は dnd-kit を用いた DnD と警告ダイアログ。**

#### 目的

Phase 4.4a で作ったマトリクスに、ドラッグ&ドロップによる入れ替え機能と候補外移動時の警告を追加する。

#### 実装範囲

`frontend\src\pages\SchedulePage.tsx` を拡張（**この拡張は共通指示の例外として許可される**：Phase 4.4 シリーズはマトリクスを段階的に機能追加する設計）：

1. `dnd-kit` のセットアップ：`npm install @dnd-kit/core @dnd-kit/sortable`
2. `DndContext` を使った各セルのドラッグ&ドロップ実装
3. 移動先が当該生徒の候補日時に含まれない場合の警告ダイアログ
   - 警告を出すが、操作自体は許可
   - 警告対象のセルに視覚的マーキング

#### テスト駆動

1. テストケース
   - ドラッグ操作でオブジェクトが入れ替わる
   - 移動先が候補日時外の場合に警告が出る
   - 候補日時内なら警告なし
2. RED → test commit → 実装 → GREEN → feat commit

#### 完了条件

- `SchedulePage.tsx` に `dnd-kit` と `DndContext` のimport/使用が含まれる
- DnD 操作が動作
- 警告ダイアログが動作
- vitest 全パス
- `docs\handoff_phase4_4b.md` 作成
- タグ `phase4.4b-done`

---

### Phase 4.4c: 日程案保存と保存完了画面【承認ポイント】

**使用モデル**: Sonnet

**v3 で Phase 4.4 を3分割。4.4c は保存・ロック・保存完了画面・再編集。**

#### 目的

日程案を保存し、ロックされた保存完了画面に遷移する。再編集ボタンも実装する。

#### 実装範囲

1. `SchedulePage.tsx` の拡張
   - 「保存」ボタン
   - 保存時に `POST /api/projects/{id}/drafts` を呼ぶ
   - 保存成功時に `SavedPage` へ遷移
2. **実コンポーネントファイル**：`frontend\src\pages\SavedPage.tsx`
   - 「PDF出力」ボタン（**Phase 5.2 で実装するため、ここではスタブ**）
     - クリック時の処理：`console.log("PDF download not yet implemented")` のスタブ
     - `<button onClick={handleDownloadPdf}>PDF出力</button>` の形で配置
     - `handleDownloadPdf` 関数を `// TODO: Phase 5.2 で実装` コメント付きで定義
   - 「再編集」ボタン
     - クリック時に `POST /api/projects/{id}/drafts/unlock` を呼ぶ
     - 成功時に `SchedulePage` へ戻る

#### テスト駆動

1. テストケース
   - 保存ボタンでドラフトAPIモック呼び出し
   - 保存成功時に SavedPage 遷移
   - SavedPage の PDF出力ボタンクリックでスタブメッセージ
   - 再編集ボタンでロック解除APIモック呼び出し
2. RED → test commit → 実装 → GREEN → feat commit

#### 完了条件

- `SavedPage.tsx` が存在
- ホーム→新規作成→Form→受領→日程案→修正→保存→保存完了 のE2E が通る
- PDF出力ボタンはスタブとして配置されている
- 再編集ボタンが動作
- vitest 全パス
- `docs\handoff_phase4_4c.md` 作成
- タグ `phase4.4c-done`
- **承認ポイント**：DnD画面の実機操作確認を含めユーザー承認

#### 注意事項

- 本サブステップ完了時、メインエージェントにセッション再起動を推奨

---

## Phase 5: PDF出力

### Phase 5.1: PDF生成サービス【承認ポイント】

**使用モデル**: Sonnet

#### 目的

ドラフトJSONからA4縦・マトリクス形式のPDF生成。

#### 実装範囲

1. ReportLab を採用
2. 日本語フォント：IPAex ゴシック
   - フォントファイルを `backend\app\fonts\ipaexg.ttf` に配置
   - ライセンス表記を README に記載
3. `backend\app\services\pdf_generator.py`
4. 1ページ超過時の挙動を判断し `docs\pdf_decisions.md` に記載

#### テスト駆動

1. テストケース
   - PDF生成（マジックバイト確認）
   - 複数日の列展開
   - 空きコマ
   - 日本語の非文字化け
2. RED → test commit → 実装 → GREEN → feat commit

#### 完了条件

- 全テストパス
- 手動PDF確認
- `docs\pdf_decisions.md` 記載
- `docs\handoff_phase5_1.md` 作成
- タグ `phase5.1-done`
- **承認ポイント**：PDFレイアウトをユーザーが確認し承認

---

### Phase 5.2: PDF出力API・UI

**使用モデル**: Sonnet

#### 目的

保存完了画面からPDFダウンロード。**Phase 4.4c で配置されたスタブを実装に置き換える。**

#### 実装範囲

1. `GET /api/projects/{id}/pdf`
2. **フロント：Phase 4.4c で配置した `handleDownloadPdf` を実装に置き換える**
   - `frontend\src\pages\SavedPage.tsx` の `handleDownloadPdf` を、`/api/projects/{id}/pdf` を呼び出して Blob ダウンロードを行う実装に変更
   - ローディング表示

#### テスト駆動

1. テストケース
   - PDF API のヘッダ
   - ドラフト未保存時の404
   - UIボタンクリック時のAPI呼び出し
2. RED → test commit → 実装 → GREEN → feat commit

#### 完了条件

- PDFダウンロード動作
- 日本語非文字化け
- 全テストパス
- `docs\handoff_phase5_2.md` 作成
- タグ `phase5.2-done`

---

## Phase 6: 仕上げ・統合テスト

### Phase 6.1: E2E 動作確認とログ整備

**使用モデル**: Sonnet

#### 目的

E2E確認とエラー時メッセージ整備。

#### 実装範囲

1. `docs\e2e_test.md` 動作確認手順
2. `backend\app\logging_config.py` ロギング整備
   - ログファイル：`%APPDATA%\meeting-scheduler\logs\app.log`
   - **`RotatingFileHandler` でローテーション設定**
3. フロントのエラーバウンダリ

#### テスト

エラーメッセージのテスト

#### 完了条件

- E2Eケース実機成功
- エラー時メッセージ表示
- ログ出力
- `logging_config.py` に `RotatingFileHandler` 文字列が含まれる
- `docs\handoff_phase6_1.md` 作成
- タグ `phase6.1-done`

---

### Phase 6.2: README とリリース準備

**使用モデル**: Sonnet

#### 目的

READMEだけでセットアップ→利用までできる状態に。

#### 実装範囲

1. README を Windows ユーザー向けに整備
2. `scripts\setup.ps1` の完成
3. `docs\limitations.md`
4. ライセンスファイル

#### 完了条件

- README だけでセットアップ→利用完了
- `setup.ps1` で初期セットアップ完了
- `start.ps1` で起動
- タグ `phase6.2-done`、`v0.1.0-prototype`

---

## サブステップ依存関係まとめ（v3 で22サブステップ）

```
Phase 1: バックエンド骨組み+OAuth
  1.1 → 1.2 → 1.3

Phase 2: Form作成・受領
  2.0【承認】→ 2.1 → 2.2 → 2.3 → [セッション再起動推奨]

Phase 3: スケジューリング
  3.1 → 3.2 → 3.3a → 3.3b【承認】→ 3.4 → [セッション再起動推奨]

Phase 4: フロントエンド
  4.1 → 4.2 → 4.3 → 4.4a → 4.4b → 4.4c【承認】→ [セッション再起動推奨]

Phase 5: PDF
  5.1【承認】→ 5.2

Phase 6: 仕上げ
  6.1 → 6.2
```

## Claude Codeへの起動指示テンプレート

```
implementation_prompts_subdivided.md の Phase X.Y を実装してください。

開始前に以下を実施:
1. requirements.md を通読
2. 当該フェーズの先行サブステップの docs\handoff_*.md を通読
3. git diff HEAD -- check_results\ Check-PhaseDone.ps1 を実行し差分がないことを確認
4. 「Phase X.Y に着手します」と宣言してから実装開始

テスト駆動の指示があるサブステップでは、
テストファースト → RED確認 → test commit → 実装 → GREEN確認 → implementation commit
の順序を厳守してください。test commit 時点でテストが失敗していたことが Check-PhaseDone.ps1 で実機検証されます。

Check-PhaseDone.ps1 および check_results\ 配下のファイルは編集禁止です。
完了条件チェックは自分で実行しないこと（メインエージェントの責務）。
```
