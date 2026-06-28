# 保護者面談調整ツール（プロトタイプ・Windows版）

中学校教師を想定ユーザーとした、保護者面談の日程調整支援ツール。

詳細仕様は [requirements.md](requirements.md) を参照。

本リポジトリは段階的に実装する。現在の到達点は **Phase 1.1（プロジェクト初期化と FastAPI 骨格）** である。

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
