<#
.SYNOPSIS
  開発モード起動スクリプト（Phase 4.1 で拡張）

.DESCRIPTION
  バックエンド (FastAPI / uvicorn) とフロントエンド (Vite dev server) を起動する。
  引数 -Mode で起動対象を切り替えられる:
    All      (既定): バックエンドとフロントエンドを両方起動
    Backend         : バックエンドのみ起動
    Frontend        : フロントエンドのみ起動

  仮想環境が存在しない場合は作成し、依存も初回インストールする。

.NOTES
  v3 ではこのスクリプトは Phase 1.1 から Phase 4.1 で拡張された。
    Phase 1.1: バックエンドのみ起動する最小実装
    Phase 4.1: フロントエンド起動を追加、-Mode 引数で選択起動が可能に

  フロントエンドは npm run dev (Vite) で http://localhost:5173 で起動する。
  本番配信は scripts\start.ps1 を使用すること。

.EXAMPLE
  pwsh .\scripts\start-dev.ps1
  pwsh .\scripts\start-dev.ps1 -Mode Backend
  pwsh .\scripts\start-dev.ps1 -Mode Frontend
  $env:MEETING_SCHEDULER_PORT=8001; pwsh .\scripts\start-dev.ps1
#>

[CmdletBinding()]
param(
    [ValidateSet("All", "Backend", "Frontend")]
    [string]$Mode = "All"
)

$ErrorActionPreference = "Stop"

# リポジトリルート (このスクリプトの親ディレクトリの親)
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$backendDir = Join-Path $repoRoot "backend"
$frontendDir = Join-Path $repoRoot "frontend"
$venvDir = Join-Path $backendDir ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$pyprojectFile = Join-Path $backendDir "pyproject.toml"
$installedMarker = Join-Path $venvDir ".phase1_1_installed"

# ポート (環境変数 MEETING_SCHEDULER_PORT 既定 8000)
$port = $env:MEETING_SCHEDULER_PORT
if ([string]::IsNullOrWhiteSpace($port)) { $port = "8000" }

Write-Host "[start-dev] repository root: $repoRoot"
Write-Host "[start-dev] mode           : $Mode"

# ===== バックエンドのセットアップ（Backend / All モード時） =====

function Setup-Backend {
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
}

# ===== Frontend のセットアップ（Frontend / All モード時） =====

function Setup-Frontend {
    Write-Host "[start-dev] frontend dir   : $frontendDir"

    # node_modules が無ければ npm install
    $nodeModulesDir = Join-Path $frontendDir "node_modules"
    if (-not (Test-Path $nodeModulesDir)) {
        Write-Host "[start-dev] npm install を実行します..."
        Push-Location $frontendDir
        try {
            npm install
            if ($LASTEXITCODE -ne 0) { throw "npm install に失敗しました" }
        } finally {
            Pop-Location
        }
    }
}

# ===== 起動 =====

if ($Mode -eq "All") {
    Setup-Backend
    Setup-Frontend

    # バックエンドを別ウィンドウで起動し、フロントエンドをこのウィンドウで起動
    Write-Host "[start-dev] バックエンドを別ウィンドウで起動します..."
    $thisScript = $PSCommandPath
    Start-Process powershell -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $thisScript, "-Mode", "Backend"

    Write-Host "[start-dev] フロントエンドを起動します (http://localhost:5173)"
    Push-Location $frontendDir
    try {
        npm run dev
    } finally {
        Pop-Location
    }

} elseif ($Mode -eq "Backend") {
    Setup-Backend
    # バックエンドのみ
    Write-Host "[start-dev] uvicorn を起動します (http://localhost:$port/api/health)"
    Push-Location $backendDir
    try {
        & $venvPython -m uvicorn app.main:app --reload --port $port
    } finally {
        Pop-Location
    }

} elseif ($Mode -eq "Frontend") {
    Setup-Frontend
    # フロントエンドのみ
    Write-Host "[start-dev] Vite dev server を起動します (http://localhost:5173)"
    Push-Location $frontendDir
    try {
        npm run dev
    } finally {
        Pop-Location
    }
}