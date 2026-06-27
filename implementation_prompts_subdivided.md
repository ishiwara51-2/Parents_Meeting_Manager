# Claude Code 実装指示プロンプト（Windows版・サブ分割）

本プロンプトは、`requirements.md`（Windows版）に基づき、保護者面談調整ツールのプロトタイプをサブステップ単位で段階実装するためのClaude Codeへの指示書である。

**動作環境前提：Windows 10/11、PowerShell 5.1+、Python 3.11+、Node.js 18+、Git for Windows**

---

## 共通指示（全サブステップ共通）

### 開始時

- サブステップに着手する前に、`requirements.md` および当該フェーズの先行サブステップで作成された `docs\handoff_*.md` を必ず通読すること
- 「Phase N.M に着手します。requirements.md の §X-Y を参照しました」と宣言してから実装を開始する
- 不明点・前提崩れを発見した場合は、実装に進まずユーザーに確認する

### 実装中

- 前サブステップで作成したコードは原則変更しない。変更が必要な場合は理由を明示する
- データアクセスは Repository パターンで抽象化する
- 秘密情報（OAuthトークン、クライアントシークレット等）はリポジトリにコミットしない。`.gitignore` を適切に設定する
- 日本語コメント・日本語UI文言を許容する
- **パスは Python では `pathlib.Path` を使用し、文字列リテラルで `\` や `/` を直書きしない**
- **PowerShell スクリプトは CRLF 改行、それ以外は LF 改行**
- **ソースコードは UTF-8（BOMなし）、PowerShellスクリプトは UTF-8 BOM 付き**

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

### 完了時

- 当該サブステップで実装した範囲のテストを追加（pytest / vitest）
- 動作確認手順を README または該当ドキュメントに追記
- 「次サブステップへの引き継ぎメモ」を `docs\handoff_phase{N}_{M}.md` に作成
- 「Phase N.M 完了。完了条件チェックリスト: ...」と報告
- 当該サブステップの完了条件をすべて満たさない限り次サブステップに進まない

---

## Phase 1: バックエンド骨組み＋OAuth認証

### Phase 1.1: プロジェクト初期化と FastAPI 骨格

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
5. ヘルスチェック `GET /api/health` の実装
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
8. `scripts\start-dev.ps1` の作成
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
- `scripts\start-dev.ps1` でサーバが起動する（PowerShell ウィンドウ内で）
- ブラウザまたは `Invoke-WebRequest http://localhost:8000/api/health` で200応答
- 起動時に `%APPDATA%\meeting-scheduler\config\` と `%APPDATA%\meeting-scheduler\projects\` が自動作成される
- `pytest` でテストが通る
- `docs\handoff_phase1_1.md` 作成（仮想環境の場所、起動コマンド、デバッグ方法を記載）
- タグ `phase1.1-done`

#### 注意事項

- フロントエンドは本フェーズではまだ作成しない
- PowerShell スクリプトは UTF-8 BOM 付きで保存
- スクリプト内で日本語メッセージを使う場合、`chcp 65001` を冒頭で実行するか、`$OutputEncoding = [System.Text.Encoding]::UTF8` を設定
- Windows Defender のリアルタイム保護で `.venv` 作成が遅い場合がある。実装時に問題なければそのままでよい

---

### Phase 1.2: Repository 抽象化の骨格

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
   - すべて `pathlib.Path` を扱うフィールドは `str` ではなく `Path` 型で保持
4. DIの仕組み整備
   - FastAPI の `Depends` で Repository を注入
5. Repository 骨格のスモークテスト

#### テスト駆動

本サブステップは対象外（骨格のみ）。

#### 完了条件

- `backend\app\repositories\` 配下に抽象基底と骨格実装
- `backend\app\models\` に Pydantic モデル
- `pytest` パス
- `docs\handoff_phase1_2.md` 作成
- タグ `phase1.2-done`

---

### Phase 1.3: Google OAuth2 認証フロー

#### 目的

教師個人のGoogleアカウントで認証し、トークンを永続化できるようにする。

#### 実装範囲

1. 依存追加：`google-auth`, `google-auth-oauthlib`, `google-api-python-client`
2. `backend\app\services\google_auth.py`
   - 必要スコープは `requirements.md §2.1`
   - 認可URLの生成
   - 認可コードからトークン取得
   - トークン保存：`%APPDATA%\meeting-scheduler\config\oauth_token.json`
   - クライアント認証情報読込：`%APPDATA%\meeting-scheduler\config\oauth_client.json`
   - リフレッシュトークンによる自動更新
3. APIエンドポイント
   - `GET /api/auth/google` 認証開始
   - `GET /api/auth/google/callback` コールバック処理
   - `GET /api/auth/status` 認証状態確認
4. README に GCP セットアップ手順を記載
   - GCPプロジェクト作成
   - Forms API / Drive API 有効化
   - OAuth同意画面（External / Testing モード / テストユーザー登録）
   - OAuthクライアントID発行（Webアプリケーション）
   - リダイレクトURI：`http://localhost:8000/api/auth/google/callback`
   - `oauth_client.json` のダウンロードと配置場所
5. テスト
   - Google APIをモック化した単体テスト
   - トークン保存/読み込みのテスト
   - リフレッシュ処理のテスト
6. PowerShell ヘルパースクリプト `scripts\open-app-data.ps1` を作成
   - `%APPDATA%\meeting-scheduler\config\` をエクスプローラで開く
   - ユーザーが `oauth_client.json` を配置しやすくする

#### テスト駆動の指示

OAuthフローはテスト駆動で実装。

1. `backend\tests\test_google_auth.py` に以下のテストケースを書く
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

- ブラウザで `http://localhost:8000/api/auth/google` にアクセスすると Google 認証画面に遷移
- 認可後に `%APPDATA%\meeting-scheduler\config\oauth_token.json` が作成される
- `GET /api/auth/status` で認証済み/未認証が判定できる
- トークン期限切れ時に自動でリフレッシュされる
- 全テストがパスする
- README にGCPセットアップ手順が記載されている
- `docs\handoff_phase1_3.md` 作成
- タグ `phase1.3-done`

---

## Phase 2: Google Form作成・回答受領

### Phase 2.0: Forms API 仕様調査

#### 目的

実装方針を確定するための事前調査。**このサブステップは調査のみで実装を含まない。**

#### 実装範囲

`docs\forms_api_research.md` に以下を記載すること。

1. チェックボックスグリッド（matrix）形式の質問が API で作成可能か
2. 作成可能な場合のリクエスト構造（サンプルJSON）
3. 作成不可の場合の代替案（日付ごとに複数選択チェックボックス質問を並べる）の実装可能性とサンプル
4. `forms.responses.list` のレスポンス構造、特にマトリクス/複数選択回答のパース方法
5. 整数バリデーション付き短文回答の作成方法
6. ポーリングAPIのクォータ制限
7. 必要なスコープの最終確認

#### 完了条件

- `docs\forms_api_research.md` が作成され、上記7項目すべてに結論が記載されている
- 調査結果をもとに Phase 2.1 で採用する方式（マトリクス or 代替案）が明示されている
- **ユーザーへの確認**：調査結果と採用方針を提示し、ユーザーの承認を得てから Phase 2.1 に進む
- タグ `phase2.0-done`

---

### Phase 2.1: プロジェクト管理 API

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

#### 目的

生成済みFormへの回答を取得しファイル保存する。

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

#### 目的

グローバルルール、プロジェクトルールのCRUDを実装。

#### 実装範囲

1. `FileRuleRepository`
   - `%APPDATA%\meeting-scheduler\config\global_rules.json`
   - `%APPDATA%\meeting-scheduler\projects\<id>\rules.json`
2. APIエンドポイント
   - `GET/PUT /api/global-rules`
   - `GET/PUT /api/projects/{id}/rules`
3. プロジェクト作成時のグローバルルール複製を本実装に
4. Rules モデルのバリデーション
   - ハード/ソフトの区別
   - 重み0-10

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

#### 目的

OR-Tools CP-SAT モデルでハード制約を満たす解を返す純粋関数を実装。

#### 実装範囲

1. 依存追加：`ortools`
2. `backend\app\services\scheduler.py`
   - 入力：受領済み回答リスト、プロジェクト情報、ルール
   - 出力：割当結果（`assignments`, `unassigned_students`, `violated_constraints`）
   - 副作用なし
3. ハード制約
   - 候補日時範囲内
   - 教師不可時間帯除外
   - 1コマ1生徒
   - 所要時間倍率
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

#### 注意事項

- Windows での OR-Tools インストールはホイール提供されており通常問題ないが、Visual C++ 再頒布可能パッケージが必要になる場合がある。エラーが出たら README に明記

---

### Phase 3.3: スケジューラ（ソフト制約追加）と API

#### 目的

ソフト制約を追加、目的関数で重み付き総和最小化、スケジューリングAPI公開。

#### 実装範囲

1. ソフト制約
   - 連続コマ数上限・強制空きコマ
   - 1日あたりコマ数上限
   - ペアリング
   - 時間帯回避・優先
2. 目的関数：重み付きペナルティ最小化
3. `POST /api/projects/{id}/schedule`
4. パフォーマンス目標：30名・5日×10コマで10秒以内

#### テスト駆動

1. `backend\tests\test_scheduler_soft.py`
   - 各ソフト制約検証
   - 重み挙動
   - ハード/ソフト混在
2. `backend\tests\test_schedule_api.py`
   - API レスポンス構造
   - 未受領生徒の扱い
3. パフォーマンステスト
4. RED → test commit → 実装 → GREEN → feat commit

#### 完了条件

- 全テストパス
- パフォーマンス目標達成
- `docs\handoff_phase3_3.md` 作成
- タグ `phase3.3-done`

---

### Phase 3.4: ドラフト保存・ロック管理

#### 目的

スケジューリング結果のドラフト保存とロック管理。

#### 実装範囲

1. `FileDraftRepository`
   - `drafts\draft_<timestamp>.json` 保存
   - ロック状態管理
   - 最新ドラフト取得
2. APIエンドポイント
   - `POST /api/projects/{id}/drafts`
   - `POST /api/projects/{id}/drafts/unlock`
   - `GET /api/projects/{id}/drafts/latest`
3. プロジェクトstatus連動

#### テスト駆動

1. テストケース
   - 保存
   - ロック状態
   - status遷移
   - ロック解除
   - 最新取得
   - 過去ファイル残置
2. RED → test commit → 実装 → GREEN → feat commit

#### 完了条件

- 全API動作、自動テスト全パス
- `docs\handoff_phase3_4.md` 作成（UIフロー想定込み）
- タグ `phase3.4-done`

---

## Phase 4: フロントエンド実装

### Phase 4.1: フロントエンド初期化とAPIクライアント

#### 目的

React + TypeScript のプロジェクトを立ち上げ、APIクライアント整備。

#### 実装範囲

1. `frontend\` を Vite + React + TypeScript で初期化
   ```powershell
   cd <project-root>
   npm create vite@latest frontend -- --template react-ts
   ```
2. 依存追加
   - React Router
   - 状態管理：Zustand + React Query
   - Tailwind CSS
   - APIクライアント：`openapi-typescript` で型自動生成
3. `frontend\src\api\` に型付きAPIクライアント
4. ルーティング骨格（全画面の空コンポーネント配置）
5. FastAPIから静的ビルド配信設定
   - 開発：Vite dev server + プロキシ設定
   - 本番：FastAPI が `frontend\dist\` を配信
6. `scripts\start-dev.ps1` を拡張
   - バックエンド起動（バックグラウンド or 別ウィンドウ）
   - フロントエンド起動（`npm run dev`）
7. `scripts\start.ps1` を作成
   - フロントのビルド
   - FastAPI 起動

#### 完了条件

- `scripts\start-dev.ps1` でフロント・バックが両方起動
- ブラウザで `http://localhost:5173`（Vite dev）または `http://localhost:8000`（本番モード）にアクセス
- 各画面ルートが404にならない
- 型付きAPIクライアントが import 可能
- vitest による smoke test がパス
- `docs\handoff_phase4_1.md` 作成
- タグ `phase4.1-done`

#### 注意事項

- PowerShell から `npm` を呼び出す際、PowerShell 実行ポリシーが `Restricted` だと npm 関連スクリプトがエラーになる。README で `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` の手順を案内する

---

### Phase 4.2: ホーム画面とプロジェクト一覧

#### 目的

ホーム、プロジェクト一覧、新規作成、グローバルルール画面を実装。

#### 実装範囲

1. ホーム画面：プロジェクト一覧 + 新規作成 + ルール設定 + 認証状態
2. 新規プロジェクト作成画面
3. グローバルルール設定画面

#### テスト駆動

1. `frontend\tests\` 配下にテスト
   - レンダリング
   - フォームバリデーション
   - APIモックを使った作成成功シナリオ
2. RED → test commit → 実装 → GREEN → feat commit

#### 完了条件

- ホーム→新規作成→プロジェクト画面遷移
- グローバルルール設定保存
- vitest 全パス
- `docs\handoff_phase4_2.md` 作成
- タグ `phase4.2-done`

---

### Phase 4.3: プロジェクト画面とForm連携UI

#### 目的

プロジェクト詳細画面でForm作成・URLコピー・受領状況・ポーリング・ルールカスタマイズ。

#### 実装範囲

1. プロジェクト画面
   - メタ情報編集
   - Form作成ボタン
   - URL表示+コピー
   - 受領状況表示
   - 手動取得+定期ポーリング（60秒）
   - ルールカスタマイズボタン
   - 面談日程案作成ボタン
2. プロジェクトルール画面

#### テスト駆動

1. テストケース
   - 各画面レンダリング
   - Form作成APIモック
   - 受領状況表示
   - ポーリング起動・停止
2. RED → test commit → 実装 → GREEN → feat commit

#### 完了条件

- Form作成→URLコピー→（手動回答）→ポーリングで受領反映
- 未受領表示の更新
- ルールカスタマイズ保存
- vitest 全パス
- `docs\handoff_phase4_3.md` 作成
- タグ `phase4.3-done`

---

### Phase 4.4: 日程案表示画面（ドラッグ&ドロップ）

#### 目的

スケジューリング結果のマトリクス表示、DnD修正、保存。

#### 実装範囲

1. 日程案表示画面
   - 日程案作成API呼び出し
   - 日付×時間枠マトリクス
   - `dnd-kit` でDnD
   - 候補外移動時の警告
   - 解なし時の違反制約・未配置リスト
   - 保存ボタン
2. 保存完了画面
   - PDF出力ボタン（Phase 5 で実装の仮置き）
   - 再編集ボタン

#### テスト駆動

1. テストケース
   - マトリクスレンダリング
   - DnD入替
   - 警告
   - 解なし表示
   - 保存・ロック・遷移
   - 再編集
2. RED → test commit → 実装 → GREEN → feat commit

#### 完了条件

- ホーム→新規作成→Form→受領→日程案→修正→保存のE2E
- 警告動作
- vitest 全パス
- `docs\handoff_phase4_4.md` 作成
- タグ `phase4.4-done`

---

## Phase 5: PDF出力

### Phase 5.1: PDF生成サービス

#### 目的

ドラフトJSONからA4縦・マトリクス形式のPDF生成。

#### 実装範囲

1. ReportLab を採用（pip インストールがWindows でも安定）
2. 日本語フォント
   - IPAex ゴシックを採用
   - フォントファイルを `backend\app\fonts\` に配置（リポジトリに含める）
   - ライセンス表記を README に記載
3. `backend\app\services\pdf_generator.py`
   - 入力：ドラフトJSON
   - 出力：PDFバイト列
   - A4縦、複数日1ページ、マトリクス
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

---

### Phase 5.2: PDF出力API・UI

#### 目的

保存完了画面からPDFダウンロード。

#### 実装範囲

1. `GET /api/projects/{id}/pdf`
   - `application/pdf`
   - `Content-Disposition: attachment; filename=...`
2. フロント：保存完了画面のPDF出力ボタン

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

#### 目的

E2E確認とエラー時メッセージ整備。

#### 実装範囲

1. `docs\e2e_test.md` 動作確認手順
2. `backend\app\logging_config.py` ロギング整備
   - ログファイル：`%APPDATA%\meeting-scheduler\logs\app.log`
   - ローテーション設定
3. フロントのエラーバウンダリ

#### テスト

エラーメッセージのテスト

#### 完了条件

- E2Eケース実機成功
- エラー時メッセージ表示
- ログ出力
- `docs\handoff_phase6_1.md` 作成
- タグ `phase6.1-done`

---

### Phase 6.2: README とリリース準備

#### 目的

READMEだけでセットアップ→利用までできる状態に。

#### 実装範囲

1. README を Windows ユーザー向けに整備
   - 動作要件（Windows 10/11、Python 3.11+、Node.js 18+、Git for Windows、PowerShell 5.1+）
   - PowerShell 実行ポリシー設定の手順
   - GCPセットアップ手順（クライアント認証情報の配置場所込み）
   - 起動方法：`.\scripts\start-dev.ps1` または `.\scripts\start.ps1`
   - 既知の制限事項
2. `scripts\setup.ps1` の完成
   - Python/Node のバージョンチェック
   - 仮想環境作成
   - 依存インストール（バックエンド・フロントエンド）
   - フロントエンドビルド
   - 初回起動時の動作確認
3. `docs\limitations.md`
4. ライセンスファイル

#### 完了条件

- README だけでセットアップ→利用完了
- `setup.ps1` で初期セットアップ完了
- `start.ps1` で起動
- タグ `phase6.2-done`、`v0.1.0-prototype`

---

## サブステップ依存関係まとめ

```
Phase 1: バックエンド骨組み+OAuth
  1.1 → 1.2 → 1.3

Phase 2: Form作成・受領
  2.0 → 2.1 → 2.2 → 2.3

Phase 3: スケジューリング
  3.1 → 3.2 → 3.3 → 3.4

Phase 4: フロントエンド
  4.1 → 4.2 → 4.3 → 4.4

Phase 5: PDF
  5.1 → 5.2

Phase 6: 仕上げ
  6.1 → 6.2
```

## Claude Codeへの起動指示テンプレート

```
implementation_prompts_subdivided.md の Phase X.Y を実装してください。

開始前に以下を実施:
1. requirements.md を通読
2. 当該フェーズの先行サブステップの docs\handoff_*.md を通読
3. 「Phase X.Y に着手します」と宣言してから実装開始

テスト駆動の指示があるサブステップでは、
テストファースト → RED確認 → test commit → 実装 → GREEN確認 → implementation commit
の順序を厳守してください。

Windows ネイティブ環境（PowerShell）前提のため、パス区切りや改行コードに注意してください。
```
