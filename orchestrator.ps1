<#
.SYNOPSIS
  保護者面談調整ツール プロトタイプ実装の自動進行スクリプト（Windows版）

.DESCRIPTION
  implementation_prompts_subdivided.md に定義された各サブステップを、
  Claude Code の headless モードで順次実行する。

.PARAMETER Resume
  指定サブステップから再開

.PARAMETER Only
  単一サブステップのみ実行

.PARAMETER DryRun
  実行計画だけ表示

.PARAMETER List
  サブステップ一覧と完了状態を表示

.EXAMPLE
  .\orchestrator.ps1
  .\orchestrator.ps1 -Resume 3.2
  .\orchestrator.ps1 -Only 1.1
  .\orchestrator.ps1 -DryRun
  .\orchestrator.ps1 -List
#>

[CmdletBinding()]
param(
    [string]$Resume,
    [string]$Only,
    [switch]$DryRun,
    [switch]$List,
    [switch]$Help
)

$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8

# ===================== 設定 =====================
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PromptsFile = Join-Path $ScriptDir "implementation_prompts_subdivided.md"
$RequirementsFile = Join-Path $ScriptDir "requirements.md"
$LogDir = Join-Path $ScriptDir "logs"
$StateFile = Join-Path $ScriptDir ".orchestrator_state"
$CheckScript = Join-Path $ScriptDir "Check-PhaseDone.ps1"

# サブステップ一覧（順序通り）
$Phases = @(
    @{ Id = "1.1"; Desc = "プロジェクト初期化と FastAPI 骨格" }
    @{ Id = "1.2"; Desc = "Repository 抽象化の骨格" }
    @{ Id = "1.3"; Desc = "Google OAuth2 認証フロー" }
    @{ Id = "2.0"; Desc = "Forms API 仕様調査"; RequireApproval = $true }
    @{ Id = "2.1"; Desc = "プロジェクト管理 API" }
    @{ Id = "2.2"; Desc = "Google Form 作成" }
    @{ Id = "2.3"; Desc = "回答ポーリングと変換" }
    @{ Id = "3.1"; Desc = "ルール管理 API" }
    @{ Id = "3.2"; Desc = "スケジューラ（ハード制約のみ）" }
    @{ Id = "3.3"; Desc = "スケジューラ（ソフト制約追加）と API"; RequireApproval = $true }
    @{ Id = "3.4"; Desc = "ドラフト保存・ロック管理" }
    @{ Id = "4.1"; Desc = "フロントエンド初期化とAPIクライアント" }
    @{ Id = "4.2"; Desc = "ホーム画面とプロジェクト一覧" }
    @{ Id = "4.3"; Desc = "プロジェクト画面とForm連携UI" }
    @{ Id = "4.4"; Desc = "日程案表示画面（ドラッグ&ドロップ）"; RequireApproval = $true }
    @{ Id = "5.1"; Desc = "PDF生成サービス"; RequireApproval = $true }
    @{ Id = "5.2"; Desc = "PDF出力API・UI" }
    @{ Id = "6.1"; Desc = "E2E 動作確認とログ整備" }
    @{ Id = "6.2"; Desc = "README とリリース準備" }
)

# ===================== ユーティリティ =====================
function Write-Info  { param([string]$Msg) Write-Host "[INFO]  $Msg" -ForegroundColor Cyan }
function Write-Ok    { param([string]$Msg) Write-Host "[OK]    $Msg" -ForegroundColor Green }
function Write-Warn  { param([string]$Msg) Write-Host "[WARN]  $Msg" -ForegroundColor Yellow }
function Write-Err   { param([string]$Msg) Write-Host "[ERROR] $Msg" -ForegroundColor Red }

function Test-NeedsApproval {
    param([string]$PhaseId)
    $phase = $Phases | Where-Object { $_.Id -eq $PhaseId }
    return $phase -and $phase.RequireApproval -eq $true
}

function Find-PhaseIndex {
    param([string]$PhaseId)
    for ($i = 0; $i -lt $Phases.Count; $i++) {
        if ($Phases[$i].Id -eq $PhaseId) { return $i }
    }
    return -1
}

# ===================== 前提チェック =====================
function Test-Preflight {
    Write-Info "前提チェック中..."

    # Claude Code
    $claudeCmd = Get-Command claude -ErrorAction SilentlyContinue
    if (-not $claudeCmd) {
        Write-Err "claude コマンドが見つかりません。Claude Code をインストールしてください。"
        Write-Err "  npm install -g @anthropic-ai/claude-code"
        exit 1
    }

    # Git
    $gitCmd = Get-Command git -ErrorAction SilentlyContinue
    if (-not $gitCmd) {
        Write-Err "git コマンドが見つかりません。Git for Windows をインストールしてください。"
        exit 1
    }

    # Python
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCmd) {
        Write-Err "python コマンドが見つかりません。Python 3.11+ をインストールしてください。"
        exit 1
    }

    # Python バージョン確認（3.11+）
    $pyVersion = & python --version 2>&1
    if ($pyVersion -match "Python (\d+)\.(\d+)") {
        $major = [int]$Matches[1]
        $minor = [int]$Matches[2]
        if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 11)) {
            Write-Err "Python 3.11+ が必要です。検出: $pyVersion"
            exit 1
        }
    }

    # 必須ファイル
    if (-not (Test-Path $PromptsFile)) {
        Write-Err "プロンプトファイルが見つかりません: $PromptsFile"
        exit 1
    }
    if (-not (Test-Path $RequirementsFile)) {
        Write-Err "要件定義ファイルが見つかりません: $RequirementsFile"
        exit 1
    }
    if (-not (Test-Path $CheckScript)) {
        Write-Err "完了チェックスクリプトが見つかりません: $CheckScript"
        exit 1
    }

    # gitリポジトリ初期化
    Push-Location $ScriptDir
    try {
        $gitDir = git rev-parse --git-dir 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-Warn "gitリポジトリが初期化されていません。初期化します。"
            git init | Out-Null
            git add $RequirementsFile, $PromptsFile 2>$null | Out-Null
            git commit -m "chore: initial commit with requirements and prompts" --allow-empty | Out-Null
        }
    }
    finally {
        Pop-Location
    }

    if (-not (Test-Path $LogDir)) {
        New-Item -ItemType Directory -Path $LogDir | Out-Null
    }

    Write-Ok "前提チェック完了"
}

# ===================== サブステップ実行 =====================
function Invoke-Phase {
    param([string]$PhaseId)

    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $logFile = Join-Path $LogDir "phase_${PhaseId}_${timestamp}.log"

    Write-Info "============================================================"
    Write-Info "Phase $PhaseId 開始"
    Write-Info "============================================================"

    # 既に完了済みかチェック
    Push-Location $ScriptDir
    try {
        $existingTag = git tag -l "phase${PhaseId}-done" 2>$null
        if ($existingTag) {
            Write-Warn "Phase $PhaseId は既に完了タグが存在します。"
            $choice = Read-Host "(y=スキップ / n=再実行 / q=中断)"
            switch ($choice) {
                "y" { Write-Info "Phase $PhaseId をスキップ"; return $true }
                "Y" { Write-Info "Phase $PhaseId をスキップ"; return $true }
                "q" { Write-Info "ユーザーにより中断"; exit 0 }
                "Q" { Write-Info "ユーザーにより中断"; exit 0 }
                default { Write-Info "Phase $PhaseId を再実行" }
            }
        }
    }
    finally {
        Pop-Location
    }

    # プロンプト構築
    $phaseIdEscaped = $PhaseId -replace '\.', '_'
    $prompt = @"
implementation_prompts_subdivided.md の Phase $PhaseId を実装してください。

開始前に以下を実施:
1. requirements.md を通読
2. 当該フェーズの先行サブステップの docs\handoff_*.md を通読
3. 「Phase $PhaseId に着手します」と宣言してから実装開始

Windows ネイティブ環境（PowerShell）前提のため、パス区切りや改行コードに注意してください。

テスト駆動の指示があるサブステップでは、
テストファースト → RED確認 → test commit → 実装 → GREEN確認 → implementation commit
の順序を厳守してください。

完了時:
- 完了条件チェックリストを報告
- docs\handoff_phase${phaseIdEscaped}.md を作成
- git tag phase${PhaseId}-done を打つ
"@

    Write-Info "Claude Code を起動します（headlessモード）..."
    Write-Info "ログ出力先: $logFile"

    # Claude Code 実行
    Push-Location $ScriptDir
    try {
        # Windows 上で claude コマンドを実行
        # 出力を tee 的にファイルとコンソール両方に
        $claudeOutput = & claude -p $prompt --output-format stream-json --verbose --dangerously-skip-permissions 2>&1
        $claudeOutput | Tee-Object -FilePath $logFile

        if ($LASTEXITCODE -ne 0) {
            Write-Err "Phase $PhaseId 実行中にエラー (exit code: $LASTEXITCODE)"
            return $false
        }
    }
    finally {
        Pop-Location
    }

    Write-Info "Phase $PhaseId 実行終了。完了条件チェック..."

    # 完了条件チェック
    Push-Location $ScriptDir
    try {
        & $CheckScript -PhaseId $PhaseId
        if ($LASTEXITCODE -ne 0) {
            Write-Err "Phase $PhaseId の完了条件を満たしていません"
            Write-Err "ログを確認してください: $logFile"
            return $false
        }
    }
    finally {
        Pop-Location
    }

    # 承認ポイント
    if (Test-NeedsApproval -PhaseId $PhaseId) {
        Write-Warn "Phase $PhaseId は承認ポイントです"
        Show-ApprovalInfo -PhaseId $PhaseId
        $approval = Read-Host "次のサブステップに進んでよいですか？ (y/n/q)"
        switch ($approval) {
            "y" { Write-Ok "承認されました" }
            "Y" { Write-Ok "承認されました" }
            "q" { Write-Info "ユーザーにより中断"; exit 0 }
            "Q" { Write-Info "ユーザーにより中断"; exit 0 }
            default { Write-Err "承認されませんでした。中断します。"; exit 1 }
        }
    }

    Write-Ok "Phase $PhaseId 完了"
    Set-Content -Path $StateFile -Value $PhaseId -Encoding UTF8
    return $true
}

function Show-ApprovalInfo {
    param([string]$PhaseId)
    switch ($PhaseId) {
        "2.0" {
            Write-Warn "=== Phase 2.0 承認確認事項 ==="
            Write-Warn "docs\forms_api_research.md を確認してください"
            $researchFile = Join-Path $ScriptDir "docs\forms_api_research.md"
            if (Test-Path $researchFile) {
                Get-Content $researchFile -Head 50
            }
        }
        "3.3" {
            Write-Warn "=== Phase 3.3 承認確認事項 ==="
            Write-Warn "スケジューラのソフト制約挙動を確認してください"
        }
        "4.4" {
            Write-Warn "=== Phase 4.4 承認確認事項 ==="
            Write-Warn "DnD画面を実機で操作確認してください"
            Write-Warn "起動: .\scripts\start-dev.ps1"
        }
        "5.1" {
            Write-Warn "=== Phase 5.1 承認確認事項 ==="
            Write-Warn "生成されたサンプルPDFを確認してください"
        }
    }
}

# ===================== コマンドハンドリング =====================
function Invoke-List {
    Write-Info "サブステップ一覧:"
    Push-Location $ScriptDir
    try {
        foreach ($phase in $Phases) {
            $marker = ""
            $tagExists = git tag -l "phase$($phase.Id)-done" 2>$null
            if ($tagExists) { $marker = " ✓" }

            $approval = ""
            if ($phase.RequireApproval) { $approval = " [要承認]" }

            Write-Host "  Phase $($phase.Id)$approval$marker - $($phase.Desc)"
        }
    }
    finally {
        Pop-Location
    }
}

function Invoke-DryRun {
    param([int]$StartIdx = 0)
    Write-Info "実行計画（dry-run）:"
    for ($i = $StartIdx; $i -lt $Phases.Count; $i++) {
        $phase = $Phases[$i]
        $approval = ""
        if ($phase.RequireApproval) { $approval = " [要承認]" }
        Write-Host "  $($i+1). Phase $($phase.Id)$approval - $($phase.Desc)"
    }
}

function Invoke-Run {
    param(
        [int]$StartIdx = 0,
        [int]$OnlyIdx = -1
    )

    Test-Preflight

    if ($OnlyIdx -ge 0) {
        $success = Invoke-Phase -PhaseId $Phases[$OnlyIdx].Id
        if (-not $success) { exit 1 }
        return
    }

    for ($i = $StartIdx; $i -lt $Phases.Count; $i++) {
        $success = Invoke-Phase -PhaseId $Phases[$i].Id
        if (-not $success) {
            Write-Err "Phase $($Phases[$i].Id) で失敗。中断します。"
            Write-Info "再開コマンド: .\orchestrator.ps1 -Resume $($Phases[$i].Id)"
            exit 1
        }
    }

    Write-Ok "============================================================"
    Write-Ok "全サブステップ完了"
    Write-Ok "============================================================"
}

function Show-Usage {
    @"
使い方:
  .\orchestrator.ps1                       全サブステップを最初から実行
  .\orchestrator.ps1 -Resume <phase>       指定サブステップから再開（例: -Resume 3.2）
  .\orchestrator.ps1 -Only <phase>         単一サブステップのみ実行
  .\orchestrator.ps1 -DryRun [-Resume <phase>]  実行計画を表示
  .\orchestrator.ps1 -List                 サブステップ一覧と完了状態を表示
  .\orchestrator.ps1 -Help                 このメッセージを表示
"@ | Write-Host
}

# ===================== エントリポイント =====================
if ($Help) {
    Show-Usage
    exit 0
}

if ($List) {
    Invoke-List
    exit 0
}

if ($DryRun) {
    $idx = 0
    if ($Resume) {
        $idx = Find-PhaseIndex -PhaseId $Resume
        if ($idx -lt 0) {
            Write-Err "不明なサブステップ: $Resume"
            exit 1
        }
    }
    Invoke-DryRun -StartIdx $idx
    exit 0
}

if ($Resume) {
    $idx = Find-PhaseIndex -PhaseId $Resume
    if ($idx -lt 0) {
        Write-Err "不明なサブステップ: $Resume"
        exit 1
    }
    Invoke-Run -StartIdx $idx
    exit 0
}

if ($Only) {
    $idx = Find-PhaseIndex -PhaseId $Only
    if ($idx -lt 0) {
        Write-Err "不明なサブステップ: $Only"
        exit 1
    }
    Invoke-Run -OnlyIdx $idx
    exit 0
}

Invoke-Run
