<#
.SYNOPSIS
  本番モード起動スクリプト（Phase 4.1）

.DESCRIPTION
  フロントエンドをビルドし、FastAPI がビルド済みフロントを配信する「本番モード」で起動する。
  requirements.md §2.2 の start.ps1 に相当する。

  起動後、ブラウザで http://localhost:8000 にアクセスする。

.NOTES
  - フロントのビルドは毎回実行される（ソース変更を反映するため）
  - バックエンド開発中は start-dev.ps1 を使うこと（--reload あり）
  - 本番モードでは uvicorn を --reload なしで起動する

.EXAMPLE
  pwsh .\scripts\start.ps1
  $env:MEETING_SCHEDULER_PORT=8001; pwsh .\scripts\start.ps1
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$backendDir = Join-Path $repoRoot "backend"
$frontendDir = Join-Path $repoRoot "frontend"
$venvDir = Join-Path $backendDir ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$pyprojectFile = Join-Path $backendDir "pyproject.toml"
$installedMarker = Join-Path $venvDir ".phase1_1_installed"

$port = $env:MEETING_SCHEDULER_PORT
if ([string]::IsNullOrWhiteSpace($port)) { $port = "8000" }

Write-Host "[start] repository root: $repoRoot"
Write-Host "[start] port           : $port"

# ===== バックエンドのセットアップ =====

if (-not (Test-Path $venvPython)) {
    Write-Host "[start] 仮想環境を作成します: $venvDir"
    python -m venv $venvDir
    if ($LASTEXITCODE -ne 0) { throw "python -m venv に失敗しました" }
}

$needInstall = $false
if (-not (Test-Path $installedMarker)) {
    $needInstall = $true
} else {
    $markerTime = (Get-Item $installedMarker).LastWriteTimeUtc
    $pyprojectTime = (Get-Item $pyprojectFile).LastWriteTimeUtc
    if ($pyprojectTime -gt $markerTime) { $needInstall = $true }
}

if ($needInstall) {
    Write-Host "[start] 依存をインストールします..."
    & $venvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "pip upgrade に失敗しました" }
    & $venvPython -m pip install -e $backendDir
    if ($LASTEXITCODE -ne 0) { throw "pip install に失敗しました" }
    Set-Content -Path $installedMarker -Value (Get-Date -Format "o") -Encoding UTF8
}

# ===== フロントエンドビルド =====

Write-Host "[start] フロントエンドをビルドします..."
$nodeModulesDir = Join-Path $frontendDir "node_modules"
if (-not (Test-Path $nodeModulesDir)) {
    Write-Host "[start] npm install を実行します..."
    Push-Location $frontendDir
    try {
        npm install
        if ($LASTEXITCODE -ne 0) { throw "npm install に失敗しました" }
    } finally {
        Pop-Location
    }
}

Push-Location $frontendDir
try {
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "npm run build に失敗しました" }
} finally {
    Pop-Location
}

Write-Host "[start] ビルド完了: $frontendDir\dist"

# ===== FastAPI 起動（本番モード）=====

Write-Host "[start] uvicorn を起動します (http://localhost:$port)"
Write-Host "[start] ブラウザで http://localhost:$port を開いてください"
Push-Location $backendDir
try {
    & $venvPython -m uvicorn app.main:app --port $port
} finally {
    Pop-Location
}