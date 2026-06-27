# オーケストレーションスクリプト 運用手順書（Windows版）

`orchestrator.ps1` は、`implementation_prompts_subdivided.md` で定義された 19 個のサブステップを、Claude Code の headless モードで自動進行させる PowerShell スクリプトです。

## 仕組み

各サブステップは **完全に独立した Claude Code セッション** として実行されます。

- セッション間でコンテキストは引き継がれない（compact不要）
- 状態の引き継ぎは **handoff ファイル** と **git タグ** で行う
- 完了条件は `Check-PhaseDone.ps1` で機械的に検証
- 承認ポイントでは自動進行を停止しユーザー判断を仰ぐ

## ファイル構成

```
project-root\
├── orchestrator.ps1                      # メインスクリプト
├── Check-PhaseDone.ps1                   # 完了条件チェック
├── requirements.md                       # 要件定義
├── implementation_prompts_subdivided.md  # サブ分割プロンプト
├── ORCHESTRATION.md                      # 本ドキュメント
├── logs\                                 # 実行ログ（自動生成）
└── .orchestrator_state                   # 最終完了サブステップ記録（自動生成）
```

## 事前準備

### 1. PowerShell 実行ポリシーの設定

Windows 標準では PowerShell スクリプトの実行が制限されています。**初回1度だけ**以下を実行してください。

PowerShell を**管理者ではなく通常モード**で起動し、以下を実行：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

確認のプロンプトが出たら `Y` を入力。

これは「ローカルで作成したスクリプトは実行可能、ネットからダウンロードしたスクリプトは署名要」という設定です。CurrentUser スコープなので、システム全体には影響しません。

### 2. 必須ツールのインストール確認

PowerShell で以下を実行し、すべてバージョンが表示されることを確認：

```powershell
python --version    # Python 3.11.x 以上
node --version      # v18 以上
git --version       # 任意のバージョン
claude --version    # Claude Code が見えること
```

Claude Code がない場合：

```powershell
npm install -g @anthropic-ai/claude-code
claude --version
```

初回起動時に Anthropic アカウントの認証が必要です。

```powershell
claude
```

ブラウザでログインを求められるので案内に従ってください。

### 3. ファイル配置と初期化

```powershell
# 作業ディレクトリ作成
mkdir $HOME\meeting-scheduler-test
cd $HOME\meeting-scheduler-test

# 4ファイルをこのディレクトリに配置
# - orchestrator.ps1
# - Check-PhaseDone.ps1
# - requirements.md
# - implementation_prompts_subdivided.md

# git 初期化（orchestrator.ps1 が自動でも行うが、明示する方が安全）
git init
git config user.name "Your Name"
git config user.email "your@email.com"
git add requirements.md implementation_prompts_subdivided.md orchestrator.ps1 Check-PhaseDone.ps1
git commit -m "chore: initial commit"
```

### 4. GCP プロジェクトの準備

Phase 1.3 までに必要です。**Phase 1.1 と 1.2 だけのテスト実行なら不要**です。

詳細は別途案内した GCP セットアップ手順を参照。完了状態は以下です。

- GCP プロジェクト作成
- Forms API / Drive API 有効化
- OAuth 同意画面（External / Testing / テストユーザー登録）
- OAuth クライアントID（Webアプリ、リダイレクトURI: `http://localhost:8000/api/auth/google/callback`）
- ダウンロードした JSON ファイルを `%APPDATA%\meeting-scheduler\config\oauth_client.json` に配置（このフォルダは Phase 1.1 実行で自動作成される）

## 使い方

### 全サブステップを順番に実行

```powershell
.\orchestrator.ps1
```

### サブステップ一覧と完了状況を確認

```powershell
.\orchestrator.ps1 -List
```

完了済みには `✓`、承認ポイントには `[要承認]` が表示されます。

### 特定サブステップから再開

```powershell
.\orchestrator.ps1 -Resume 3.2
```

### 単一サブステップのみ実行

```powershell
.\orchestrator.ps1 -Only 1.1
```

### 実行計画の確認（dry-run）

```powershell
.\orchestrator.ps1 -DryRun
.\orchestrator.ps1 -DryRun -Resume 4.1
```

## 自動進行の挙動

### 通常サブステップ

1. Claude Code を headless モード（`claude -p`）で起動
2. プロンプトを渡して実装
3. `Check-PhaseDone.ps1` で完了条件を検証
4. 成功なら次のサブステップへ自動進行
5. 失敗ならスクリプトを停止し、再開コマンドを表示

### 承認ポイント

以下のサブステップは自動進行を停止し、ユーザーの確認を求めます。

| Phase | 承認内容 |
|---|---|
| 2.0 | Forms API 調査結果と採用方針 |
| 3.3 | スケジューラのソフト制約挙動 |
| 4.4 | DnD画面の操作確認 |
| 5.1 | PDFレイアウト |

### 既に完了済みのサブステップに当たった場合

`git tag` が既に存在する場合、スキップ/再実行/中断を選択できます。

## 失敗時の対処

### `Check-PhaseDone.ps1` で失敗した場合

完了条件のうち何が満たされていないか具体的に表示されます。

例：

```
Phase 3.2 完了条件チェック
  [OK] handoff ファイル存在: docs\handoff_phase3_2.md
  [NG] git tag がありません: phase3.2-done
  [OK] 未コミットの変更なし
  [OK] backend\app\services\scheduler.py 存在
  [OK] backend\tests\test_scheduler_hard.py 存在
  [NG] TDD: 'test(phase3.2)' を含む commit が見つかりません

Phase 3.2: 2 件の完了条件未達
```

対処は以下のいずれか：

1. **手動で完了処理を行う**（タグを打つ、handoff 作成等）してから `-Resume` で次から実行
2. **当該サブステップを再実行**：`.\orchestrator.ps1 -Only 3.2`
3. **ログを確認**：`logs\phase_3.2_*.log`

### Claude Code が途中で停止した場合

ログを確認して原因特定後、再実行：

```powershell
.\orchestrator.ps1 -Resume <停止したphase>
```

### テストが失敗する場合

`Check-PhaseDone.ps1` は完了時に `pytest` と `vitest` を実行します。失敗時は Claude Code 側でテストを通せていない状態です。

## ログ

実行ログは `logs\phase_<phase>_<timestamp>.log` に保存されます。

Claude Code の `stream-json` 出力をそのまま記録します。

## Windows 固有の注意事項

### `--dangerously-skip-permissions` について

`orchestrator.ps1` は Claude Code をこのオプション付きで起動します。Claude Code が任意のファイル操作・コマンド実行を確認なしで行えます。

- **専用のディレクトリで実行すること**
- 本番環境や重要ファイルがある場所では実行しないこと

### Windows Defender の影響

Python 仮想環境作成や node_modules インストール時に Defender のリアルタイム保護で時間がかかる場合があります。実用上は問題なし。あまりに遅い場合は、作業ディレクトリを Defender の除外設定に追加することを検討。

### 文字化けが発生する場合

PowerShell の文字化けは典型的な問題です。以下を `$PROFILE` に追加すると恒久的に解決します。

```powershell
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
```

`$PROFILE` ファイルの場所は `notepad $PROFILE` で開けます（存在しない場合は作成）。

### パス区切り

PowerShell では `\` と `/` の両方が動作しますが、本プロジェクトのスクリプトは `\` で統一しています。Claude Code が生成する Python コードでは `pathlib.Path` を使うため、内部的にOS差異が吸収されます。

### Claude Code API レート制限

19 サブステップを連続実行するとトークン消費が大きくなります。Anthropic のレート制限・契約プランを確認してください。

### 並列実行は不可

サブステップは前後依存があるため、`orchestrator.ps1` を複数並列起動しないでください。

## トラブルシューティング

### 「`...の読み込みができません。デジタル署名されていません`」

実行ポリシーが設定されていません。事前準備1を再度確認。

### 「`claude`: コマンドが見つかりません」

Claude Code がインストールされていないか、PATHが通っていません。`npm install -g @anthropic-ai/claude-code` を再度実行し、PowerShell を再起動。

### Python・Node のバージョンが古い

新しいバージョンをインストールしてください。`pyenv-win` や `nvm-windows` を使うとバージョン管理が楽になります。

### git の認証エラー

`git config --global user.name` と `user.email` が設定されているか確認。
