<#
.SYNOPSIS
  開発モード起動スクリプト（Phase 1.1）

.DESCRIPTION
  バックエンド (FastAPI / uvicorn) を --reload 付きで起動する。
  仮想環境が存在しない場合は作成し、依存も初回インストールする。

.NOTES
  v3 では本スクリプトは Phase 4.1 で拡張される。
    - フロントエンド (Vite dev server) の同時起動
    - 引数 (-Backend / -Frontend / -All) による選択起動
  現時点ではバックエンドのみ起動する最小実装である。

.EXAMPLE
  pwsh .\scripts\start-dev.ps1
  $env:MEETING_SCHEDULER_PORT=8001; pwsh .\scripts\start-dev.ps1
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

# リポジトリルート (このスクリプトの親ディレクトリの親)
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$backendDir = Join-Path $repoRoot "backend"
$venvDir = Join-Path $backendDir ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$pyprojectFile = Join-Path $backendDir "pyproject.toml"
$installedMarker = Join-Path $venvDir ".phase1_1_installed"

# ポート (環境変数 MEETING_SCHEDULER_PORT 既定 8000)
$port = $env:MEETING_SCHEDULER_PORT
if ([string]::IsNullOrWhiteSpace($port)) { $port = "8000" }

Write-Host "[start-dev] repository root: $repoRoot"
Write-Host "[start-dev] backend dir    : $backendDir"
Write-Host "[start-dev] port           : $port"

# 1. 仮想環境作成 (存在しなければ)
if (-not (Test-Path $venvPython)) {
    Write-Host "[start-dev] 仮想環境を作成します: $venvDir"
    python -m venv $venvDir
    if ($LASTEXITCODE -ne 0) {
        throw "python -m venv の実行に失敗しました"
    }
}

# 2. 依存インストール (初回 or pyproject.toml が installed marker より新しい)
$needInstall = $false
if (-not (Test-Path $installedMarker)) {
    $needInstall = $true
} else {
    $markerTime = (Get-Item $installedMarker).LastWriteTimeUtc
    $pyprojectTime = (Get-Item $pyprojectFile).LastWriteTimeUtc
    if ($pyprojectTime -gt $markerTime) { $needInstall = $true }
}

if ($needInstall) {
    Write-Host "[start-dev] 依存をインストールします (pip install -e backend)"
    & $venvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "pip upgrade に失敗しました" }
    & $venvPython -m pip install -e $backendDir
    if ($LASTEXITCODE -ne 0) { throw "pip install -e backend に失敗しました" }
    # marker 更新
    Set-Content -Path $installedMarker -Value (Get-Date -Format "o") -Encoding UTF8
}

# 3. uvicorn を --reload 付きで起動
Write-Host "[start-dev] uvicorn を起動します (http://localhost:$port/api/health)"
Push-Location $backendDir
try {
    & $venvPython -m uvicorn app.main:app --reload --port $port
}
finally {
    Pop-Location
}
