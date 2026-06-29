# 保護者面談調整ツール（プロトタイプ・Windows版）

中学校教師を想定ユーザーとした、保護者面談の日程調整支援ツール（プロトタイプ）です。

## 主要機能

- **Google Form 連携** — 候補日程の希望調査用 Google Form を自動生成し、回答を自動取り込み
- **CP-SAT スケジューラ** — OR-Tools の CP-SAT ソルバーで最適な面談日程案を生成（ソフト制約の重み付き最適化）
- **ドラッグ＆ドロップ編集** — 生成された日程案をブラウザ上でドラッグ＆ドロップで手修正
- **PDF 出力** — A4 縦・マトリクス形式の日程表 PDF を生成・ダウンロード（Noto Sans JP による日本語表示）
- **ルール管理** — 連続コマ数上限、教師不可時間帯、ペアリング等の制約をプロジェクトごとに設定

---

## 動作要件

| 項目 | 要件 |
|---|---|
| OS | Windows 10 / 11 |
| PowerShell | 5.1 以上（Windows 10/11 標準搭載） |
| Python | 3.11 以上 |
| Node.js | 18 以上（LTS 推奨） |
| Git | Git for Windows |
| Google アカウント | 個人の Google アカウント（GCP プロジェクト作成権限が必要） |

---

## クイックスタート（PowerShell）

### 1. リポジトリのクローン

```powershell
git clone <repository-url> Parents_Meeting_Manager
cd Parents_Meeting_Manager
```

### 2. セットアップスクリプトの実行

```powershell
pwsh .\scripts\setup.ps1
```

`setup.ps1` は以下を自動実行します。

1. Python / Node.js のバージョンチェック
2. Python 仮想環境の作成（`backend\.venv`）
3. バックエンド依存のインストール（`pip install -e backend`）
4. フロントエンド依存のインストール（`npm install`）
5. データディレクトリの作成（`%APPDATA%\meeting-scheduler\` 配下）

### 3. Google OAuth クライアント情報の配置

GCP コンソールで OAuth2 クライアント ID を発行し、ダウンロードした JSON ファイルを以下のパスへ配置してください。

```
%APPDATA%\meeting-scheduler\config\oauth_client.json
```

`%APPDATA%` は通常 `C:\Users\<ユーザー名>\AppData\Roaming` です。

> **詳細手順**: GCP の設定方法は「[詳細セットアップ — GCP 設定](#詳細セットアップ--gcp-設定)」を参照してください。

### 4. アプリの起動

```powershell
pwsh .\scripts\start.ps1
```

フロントエンドのビルドとバックエンド（FastAPI）の起動を自動実行します。

### 5. ブラウザでアクセス

起動後、ブラウザで以下の URL を開いてください。

```
http://localhost:8000
```

---

## 詳細セットアップ — GCP 設定

Google Forms / Drive API を利用するには、GCP プロジェクトの設定が必要です。

### 1. GCP プロジェクト作成

1. [Google Cloud Console](https://console.cloud.google.com/) にログイン
2. 上部のプロジェクトセレクタから「新しいプロジェクト」を選択
3. 任意の名前（例: `meeting-scheduler-proto`）でプロジェクトを作成

### 2. Forms API / Drive API の有効化

1. ナビゲーションメニュー → **API とサービス** → **ライブラリ**
2. 以下の API を検索し、それぞれ「有効にする」をクリック
   - **Google Forms API**
   - **Google Drive API**

### 3. OAuth 同意画面の構成

1. ナビゲーションメニュー → **API とサービス** → **OAuth 同意画面**
2. **User Type**: `External` を選択
3. アプリ名・サポートメール・デベロッパーメールを入力（個人利用のためダミーで可）
4. **公開ステータス**: `Testing` のままにする
5. **テストユーザー**: 実装者本人の Google アカウントを追加（追加しないと認可時に拒否される）
6. **スコープ**: 以下の 3 つを「スコープを追加または削除」から追加
   - `https://www.googleapis.com/auth/forms.body`
   - `https://www.googleapis.com/auth/forms.responses.readonly`
   - `https://www.googleapis.com/auth/drive.file`

### 4. OAuth クライアント ID の発行

1. ナビゲーションメニュー → **API とサービス** → **認証情報**
2. 「**+ 認証情報を作成**」→ **OAuth クライアント ID** を選択
3. **アプリケーションの種類**: `ウェブアプリケーション`
4. **承認済みのリダイレクト URI** に以下を追加（**完全一致**で登録すること）
   ```
   http://localhost:8000/api/auth/google/callback
   ```
5. 作成後、「JSON をダウンロード」をクリック

### 5. クライアント認証情報の配置

ダウンロードした JSON を `oauth_client.json` にリネームし、以下へ配置します。

```
%APPDATA%\meeting-scheduler\config\oauth_client.json
```

> **セキュリティ**: `oauth_client.json` と認可後に生成される `oauth_token.json` は
> **絶対にリポジトリへコミットしてはなりません**。`.gitignore` で除外済みです。

### 6. Google OAuth 認証の実行

初回起動後、以下の手順で認証します。

1. ブラウザで `http://localhost:8000` を開く
2. 右上の「Google でログイン」ボタンをクリック（または `http://localhost:8000/api/auth/google` へ直接アクセス）
3. Google アカウント選択 → スコープに同意
4. 認証完了後、`oauth_token.json` がディスクに保存される
5. `http://localhost:8000/api/auth/status` で `{"status":"authorized"}` が返れば成功

---

## 起動方法

### 本番モード（推奨）

```powershell
pwsh .\scripts\start.ps1
```

フロントエンドをビルドして FastAPI が静的ファイルとして配信します。
ブラウザで `http://localhost:8000` にアクセスします。

ポートを変更する場合:

```powershell
$env:MEETING_SCHEDULER_PORT = "8001"
pwsh .\scripts\start.ps1
```

### 開発モード（フロントエンドとバックエンドを別プロセスで起動）

```powershell
pwsh .\scripts\start-dev.ps1
```

バックエンドは `http://localhost:8000`（`--reload` オプション付き）、
フロントエンドは `http://localhost:5173` で起動します。
開発時は `http://localhost:5173` をブラウザで開いてください。

起動モードの切り替え:

```powershell
pwsh .\scripts\start-dev.ps1 -Mode Backend    # バックエンドのみ
pwsh .\scripts\start-dev.ps1 -Mode Frontend   # フロントエンドのみ
pwsh .\scripts\start-dev.ps1 -Mode All        # 両方（既定）
```

---

## データディレクトリ

アプリケーションのデータは以下のディレクトリに保存されます。

```
%APPDATA%\meeting-scheduler\
├── config\
│   ├── oauth_client.json    # GCP からダウンロードした OAuth2 クライアント情報
│   └── oauth_token.json     # Google OAuth2 トークン（認証後に自動生成）
├── logs\
│   └── app.log              # アプリログ（10 MB × 5 世代でローテーション）
├── data\
└── projects\
    └── <project_id>\
        ├── project.json
        ├── rules.json
        ├── form.json
        ├── responses\
        ├── drafts\
        └── output\
```

`%APPDATA%` は通常 `C:\Users\<ユーザー名>\AppData\Roaming` を指します。

ログファイルの確認:

```powershell
notepad "$env:APPDATA\meeting-scheduler\logs\app.log"
```

---

## トラブルシューティング

| 症状 | 対処 |
|---|---|
| `redirect_uri_mismatch` エラー | GCP コンソールの「承認済みリダイレクト URI」が `http://localhost:8000/api/auth/google/callback` と**完全一致**しているか確認（末尾スラッシュ・プロトコルに注意） |
| `access_denied` エラー | OAuth 同意画面の「テストユーザー」に当該 Google アカウントが追加されているか確認 |
| `oauth_client.json not found` | `%APPDATA%\meeting-scheduler\config\oauth_client.json` のパスを再確認 |
| state mismatch (400) | ブラウザのセッション（cookie）が切れた可能性。`/api/auth/google` から再度実行 |
| ポート競合 | `$env:MEETING_SCHEDULER_PORT = "8001"` で別ポートを指定 |
| `python` コマンドが見つからない | Python 3.11+ をインストールし、PATH に追加されているか確認 |
| `node` コマンドが見つからない | Node.js 18+ をインストールし、PATH に追加されているか確認 |
| PDF が文字化けする | フォントファイル `backend\app\fonts\NotoSansCJKjp-Regular.otf` が存在するか確認。存在しない場合は `app.log` を確認 |

---

## E2E 動作確認手順

実機での動作確認手順は [`docs\e2e_test.md`](docs/e2e_test.md) を参照してください。

---

## 既知の制限事項

プロトタイプとしての制限事項は [`docs\limitations.md`](docs/limitations.md) を参照してください。

---

## 開発者向け情報

### テストの実行

**バックエンドテスト（pytest）:**

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend\tests -v
```

テスト用データは `%APPDATA%` に副作用を残しません（`conftest.py` の `isolated_data_root` フィクスチャで分離）。

**フロントエンドテスト（vitest）:**

```powershell
cd frontend
npm test
```

### コード構成

```
project-root\
├── backend\
│   ├── app\
│   │   ├── main.py              # FastAPI エントリポイント・lifespan フック
│   │   ├── config.py            # 設定（APP_DATA_ROOT、ポート等）
│   │   ├── logging_config.py    # RotatingFileHandler 付きログ設定
│   │   ├── api\                 # FastAPI ルータ（projects, forms, responses, schedule, drafts, pdf, auth）
│   │   ├── services\            # サービス層（google_forms, scheduler, pdf_generator, polling）
│   │   ├── repositories\        # Repository 層（file_repository.py）
│   │   ├── models\              # Pydantic モデル
│   │   └── fonts\               # 埋め込みフォント（NotoSansCJKjp-Regular.otf）
│   ├── tests\                   # pytest テスト（133 件）
│   └── pyproject.toml
├── frontend\
│   ├── src\
│   │   ├── pages\               # 画面コンポーネント（Home, Project, Schedule, Saved 等）
│   │   ├── components\          # 共通コンポーネント（ErrorBoundary 等）
│   │   └── api\                 # API クライアント関数
│   ├── tests\                   # vitest テスト（50 件）
│   ├── package.json
│   └── vite.config.ts
├── scripts\
│   ├── setup.ps1                # 初回セットアップ
│   ├── start.ps1                # 本番モード起動
│   └── start-dev.ps1            # 開発モード起動（--reload + Vite dev server）
├── docs\
│   ├── e2e_test.md              # E2E 手動確認手順
│   ├── limitations.md           # 既知の制限事項
│   ├── pdf_decisions.md         # PDF 設計決定事項
│   └── handoff_phase*.md        # 各フェーズの実装引き継ぎメモ
└── README.md
```

### 主要 API エンドポイント

| メソッド | パス | 用途 |
|---|---|---|
| GET | `/api/health` | ヘルスチェック |
| GET | `/api/auth/google` | OAuth 認証開始 |
| GET | `/api/auth/status` | 認証状態確認 |
| GET/POST | `/api/projects` | プロジェクト一覧・作成 |
| POST | `/api/projects/{id}/form` | Google Form 作成 |
| POST | `/api/projects/{id}/responses/sync` | 回答ポーリング実行 |
| POST | `/api/projects/{id}/schedule` | スケジューリング実行 |
| POST | `/api/projects/{id}/drafts` | ドラフト保存 |
| GET | `/api/projects/{id}/pdf` | PDF 生成・ダウンロード |

---

## ライセンス

本プロジェクトは [MIT ライセンス](LICENSE) のもとで公開されています。

### サードパーティライセンス

#### Noto Sans JP

PDF 出力機能では **Noto Sans JP**（TrueType アウトライン版）を使用しています。

> This product includes Noto Sans CJK JP / Noto Sans JP,
> licensed under the SIL Open Font License 1.1 (Google/Adobe).

- フォントファイル: `backend/app/fonts/NotoSansCJKjp-Regular.otf`
- ライセンス全文: `backend/app/fonts/OFL.txt`
- ライセンス URL: https://scripts.sil.org/OFL
