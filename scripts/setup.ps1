<#
.SYNOPSIS
  初回セットアップスクリプト

.DESCRIPTION
  - Python バージョンチェック (3.11+)
  - 仮想環境の作成: backend\.venv
  - バックエンド依存インストール: pip install -e backend
  - フロントエンド依存インストール: npm install
  - %APPDATA%\meeting-scheduler\ 配下のディレクトリ作成（config\、logs\、data\）
  - 完了後のガイダンス表示

.EXAMPLE
  pwsh .\scripts\setup.ps1
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$backendDir = Join-Path $repoRoot "backend"
$frontendDir = Join-Path $repoRoot "frontend"
$venvDir = Join-Path $backendDir ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

Write-Host "[setup] リポジトリルート: $repoRoot"

# ------------------------------------------------------------------
# 1. Python バージョンチェック (3.11+)
# ------------------------------------------------------------------
$pythonExe = "python"
try {
    $versionOutput = & $pythonExe --version 2>&1
} catch {
    Write-Error "python コマンドが見つかりません。Python 3.11+ をインストールしてください。"
    exit 1
}

if ($versionOutput -match "Python (\d+)\.(\d+)\.(\d+)") {
    $major = [int]$Matches[1]
    $minor = [int]$Matches[2]
    Write-Host "[setup] 検出: $versionOutput"
    if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 11)) {
        Write-Error "Python 3.11 以上が必要です (検出: $versionOutput)"
        exit 1
    }
} else {
    Write-Error "Python のバージョンを判定できませんでした: $versionOutput"
    exit 1
}

# ------------------------------------------------------------------
# 2. Node.js チェック (18+)
# ------------------------------------------------------------------
try {
    $nodeVersionOutput = & node --version 2>&1
    Write-Host "[setup] Node.js 検出: $nodeVersionOutput"
    if ($nodeVersionOutput -match "v(\d+)\.") {
        $nodeMajor = [int]$Matches[1]
        if ($nodeMajor -lt 18) {
            Write-Error "Node.js 18 以上が必要です (検出: $nodeVersionOutput)"
            exit 1
        }
    }
} catch {
    Write-Error "node コマンドが見つかりません。Node.js 18+ をインストールしてください。"
    exit 1
}

# ------------------------------------------------------------------
# 3. Python 仮想環境作成
# ------------------------------------------------------------------
if (Test-Path $venvPython) {
    Write-Host "[setup] 仮想環境は既に存在します: $venvDir"
} else {
    Write-Host "[setup] 仮想環境を作成します: $venvDir"
    & $pythonExe -m venv $venvDir
    if ($LASTEXITCODE -ne 0) {
        Write-Error "python -m venv に失敗しました"
        exit 1
    }
}

# ------------------------------------------------------------------
# 4. バックエンド依存インストール
# ------------------------------------------------------------------
Write-Host "[setup] pip をアップグレードします..."
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    Write-Error "pip upgrade に失敗しました"
    exit 1
}

Write-Host "[setup] バックエンド依存をインストールします (pip install -e backend)..."
& $venvPython -m pip install -e $backendDir
if ($LASTEXITCODE -ne 0) {
    Write-Error "pip install -e backend に失敗しました"
    exit 1
}

# installed marker (start.ps1 / start-dev.ps1 がスキップ判定に使う)
$installedMarker = Join-Path $venvDir ".phase1_1_installed"
Set-Content -Path $installedMarker -Value (Get-Date -Format "o") -Encoding UTF8

# ------------------------------------------------------------------
# 5. フロントエンド依存インストール
# ------------------------------------------------------------------
Write-Host "[setup] フロントエンド依存をインストールします (npm install)..."
$nodeModulesDir = Join-Path $frontendDir "node_modules"
if (Test-Path $nodeModulesDir) {
    Write-Host "[setup] node_modules は既に存在します。スキップします。"
} else {
    Push-Location $frontendDir
    try {
        npm install
        if ($LASTEXITCODE -ne 0) {
            Write-Error "npm install に失敗しました"
            exit 1
        }
    } finally {
        Pop-Location
    }
}

# ------------------------------------------------------------------
# 6. %APPDATA%\meeting-scheduler\ 配下ディレクトリ作成
# ------------------------------------------------------------------
$appData = $env:APPDATA
if ([string]::IsNullOrWhiteSpace($appData)) {
    $appData = Join-Path $env:USERPROFILE "AppData\Roaming"
}
$dataRoot = Join-Path $appData "meeting-scheduler"

Write-Host "[setup] データディレクトリを作成します: $dataRoot"
foreach ($subDir in @("config", "logs", "data", "projects")) {
    $dir = Join-Path $dataRoot $subDir
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "[setup]   作成: $dir"
    } else {
        Write-Host "[setup]   既存: $dir"
    }
}

# ------------------------------------------------------------------
# 完了メッセージ
# ------------------------------------------------------------------
Write-Host ""
Write-Host "======================================================"
Write-Host " セットアップ完了！"
Write-Host "======================================================"
Write-Host ""
Write-Host "次のステップ:"
Write-Host "  1. Google OAuth クライアント情報を配置してください:"
Write-Host "     $dataRoot\config\oauth_client.json"
Write-Host "     (GCP コンソールから JSON をダウンロードし、上記パスへ配置)"
Write-Host ""
Write-Host "  2. 起動スクリプトを実行してください:"
Write-Host "     pwsh .\scripts\start.ps1"
Write-Host "     ブラウザで http://localhost:8000 を開く"
Write-Host ""
Write-Host "  詳細は README.md を参照してください。"
