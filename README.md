# 保護者面談調整ツール（プロトタイプ・Windows版）

中学校教師を想定ユーザーとした、保護者面談の日程調整支援ツール。

詳細仕様は [requirements.md](requirements.md) を参照。

本リポジトリは段階的に実装する。現在の到達点は **Phase 1.3（Google OAuth2 認証フロー）** である。

---

## 動作環境

- Windows 10 / 11
- PowerShell 5.1+
- Python 3.11+
- Git for Windows

Phase 4.1 以降では Node.js 18+ も必要になる。

---

## セットアップ

リポジトリ直下で以下を実行する。

```powershell
pwsh .\scripts\setup.ps1
```

`setup.ps1` は次を実施する。

1. Python のバージョンチェック（3.11+）
2. 仮想環境作成 `backend\.venv`
3. 依存インストール `backend\.venv\Scripts\pip install -e backend`

---

## GCP セットアップ（Phase 1.3 以降必須）

Google Forms / Drive API を利用するために、以下を GCP コンソール上で行う。
取得した `oauth_client.json` を `%APPDATA%\meeting-scheduler\config\oauth_client.json` に配置する。

### 1. GCP プロジェクト作成

1. [Google Cloud Console](https://console.cloud.google.com/) にログイン
2. 上部のプロジェクトセレクタから「新しいプロジェクト」を選択
3. 任意の名前（例：`meeting-scheduler-proto`）でプロジェクトを作成

### 2. Forms API / Drive API 有効化

1. ナビゲーションメニュー → **API とサービス** → **ライブラリ**
2. 以下の API を検索し、それぞれ「有効にする」をクリック
   - **Google Forms API**
   - **Google Drive API**

### 3. OAuth 同意画面の構成

1. ナビゲーションメニュー → **API とサービス** → **OAuth 同意画面**
2. **User Type**：`External` を選択
3. アプリ名・サポートメール・デベロッパーメールを入力（個人利用のためダミーで可）
4. **公開ステータス**：`Testing` のままにする
5. **テストユーザー**：実装者本人の Google アカウントを追加（追加しないと認可時に拒否される）
6. **スコープ**：以下の3つを「スコープを追加または削除」から追加
   - `https://www.googleapis.com/auth/forms.body`
   - `https://www.googleapis.com/auth/forms.responses.readonly`
   - `https://www.googleapis.com/auth/drive.file`

### 4. OAuth クライアント ID の発行

1. ナビゲーションメニュー → **API とサービス** → **認証情報**
2. 「**+ 認証情報を作成**」→ **OAuth クライアント ID** を選択
3. **アプリケーションの種類**：`ウェブアプリケーション`
4. **承認済みのリダイレクト URI** に以下を追加（**完全一致**で登録すること）
   ```
   http://localhost:8000/api/auth/google/callback
   ```
5. 作成後、ダイアログ右上の「JSON をダウンロード」をクリック

### 5. クライアント認証情報の配置

ダウンロードした JSON を `oauth_client.json` というファイル名にリネームし、以下のパスへ配置する。

```
%APPDATA%\meeting-scheduler\config\oauth_client.json
```

`%APPDATA%` は通常 `C:\Users\<ユーザー名>\AppData\Roaming` を指す。配置先ディレクトリは
バックエンドを一度起動すれば自動作成される。

> セキュリティ上、`oauth_client.json` と認可後に作成される `oauth_token.json` は
> **絶対にリポジトリへコミットしてはならない**。`.gitignore` で除外済み。

### 6. 認証フローの実行

1. バックエンドを起動（`pwsh .\scripts\start-dev.ps1`）
2. ブラウザで <http://localhost:8000/api/auth/google> にアクセス
3. Google アカウント選択 → スコープ同意
4. リダイレクトで `/api/auth/google/callback` に戻り、`oauth_token.json` がディスクに保存される
5. <http://localhost:8000/api/auth/status> で `{"status": "authorized"}` が返れば成功

### トラブルシューティング

| 症状 | 対処 |
|---|---|
| `redirect_uri_mismatch` エラー | GCP コンソールの「承認済みリダイレクト URI」が完全一致しているか確認（末尾スラッシュ／プロトコルに注意） |
| `access_denied` エラー | OAuth 同意画面の「テストユーザー」に当該 Google アカウントが追加されているか確認 |
| `oauth_client.json not found` | 配置先パスを再確認。`%APPDATA%` は環境変数 `APPDATA` で解決される |
| state mismatch (400) | ブラウザのセッション（cookie）が切れた可能性。`/api/auth/google` から再度実行 |

---

## 起動方法

### 開発モード（FastAPI を `--reload` で起動）

```powershell
pwsh .\scripts\start-dev.ps1
```

ポートは環境変数 `MEETING_SCHEDULER_PORT` で変更できる（既定 8000）。

```powershell
$env:MEETING_SCHEDULER_PORT = "8001"
pwsh .\scripts\start-dev.ps1
```

起動後、ブラウザまたは `Invoke-WebRequest` でヘルスチェックを確認する。

```powershell
Invoke-WebRequest http://localhost:8000/api/health
```

応答例：

```json
{"status": "ok"}
```

### データディレクトリ

起動時に以下が自動作成される（`%APPDATA%` は通常 `C:\Users\<ユーザー名>\AppData\Roaming`）。

```
%APPDATA%\meeting-scheduler\
├── config\
└── projects\
```

環境変数 `MEETING_SCHEDULER_DATA_ROOT` を設定するとデータルートを差し替えられる（テスト用途）。

---

## テスト

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend\tests
```

`backend\tests\conftest.py` の `isolated_data_root` フィクスチャにより、テスト実行は `%APPDATA%` に副作用を残さない。

---

## サードパーティライセンス

### Noto Sans JP

PDF 出力機能では **Noto Sans JP**（TrueType アウトライン版）を使用しています。

> This product includes Noto Sans CJK JP / Noto Sans JP,
> licensed under the SIL Open Font License 1.1 (Google/Adobe).

- フォントファイル: `backend/app/fonts/NotoSansCJKjp-Regular.otf`
- ライセンス全文: `backend/app/fonts/OFL.txt`
- ライセンス URL: https://scripts.sil.org/OFL

---

## ディレクトリ構成（Phase 1.1 時点）

```
project-root\
├── backend\
│   ├── app\
│   │   ├── main.py            # FastAPI エントリ
│   │   ├── config.py          # 設定（APP_DATA_ROOT, ポート）
│   │   ├── api\               # ルータ（後続フェーズ）
│   │   ├── services\          # サービス層（後続フェーズ）
│   │   ├── repositories\      # Repository 層（Phase 1.2 以降）
│   │   └── models\            # Pydantic モデル（Phase 1.2 以降）
│   ├── tests\
│   │   ├── conftest.py
│   │   └── test_health.py
│   └── pyproject.toml
├── scripts\
│   ├── setup.ps1
│   └── start-dev.ps1
└── docs\
    └── handoff_phase1_1.md
```

`requirements.md §7` のディレクトリ構成に準拠。フロントエンドは Phase 4.1 で初期化する。
