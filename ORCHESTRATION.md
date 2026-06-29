# 運用手順書（v3.3：audit trail方式）

**v3.3 変更点（v3.2 から）**：
- サブエージェントのモデル使い分け（Sonnet/Opus）を導入
- 22サブステップ中 Opus 使用は 4 つのみ（2.0、3.2、3.3a、3.3b）、残り 18 は Sonnet
- メインエージェントは引き続き Opus 推奨

**v3.2 変更点（v3.1 から）**：
- `Check-PhaseDone.ps1` 修正の運用ルール（承認制）を追加
- `audit_trail_integrity` チェックが `fix(check):` と `chore(approval):` プレフィックスを正規扱いに

**v3.1 変更点（v3 から）**：
- パイロット実装で判明した知見を反映
- カテゴリ1：PowerShell 構文の堅牢化（`${variable}:` 表記の徹底、構文事前検証手順を追加）
- カテゴリ2：エンコーディング管理の重要性昇格（事前準備で「必須」明記、検証コマンド追加、トラブルシューティング詳細化）
- カテゴリ3：原則4「スクリプト改竄の禁止」の境界明確化（`main_agent_prompt.md` および `implementation_prompts_subdivided.md` を更新）

本ドキュメントは、保護者面談調整ツールのプロトタイプ実装を、Claude Code の対話モードで進めるための運用ガイドである。

## v3 の設計思想

### audit trail（事後監査）として再定義

v2 では「改竄防止」を謳っていたが、Claude Code が完了条件チェックも改竄検知も同じ権限で実行できる構造のため、構造的に完全防止は不可能。v3 では設計目的を **「事後 audit trail（監査履歴）の確保」** に再定義した。

- Claude Code による完全な改竄防止は構造的に保証しない
- 代わりに、すべてのチェック実行を git commit で履歴に残し、ユーザーが事後に検証可能とする
- スクリプト自己ハッシュ記録のような無効な機構は廃止
- 監査トレイル整合性チェック（直前 Check 時の HEAD から現在の HEAD までの不審コミット検知）を強化

### サブエージェント委譲方式

```
[ユーザー]
   ↓ 指示
[Claude Code メインエージェント（司令塔）= Opus]
   ├─ Task で Phase 1.1 実装サブエージェント起動 (Sonnet)
   │    └─ サブエージェントが実装、完了報告
   ├─ メインが Check-PhaseDone.ps1 を実行
   ├─ 結果（PASS時はサマリ / FAIL時は全文）をユーザーに提示
   ├─ Task で Phase 1.2 実装サブエージェント起動 (Sonnet)
   ├─ ... Phase 2.0 のみ Opus、Phase 3.2/3.3a/3.3b も Opus
   └─ ...
```

### モデル使い分け（v3.3 で導入）

22サブステップ中、複雑な設計判断が必要な4サブステップのみ Opus、残り18サブステップは Sonnet を使用してコストを抑える。

| カテゴリ | 対象 Phase | モデル | 数 |
|---|---|---|---|
| 複雑な設計判断 | 2.0、3.2、3.3a、3.3b | Opus | 4 |
| 定型的な実装 | 上記以外（1.1〜2.3、3.1、3.4、4.x、5.x、6.x） | Sonnet | 18 |
| メインエージェント | 全体の進行管理 | Opus | - |

詳細は `main_agent_prompt.md` のサブエージェントモデル割当表を参照。

### v3 の主要変更点（v2 から）

1. **Phase 3.3 を 3.3a/3.3b に分割**：ソフト制約モデルと API 統合・パフォーマンステストを分離
2. **Phase 4.4 を 4.4a/4.4b/4.4c に分割**：マトリクス表示、DnD、保存・保存完了画面を段階化
3. **全22サブステップ**（v2: 19 → v3: 22）
4. **TDD 厳格検証**：test commit 時点で `git checkout` + `pytest` を実機実行し、テストが実際に失敗していたことを検証
5. **完了条件の実効性強化**：実コンポーネントファイル存在チェック、キーワード grep、Phase 1.1 の実機ヘルスチェック
6. **承認ポイントの機械的 enforce**：JSON に `approval_required` と `next_phase_blocked` フラグ、承認ファイル `check_results\approvals\phase_<id>.approved` をユーザーが手動作成
7. **失敗時の詳細ログ**：pytest/vitest 失敗時、最後80行を別ファイルに保存
8. **同一エラー2回連続で停止**：3回固定ループから、無駄な反復を回避
9. **OAuth state パラメータ**：CSRF 対策を Phase 1.3 で実装

## ファイル構成

```
project-root\
├── main_agent_prompt.md                  # メインエージェント司令塔プロンプト
├── implementation_prompts_subdivided.md  # 各サブステップ詳細プロンプト
├── requirements.md                       # 要件定義
├── Check-PhaseDone.ps1                   # 完了条件チェック
├── ORCHESTRATION.md                      # 本ドキュメント
├── check_results\                        # JSON結果ファイル（自動生成、git管理）
│   ├── phase_<id>_<ts>.json
│   ├── phase_<id>_<ts>.pytest.log
│   └── approvals\
│       └── phase_<id>.approved           # ユーザーが手動作成
└── docs\                                 # 各種ドキュメント（自動生成）
    └── handoff_phase<id>.md
```

## 事前準備

> **⚠️ 重要：以下の手順を順番通りに実行してください。特にステップ4のエンコーディング設定は必須です（PowerShell スクリプトが日本語を含むため、BOM 付き UTF-8 でないと構文エラーになります）。**

### 1. PowerShell 実行ポリシー設定（初回1度のみ）

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### 2. 必須ツールのインストール確認

```powershell
python --version    # 3.11+
node --version      # 18+
git --version
claude --version
```

Claude Code 未インストール時：

```powershell
npm install -g @anthropic-ai/claude-code
claude  # 初回認証
```

### 3. 作業ディレクトリと初期化

```powershell
mkdir $HOME\meeting-scheduler
cd $HOME\meeting-scheduler

# 5ファイルをこのディレクトリに配置：
#   - main_agent_prompt.md
#   - implementation_prompts_subdivided.md
#   - requirements.md
#   - Check-PhaseDone.ps1
#   - ORCHESTRATION.md（本書）
```

### 4. 【必須】ダウンロードファイルのブロック解除と BOM 付き UTF-8 変換

PowerShell 5.1 は BOM なしの UTF-8 ファイルを日本語環境で読むとき Shift-JIS として解釈してしまうため、PowerShell スクリプトは必ず **BOM 付き UTF-8** で保存する必要があります。

```powershell
# 4-1. ブロック解除（ダウンロードファイルの実行を許可）
Get-ChildItem -Path . -Filter *.ps1 | Unblock-File

# 4-2. BOM 付き UTF-8 に変換（PowerShell スクリプト全て）
Get-ChildItem -Path . -Filter *.ps1 | ForEach-Object {
    $content = Get-Content -Path $_.FullName -Raw -Encoding UTF8
    $utf8WithBom = New-Object System.Text.UTF8Encoding $true
    [System.IO.File]::WriteAllText($_.FullName, $content, $utf8WithBom)
    Write-Host "Converted to UTF-8 BOM: $($_.Name)"
}

# 4-3. BOM が正しく付与されているか確認
Get-ChildItem -Path . -Filter *.ps1 | ForEach-Object {
    $bytes = [System.IO.File]::ReadAllBytes($_.FullName)[0..2]
    $hex = ($bytes | ForEach-Object { $_.ToString("X2") }) -join " "
    $hasBom = ($hex -eq "EF BB BF")
    $status = if ($hasBom) { "[OK]" } else { "[NG]" }
    Write-Host "$status $($_.Name): $hex"
}
# 全ファイルが [OK] EF BB BF であることを確認
```

### 5. git 初期化

```powershell
git init
git config user.name "Your Name"
git config user.email "your@email.com"
git add *.md *.ps1
git commit -m "chore: initial commit"
```

### 6. PowerShell 構文の事前検証（推奨）

`Check-PhaseDone.ps1` の構文を実行前に検証します。

```powershell
$tokens = $null
$errors = $null
[System.Management.Automation.Language.Parser]::ParseFile(
    "$PWD\Check-PhaseDone.ps1", [ref]$tokens, [ref]$errors
) | Out-Null
if ($errors.Count -eq 0) {
    Write-Host "[OK] Check-PhaseDone.ps1 syntax is valid"
} else {
    Write-Host "[NG] Syntax errors found:"
    $errors | ForEach-Object { Write-Host "  $($_.Message) at line $($_.Extent.StartLineNumber)" }
}
```

エラーがあれば本番開始前に対処すること。

### 7. GCP プロジェクトの準備

Phase 1.3 以降で必要。Phase 1.1/1.2 のテストのみなら不要。

- GCP プロジェクト作成
- Forms API / Drive API 有効化
- OAuth 同意画面（External / Testing / テストユーザー登録）
- OAuth クライアントID（Webアプリ、リダイレクトURI: `http://localhost:8000/api/auth/google/callback`）
- ダウンロードした JSON ファイルを `%APPDATA%\meeting-scheduler\config\oauth_client.json` に配置

メインエージェントは Phase 1.3 着手前にこの配置を確認する。

## 実行方法

### 起動

```powershell
cd $HOME\meeting-scheduler
claude
```

### メインエージェントへの初回指示

Claude Code が起動したら、以下を入力：

```
main_agent_prompt.md を読み、その役割に従ってください。
その後、implementation_prompts_subdivided.md に従って Phase 1.1 から実装を開始してください。
```

### 単一サブステップのみ実行

```
main_agent_prompt.md を読み、その役割に従ってください。
Phase 1.1 だけ実行してください。
```

### 途中再開

```
main_agent_prompt.md を読み、その役割に従ってください。
Phase 3.2 から再開してください。
```

メインエージェントは前サブステップの完了タグ存在と、最新の `chore(check):` コミットハッシュを取得して進める。

## 進行中の挙動

### 通常サブステップ

1. メインエージェントが「Phase X.Y を開始します」と宣言
2. **監査トレイル整合性確認**：`git diff HEAD -- check_results\ Check-PhaseDone.ps1`
3. Task ツールでサブエージェント起動
4. サブエージェントが実装作業
5. メインエージェントが Bash ツールで `Check-PhaseDone.ps1 -PhaseId <id> -LastCheckCommit <前回のhash>` を実行
6. 結果を提示（PASS 時はサマリ / FAIL 時は全文）
7. 判定結果に応じて次へ進む / 再実装 / 承認待ち

### 承認ポイント（Phase 2.0, 3.3b, 4.4c, 5.1）

JSON で `approval_required: true` かつ `next_phase_blocked: true` の場合、メインエージェントが停止します。

ユーザーは以下の手順で承認：

```powershell
# 承認確認後（JSON 内容や実機動作を確認した上で）
New-Item check_results\approvals\phase_<id>.approved -ItemType File
git add check_results\approvals\phase_<id>.approved
git commit -m "chore(approval): phase <id> approved"
```

その後、メインエージェントに「承認完了しました」と伝える。

### 失敗時の自動再実装

`Check-PhaseDone.ps1` が NG → メインが修正サブエージェントを起動。以下のルール：

- 最大3回まで
- **同一エラーが2回連続で出たら3回目を待たず停止**
- environment 系（OAuth未設定、ネットワーク等）は1回目で即ユーザーエスカレート

## 監査トレイルの確認

各 Check-PhaseDone.ps1 実行のたびに git に `chore(check): phase X.Y result PASS/FAIL` がコミットされる。ユーザーは以下で履歴確認可能：

```powershell
# 全 check 実行履歴
git log --oneline --grep="chore(check)"

# 最新の結果ファイル
Get-ChildItem check_results -Filter "phase_*.json" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1 |
    Get-Content

# 特定 Phase の結果（複数あれば再実装の履歴）
Get-ChildItem check_results -Filter "phase_1.1_*.json"

# 承認履歴
git log --oneline --grep="chore(approval)"
Get-ChildItem check_results\approvals
```

## 監査トレイル整合性チェックの仕組み

`Check-PhaseDone.ps1` は以下2つの観点で監査トレイルを検証する：

### 1. 直前 Check 実行時の HEAD から現在の HEAD までの不審コミット検知

`-LastCheckCommit <hash>` 引数（前回 check 実行直後の HEAD ハッシュ）を渡すと、その範囲内で `check_results\` と `Check-PhaseDone.ps1` への変更コミットを抽出し、以下の正規プレフィックス以外のコミットメッセージがあれば FAIL とする：

- `chore(check):` — `Check-PhaseDone.ps1` 自身による自動コミット
- `fix(check):` — ユーザー承認済みの修正コミット（後述）
- `chore(approval):` — 承認ファイルのコミット

つまり、サブエージェントが結果ファイルを編集して `git add && git commit -m "fix: manual correction"` のように偽装しようとしても、メッセージ規則の不一致で検知される。

### 2. Check-PhaseDone.ps1 自身に未コミット変更がないこと

`git diff HEAD -- Check-PhaseDone.ps1` で差分が出れば FAIL。スクリプトを書き換えた状態でチェックが実行されるのを防ぐ。

### 限界（誠実な説明）

以下は構造上検知できない：

- **メインエージェント自身がスキップを偽装**：「チェックを実行しました」と虚偽報告し、実際は走らせない
- **git history rewrite**：`git filter-branch`, `git rebase -i` で過去を改変
- **正規メッセージ偽装**：`chore(check):`、`fix(check):`、`chore(approval):` というメッセージで偽の結果ファイルをコミット
- **`check_results\` のディレクトリ削除**：その後の `Check-PhaseDone.ps1` 実行で再生成されるため検知不能

これらは事後監査の限界として受け入れる。プロトタイプ用途として許容される範囲と判断。

## Check-PhaseDone.ps1 修正の運用ルール（承認制）

`Check-PhaseDone.ps1` 自体にバグが見つかった場合（パイロットでは `$PhaseId:` 構文エラーや BOM 欠落が発生）、以下のフローで修正する。

### Claude Code 側のフロー

1. Claude Code（メインまたはサブ）が問題を発見
2. 自分では修正せず、以下を含めてユーザーに報告：
   - 問題のあるファイルと箇所（行番号含む）
   - 問題の症状
   - 問題の原因の分析
   - 推奨される修正方法（diff または patch 形式）
3. ユーザーの明示的な承認を待つ
4. 承認後、最小限の修正を実施
5. `fix(check):` プレフィックスでコミット：
   ```bash
   git commit -m "fix(check): <修正内容の要約>"
   ```

### ユーザー側の対応

Claude Code から修正提案を受け取ったら：

1. 提案内容（diff）を確認
2. 妥当と判断したら「承認します」「進めてください」など明示的に承認
3. 不適切と判断したら却下し、代替方針を指示
4. 修正実施後、`Check-PhaseDone.ps1` を BOM 付き UTF-8 で保存し直されているかを確認

### 許可される修正範囲

- 構文エラーの修正
- エンコーディング修正（BOM の付け外し）
- 改行コード変換
- 軽微なバグ修正

### 承認があっても禁止される変更

- 新規ロジックの追加（チェック項目の追加など）
- 関数定義の大幅な書き換え
- 結果ファイル（JSON）の編集・削除
- 詳細ログファイルの編集・削除
- 承認ファイルの作成・編集・削除

これらが必要な場合は、本番フローを一時停止し、設計レベルから見直す。

## トラブルシューティング

### PowerShell スクリプトのエンコーディング問題（最頻出）

PowerShell 5.1 は BOM なし UTF-8 を日本語環境で Shift-JIS として解釈するため、PowerShell スクリプト内の日本語が文字化けして構文エラーになります。

**症状例**：

```
発生場所 ... :54 文字:14
+     @{ Id = "3.3"; Desc = "繧ｹ繧ｱ繧ｸ繝･繝ｼ繝ｩ・医た繝輔ヨ蛻ｶ邏・ｿｽ蜉・峨→ API
式またはステートメントのトークン '3.3"; Desc = "繧ｹ繧ｱ繧ｸ繝･...' を使用できません。
```

**対処**：BOM 付き UTF-8 に変換し直す。

```powershell
Get-ChildItem -Path . -Filter *.ps1 | ForEach-Object {
    $content = Get-Content -Path $_.FullName -Raw -Encoding UTF8
    $utf8WithBom = New-Object System.Text.UTF8Encoding $true
    [System.IO.File]::WriteAllText($_.FullName, $content, $utf8WithBom)
}
```

**注意点**：
- `sed`、`Set-Content`（既定エンコーディング）、`Out-File`（既定エンコーディング）、エディタの保存時のエンコーディング選択ミスなどで簡単に BOM が落ちます
- PowerShell スクリプトを変更したら、**毎回必ず**上記の変換を実施し、事前準備 4-3 のチェックで BOM 有無を確認すること

### PowerShell の `$variable:` 構文エラー

`$variable:` のような表記は PowerShell ではスコープ修飾子（`$env:`、`$script:` など）として解釈されます。文字列中で変数名のあとに `:` を続けたい場合は `${variable}:` のように波括弧で囲む必要があります。

**症状例**：

```
式またはステートメントのトークン '<変数名>:' を使用できません。
```

**対処**：

```powershell
# 誤
Write-Host "Phase $PhaseId: [PASS]"

# 正
Write-Host "Phase ${PhaseId}: [PASS]"
```

### 「`...の読み込みができません。デジタル署名されていません`」

実行ポリシーが設定されていません。事前準備 1 を実施。

### サブエージェントが期待通り動かない

メインエージェントが「Phase X.Y で失敗が続いています」と報告し、3回試行後または同一エラー2回連続後に停止した場合：

1. JSON 結果ファイルで失敗項目を確認
2. 詳細ログ（`.pytest.log` 等）も確認
3. 必要に応じて要件定義や詳細プロンプトを修正
4. メインエージェントに再開指示：「Phase X.Y を再度実行してください」

### 承認ポイントを通り過ぎてしまった

`check_results\approvals\phase_<id>.approved` が存在せず次フェーズが進んでしまった場合：

1. メインエージェントに「Phase <id> の承認をスキップしたようなので、進行を止めて確認してください」と指示
2. 現状の実装を確認した上で、後追いで承認ファイルを作る場合：

```powershell
New-Item check_results\approvals\phase_<id>.approved -ItemType File
git add check_results\approvals\phase_<id>.approved
git commit -m "chore(approval): phase <id> approved (retroactive)"
```

### Check-PhaseDone.ps1 がエラーで終了する

スクリプト自体の問題の可能性。以下を確認：

```powershell
# 構文チェック
powershell -NoProfile -Command "& {[scriptblock]::Create((Get-Content .\Check-PhaseDone.ps1 -Raw))}"

# 手動実行で詳細エラー
.\Check-PhaseDone.ps1 -PhaseId 1.1 -Verbose
```

### TDD 厳格検証が遅い

`Check-PhaseDone.ps1` は test commit 時点で `git checkout` + `pytest` を実行する（数十秒）。これは TDD の本質的な検証（テストが本当に最初は失敗していたか）のために必要な処理。

どうしても遅くて困る場合は、`Check-PhaseDone.ps1` の `Test-TddCommitOrder` 関数内の TDD strict verification ブロックをコメントアウト可能。ただし TDD 形骸化検知能力は下がる。

## コンテキスト管理

メインエージェントは 22 サブステップを通して動くため、コンテキスト圧迫の可能性がある。推奨：

- **Phase 2.3、3.4、4.4c 完了時にセッション再起動**
- 再起動指示：`Phase X.Y から再開してください`
- 再起動後、メインエージェントは git tag と handoff ファイルから状態復元

メインエージェントがコンテキスト枯渇の兆候（応答の省略、原則の忘却、承認ポイントの見落とし）を見せたら、即セッション再起動を指示する。

## 注意事項

### コスト

22 サブステップ通すと相応のトークンを消費。Anthropic の契約プランに応じて確認。

### 中断と再開

git タグと handoff ファイルが残るため、いつでも途中から再開可能。

### 設計判断が必要な場面

メインエージェントは設計判断が必要な場面でユーザー確認するよう指示されているが、見落とす可能性もある。サブエージェントの実装内容に疑問があれば、いつでも進行を止めて確認可能：

- `いったん止めて、Phase 3.2 の実装内容を要約してください`
- `次のサブステップに進む前に、現在の Repository 抽象化の設計を確認したい`

## パイロット実装（着手前推奨）

22 サブステップ本実行前に、以下のパイロットで設計を検証することを推奨：

### パイロット1：サブエージェント委譲の挙動確認

`hello.txt` 作成のような最小タスクで、メインエージェントが以下を実際に行うか確認：

- Task ツールでサブエージェントを起動するか（自分で Edit/Write を使い始めないか）
- サブエージェントが Check-PhaseDone.ps1 を勝手に走らせないか
- メインが Bash で Check-PhaseDone.ps1 を実行するか
- 監査トレイル整合性確認（`git diff HEAD -- check_results\ Check-PhaseDone.ps1`）を本当に実行するか
- 結果提示の原則（PASS 時サマリ、FAIL 時全文）を守るか

### パイロット2：改竄シナリオ

意図的に Check-PhaseDone.ps1 の switch 文を一時編集してみる、JSON ファイルを手動編集 + commit してみる、等で監査トレイル整合性チェックが機能するか確認。

### パイロット3：コンテキスト消費の実測

Phase 1.1〜1.3 の3サブステップを流し、メインのコンテキスト消費レートから Phase 6.2 まで持つかを試算。

これらのパイロットで C1/C2/C3 系の問題が早期発見できる。
