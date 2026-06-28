# Phase 1.3 引き継ぎメモ

## サマリ

教師個人の Google アカウントによる OAuth2 認証フローを実装した。
**CSRF 対策の `state` パラメータ**を `secrets.token_urlsafe(32)` で生成し、
`starlette.middleware.sessions.SessionMiddleware` を介してサーバ側セッションに
保存→コールバック時に検証する。state 不一致／セッション未保存はいずれも HTTP 400。

トークンは `%APPDATA%\meeting-scheduler\config\oauth_token.json` に永続化し、
期限切れ時に `Credentials.refresh()` で自動更新する。

## 採用方式・決定事項

### セッションミドルウェア

- **採用**：`starlette.middleware.sessions.SessionMiddleware`（Phase 1.3 指示の推奨）
- 署名鍵：環境変数 `MEETING_SCHEDULER_SESSION_SECRET` が設定されていればそれを使用、
  未設定時はプロセス起動毎に `secrets.token_urlsafe(32)` で都度生成
- プロセス再起動でセッションは無効化（プロトタイプ運用として許容）
- `same_site="lax"`、`http://localhost` 用途のため `https_only` は無効

### state 生成と検証

- 認可開始時：`secrets.token_urlsafe(32)` で生成 → セッション `oauth_state` キーに保存
- 認可URL：`Flow.authorization_url(state=state, access_type="offline", prompt="consent", include_granted_scopes="true")`
- コールバック時：
  1. セッションから `oauth_state` を取り出す（無ければ 400）
  2. クエリの `state` と一致するか検証（不一致は 400、セッションから消去）
  3. 一致時は使い切りでセッションから削除した上でトークン交換

### Google スコープ（requirements.md §2.1 完全準拠）

```python
SCOPES = [
    "https://www.googleapis.com/auth/forms.body",
    "https://www.googleapis.com/auth/forms.responses.readonly",
    "https://www.googleapis.com/auth/drive.file",
]
```

### トークン永続化形式

- 保存：`Credentials.to_json()` をそのまま `oauth_token.json` に書き込み
- 読込：`Credentials.from_authorized_user_info(json.loads(...), scopes=SCOPES)`
- `to_json()` は `token` / `refresh_token` / `token_uri` / `client_id` /
  `client_secret` / `scopes` / `expiry`（ISO 文字列）を含むため、ラウンドトリップ可能
- 保存先パス：`Settings.config_dir / "oauth_token.json"`（`%APPDATA%\meeting-scheduler\config\oauth_token.json`）

### リダイレクト URI（requirements.md §8.5 準拠）

- 固定：`http://localhost:8000/api/auth/google/callback`
- GCP コンソール側にも同じ URI を「承認済みリダイレクト URI」として登録する必要あり
- ポート番号を変更（`MEETING_SCHEDULER_PORT`）した場合は GCP 側設定も併せて変更する前提

### `OAUTHLIB_INSECURE_TRANSPORT` の取り扱い

- `http://localhost` 運用のため、`google_auth.py` モジュール初期化時に
  `os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")` を設定
- プロトタイプ・ローカルホスト限定の暫定措置（本番化時に要再検討）

## 主要な実装上のパラメータ

| 項目 | 値 | 備考 |
|---|---|---|
| state 長 | `secrets.token_urlsafe(32)`（43 文字） | OAuth 2.0 RFC 6749 §10.12 推奨を上回る |
| トークン保存先 | `Settings.config_dir / oauth_token.json` | `%APPDATA%\meeting-scheduler\config\` |
| クライアント認証情報 | `Settings.config_dir / oauth_client.json` | GCP コンソールからダウンロード |
| セッションキー名 | `oauth_state` | `app.api.auth.SESSION_STATE_KEY` |
| アクセス種別 | `offline` | リフレッシュトークン取得のため |
| prompt | `consent` | 既存付与でもリフレッシュトークンを確実に得るため |
| テスト総数 | 既存 20 + 新規 7 = 27 件 | 全 PASS |

## 追加した依存

- `google-auth>=2.29`
- `google-auth-oauthlib>=1.2`
- `google-api-python-client>=2.130`（Phase 2.2 で使うが本フェーズで前倒し追加）
- `itsdangerous>=2.2`（`SessionMiddleware` の署名で要求される）

`backend\.venv\Scripts\pip install -e backend` で再インストール済み。

## 主要ファイル

### 新規

- `backend/app/services/google_auth.py`：OAuth2 フローのコアロジック
  - `SCOPES`, `REDIRECT_URI` 定数
  - `build_authorization_url() -> (url, state)`
  - `exchange_code_for_token(code, state) -> Credentials`
  - `load_credentials() -> Credentials | None`
  - `get_valid_credentials() -> Credentials | None`（期限切れ自動リフレッシュ）
  - `is_authenticated() -> bool`
- `backend/app/api/auth.py`：認証 API ルータ
  - `GET /api/auth/google`：state 生成→セッション保存→認可URLへリダイレクト
  - `GET /api/auth/google/callback`：state 検証→トークン交換→保存
  - `GET /api/auth/status`：`authorized` / `unauthorized` を返す
- `backend/tests/test_google_auth.py`：7 テストケース（モック・隔離 tmp_path 使用）

### 変更

- `backend/app/main.py`：
  - `SessionMiddleware` を `add_middleware` で登録（`MEETING_SCHEDULER_SESSION_SECRET`
    対応 or プロセス起動毎ランダム）
  - `auth_router` を `include_router` で登録
- `backend/pyproject.toml`：依存4つを追加
- `README.md`：「GCP セットアップ」セクションを追加（プロジェクト作成／API 有効化／
  同意画面／クライアント ID 発行／クライアント JSON 配置／認証フロー実行手順／
  トラブルシューティング表）

### 無変更

- `backend/app/config.py`、`backend/app/repositories/*`、`backend/app/models/*`、
  `backend/app/dependencies.py`、`backend/tests/conftest.py`、
  `backend/tests/test_health.py`、`backend/tests/test_repositories.py`、
  `scripts/setup.ps1`、`scripts/start-dev.ps1`、`.gitignore`、`.gitattributes`

## コミット履歴

```
fa21684 feat(phase1.3): implement google oauth flow with CSRF state (GREEN)
0722d9b test(phase1.3): add google oauth test cases including state validation (RED)
```

最終コミットハッシュ（HEAD、handoff コミット前）：`fa21684`
本ドキュメント追加後の HEAD は `git rev-parse phase1.3-done` で取得可能。

## 後続サブステップへの引き継ぎ事項

### Phase 2.1（プロジェクト管理 API）

- DI プロバイダ `app.dependencies.get_project_repository` は Phase 1.2 の通り。
  本フェーズで新規追加なし
- 認証は API 側でガードしないが、Phase 2.2 の Form 作成 API では `is_authenticated()`
  でガードする想定。Phase 2.1 ではプロジェクト CRUD のみで Google API は触らない

### Phase 2.2（Google Form 作成）

- `google_auth.get_valid_credentials()` を呼べば、期限切れトークンは自動リフレッシュされた
  `Credentials` が返る（ディスクにも反映済み）
- `googleapiclient.discovery.build("forms", "v1", credentials=creds)` を使う想定
- `oauth_token.json` が存在しない／リフレッシュ失敗時は 401 などで Form 作成 API を
  拒否する。フロント側に「認証してください」を案内する
- スコープは Phase 1.3 で `forms.body` / `drive.file` を確保済み

### Phase 2.3（回答ポーリング）

- `forms.responses.readonly` スコープも本フェーズで確保済み
- 同じ `get_valid_credentials()` でリフレッシュ込みのトークンが得られる

### 共通

- `oauth_client.json` の path は `app.services.google_auth._client_config_path()` で
  解決。Settings を経由するためテスト時は自動的に `tmp_path` 配下に向く
- セッション署名鍵は本番運用時に固定化（`MEETING_SCHEDULER_SESSION_SECRET`）を検討。
  プロトタイプではプロセス起動毎ランダムでも可

## 未解決の課題・要確認事項

- **保留**：`OAUTHLIB_INSECURE_TRANSPORT=1` を `google_auth.py` モジュールロード時に
  設定している。これはプロトタイプ・`http://localhost` 運用の暫定。HTTPS 化時に再検討
- **保留**：セッション署名鍵がプロセス再起動で変わるため、長寿命セッションは持てない。
  認可フローは数秒〜数分で完結するため実害は無いが、`MEETING_SCHEDULER_SESSION_SECRET`
  を `setup.ps1` で自動生成・永続化する案は将来検討
- **要確認**：`Credentials.from_authorized_user_info()` の `scopes` 引数に渡しているのは
  「期待するスコープ」であり、トークンに対するスコープ整合性検証は別途必要かどうか。
  Phase 2.2 で実 API 呼び出し時に挙動を確認する
- **保留**：`AuthorizationError` 系の独自例外クラスは未定義。`google-auth` 系の例外を
  そのまま 500 で投げる構造。フロント実装時にエラーメッセージを整形する必要がある場合は
  Phase 4.1 以降で例外ハンドラを追加する

## 手動 E2E 確認手順

1. `pwsh .\scripts\start-dev.ps1` でサーバ起動（既定ポート 8000）
2. ブラウザで <http://localhost:8000/api/auth/status> → `{"status":"unauthorized"}`
3. <http://localhost:8000/api/auth/google> にアクセス → Google アカウント選択画面へ遷移
4. テストユーザーとして登録した Google アカウントでログイン → スコープ同意
5. `/api/auth/google/callback` にリダイレクト後、`{"status":"authorized"}` 応答
6. `%APPDATA%\meeting-scheduler\config\oauth_token.json` がディスク上に生成されていること
7. <http://localhost:8000/api/auth/status> → `{"status":"authorized"}`
8. 念のため、不正な state でコールバックを叩くと 400 が返ること（curl で再現可能）
