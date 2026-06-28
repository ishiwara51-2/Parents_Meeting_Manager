# Phase 1.1 引き継ぎメモ

## サマリ

`requirements.md §7` に従ったディレクトリ構成と FastAPI 骨格を作成し、
`GET /api/health` で 200 を返すまでを実装した。

## 採用方式・決定事項

### 仮想環境

- 場所：`backend\.venv\`
- 作成：`scripts\setup.ps1` または `scripts\start-dev.ps1`（無ければ自動作成）
- Python：3.11 以上が必須。本機の検証は Python 3.14.6 で実施
- インストール対象：`pip install -e backend`（editable インストール）
- 依存マーカー：`backend\.venv\.phase1_1_installed` を置き、`pyproject.toml` のタイムスタンプと比較して `start-dev.ps1` が再インストール要否を判定

### 起動コマンド

開発モード（FastAPI を `--reload` で起動）：

```powershell
pwsh .\scripts\start-dev.ps1
```

ポート上書き：

```powershell
$env:MEETING_SCHEDULER_PORT = "8001"
pwsh .\scripts\start-dev.ps1
```

直接 uvicorn を起動する場合（Check-PhaseDone.ps1 が行うのと同じ方式）：

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 18000
Pop-Location
```

### デバッグ方法

- ヘルスチェック：`Invoke-WebRequest http://localhost:8000/api/health`
- ログ：uvicorn が標準出力に INFO ログを出す（リクエスト/ステータスコードを確認可能）
- テスト：`.\backend\.venv\Scripts\python.exe -m pytest backend\tests -v`
- データルート上書き（テスト用）：環境変数 `MEETING_SCHEDULER_DATA_ROOT` に書き込み可能な任意のパスを設定。`backend\tests\conftest.py` の `isolated_data_root` フィクスチャがこの仕組みを使う

## 主要な実装上のパラメータ

| 項目 | 値 | 備考 |
|---|---|---|
| 既定ポート | 8000 | `MEETING_SCHEDULER_PORT` で上書き |
| データルート（既定） | `%APPDATA%\meeting-scheduler\` | `os.getenv("APPDATA")` から `pathlib.Path` で合成 |
| データルート（テスト） | 環境変数 `MEETING_SCHEDULER_DATA_ROOT` | 設定があれば優先 |
| データルート（フォールバック） | `~/.meeting-scheduler` | `APPDATA` 未定義時のみ。Windows 通常運用では発火しない |
| 自動作成ディレクトリ | `<root>\config\`, `<root>\projects\` | FastAPI lifespan で `mkdir(parents=True, exist_ok=True)` |
| Settings シングルトン | `app.config.get_settings()` | `functools.lru_cache` |

## 主要ファイル

- `backend\pyproject.toml`：依存 (`fastapi`, `uvicorn[standard]`, `pydantic>=2`, `pydantic-settings`, `pytest`, `httpx`)、Python `>=3.11`、`pytest` 設定
- `backend\app\main.py`：`create_app()` ファクトリと `lifespan` でディレクトリ自動作成、`GET /api/health`
- `backend\app\config.py`：`Settings`、`get_settings()`、`MEETING_SCHEDULER_DATA_ROOT` / `MEETING_SCHEDULER_PORT` 対応
- `backend\tests\conftest.py`：`isolated_data_root` フィクスチャで全テストの `APPDATA` 汚染を防止
- `backend\tests\test_health.py`：200/ボディ確認 + 起動時ディレクトリ自動作成確認の2ケース
- `scripts\setup.ps1`：Python バージョンチェック、venv 作成、editable インストール（**UTF-8 BOM + CRLF**）
- `scripts\start-dev.ps1`：venv が無ければ作成、依存が古ければ再インストール、`uvicorn --reload`（**UTF-8 BOM + CRLF**、**ヘッダコメントに Phase 4.1 で拡張予定の旨を明記**）
- `.gitignore`：`oauth_token.json` / `oauth_client.json` / `.venv/` / `__pycache__/` / `Thumbs.db` 等
- `.gitattributes`：`* text=auto eol=lf`, `*.ps1` と `*.bat` は `eol=crlf`

## 後続サブステップへの引き継ぎ事項

1. **Phase 1.2（Repository 骨格）**
   - 設定取得は `app.config.get_settings()` を通すこと。直に環境変数を読まない
   - パス操作は `pathlib.Path` を使い、文字列リテラルで `\` や `/` を直書きしない
   - 各 Repository は `Settings.projects_dir` 配下にアクセスする想定

2. **Phase 1.3（OAuth）**
   - `Settings.config_dir` が `oauth_client.json` / `oauth_token.json` の置き場所
   - リダイレクト URI は固定で `http://localhost:8000/api/auth/google/callback`（requirements.md §8.5）。ポート変更時は GCP 側の設定も合わせる必要があるが、プロトタイプ運用では 8000 固定を前提とする

3. **Phase 4.1（フロント初期化と起動スクリプト拡張）**
   - 本サブステップの `scripts\start-dev.ps1` はバックエンドのみ起動する最小実装。Phase 4.1 でフロント同時起動・引数による選択起動に拡張する旨をスクリプトヘッダコメントに記載済み
   - 拡張時は既存ロジック（venv 自動作成・依存インストール判定）を保持する

4. **テストの副作用**
   - `backend\tests\conftest.py` がデータルートを `tmp_path` に向けるため、全テストで `%APPDATA%` を汚さない。新規テストもこのフィクスチャを継承する

## 未解決の課題・要確認事項

- **保留**：本機の Python は 3.14.6。`requirements.md §1.4` は 3.11+ を要求しており満たすが、3.11 / 3.12 / 3.13 各環境でのスモーク検証は未実施
- **要確認**：`fastapi` `TestClient` 利用時に `httpx` の deprecation 警告 (`Using httpx with starlette.testclient is deprecated; install httpx2 instead`) が出る。Starlette 1.3 系の暫定挙動と思われる。CI/動作には影響なしのため、Phase 1.3 以降のテスト依存追加時に再検討する

## 最終コミットハッシュ

このサブステップの最終コミットハッシュは「完了報告」セクションを参照すること（git tag `phase1.1-done` がこのコミットを指す）。

実コミットハッシュは `git rev-parse phase1.1-done` で取得可能。
