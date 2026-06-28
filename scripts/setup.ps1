<#
.SYNOPSIS
  初回セットアップスクリプト (Phase 1.1)

.DESCRIPTION
  - Python のバージョンチェック (3.11+)
  - 仮想環境の作成: backend\.venv
  - 依存インストール: backend\.venv\Scripts\pip install -e backend

.EXAMPLE
  pwsh .\scripts\setup.ps1
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$backendDir = Join-Path $repoRoot "backend"
$venvDir = Join-Path $backendDir ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

Write-Host "[setup] repository root: $repoRoot"

# 1. Python バージョンチェック (3.11+)
$pythonExe = "python"
try {
    $versionOutput = & $pythonExe --version 2>&1
} catch {
    throw "python コマンドが見つかりません。Python 3.11+ をインストールしてください。"
}

if ($versionOutput -match "Python (\d+)\.(\d+)\.(\d+)") {
    $major = [int]$Matches[1]
    $minor = [int]$Matches[2]
    Write-Host "[setup] 検出: $versionOutput"
    if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 11)) {
        throw "Python 3.11 以上が必要です (検出: $versionOutput)"
    }
} else {
    throw "Python のバージョンを判定できませんでした: $versionOutput"
}

# 2. 仮想環境作成
if (Test-Path $venvPython) {
    Write-Host "[setup] 仮想環境は既に存在します: $venvDir"
} else {
    Write-Host "[setup] 仮想環境を作成します: $venvDir"
    & $pythonExe -m venv $venvDir
    if ($LASTEXITCODE -ne 0) { throw "python -m venv に失敗しました" }
}

# 3. 依存インストール (editable install)
Write-Host "[setup] pip upgrade ..."
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade に失敗しました" }

Write-Host "[setup] 依存をインストールします: pip install -e backend"
& $venvPython -m pip install -e $backendDir
if ($LASTEXITCODE -ne 0) { throw "pip install -e backend に失敗しました" }

# installed marker (start-dev.ps1 がスキップ判定に使う)
$installedMarker = Join-Path $venvDir ".phase1_1_installed"
Set-Content -Path $installedMarker -Value (Get-Date -Format "o") -Encoding UTF8

Write-Host "[setup] 完了しました。起動は scripts\start-dev.ps1 を実行してください。"
