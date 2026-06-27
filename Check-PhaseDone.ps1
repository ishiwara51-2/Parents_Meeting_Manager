<#
.SYNOPSIS
  指定サブステップの完了条件を機械的にチェックする

.PARAMETER PhaseId
  チェック対象のサブステップID（例: "1.1"）

.EXAMPLE
  .\Check-PhaseDone.ps1 -PhaseId 1.1
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$PhaseId
)

$ErrorActionPreference = "Continue"
$script:errors = 0

function Test-CheckPass { param([string]$Msg) Write-Host "  [OK] $Msg" -ForegroundColor Green }
function Test-CheckFail { param([string]$Msg) Write-Host "  [NG] $Msg" -ForegroundColor Red; $script:errors++ }

Write-Host "Phase $PhaseId 完了条件チェック" -ForegroundColor Cyan

$phaseIdEscaped = $PhaseId -replace '\.', '_'
$handoffFile = Join-Path "docs" "handoff_phase${phaseIdEscaped}.md"

# ===== 共通チェック =====

# 1. handoff ファイル存在
if (Test-Path $handoffFile) {
    Test-CheckPass "handoff ファイル存在: $handoffFile"
} else {
    Test-CheckFail "handoff ファイルがありません: $handoffFile"
}

# 2. git tag 存在
$existingTag = git tag -l "phase${PhaseId}-done" 2>$null
if ($existingTag) {
    Test-CheckPass "git tag 存在: phase${PhaseId}-done"
} else {
    Test-CheckFail "git tag がありません: phase${PhaseId}-done"
}

# 3. 未コミット変更がないこと
$gitStatus = git status --porcelain 2>$null
if ([string]::IsNullOrWhiteSpace($gitStatus)) {
    Test-CheckPass "未コミットの変更なし"
} else {
    Test-CheckFail "未コミットの変更があります（git status で確認）"
}

# ===== Phase 固有チェック =====

function Test-FileExists {
    param([string]$RelativePath)
    if (Test-Path $RelativePath) {
        Test-CheckPass "$RelativePath 存在"
    } else {
        Test-CheckFail "$RelativePath がありません"
    }
}

function Test-TddCommit {
    param([string]$PhaseId)
    $gitLog = git log --oneline 2>$null
    if ($gitLog -match "test\(phase$([regex]::Escape($PhaseId))\)") {
        Test-CheckPass "TDD: test commit が記録されている"
    } else {
        Test-CheckFail "TDD: 'test(phase$PhaseId)' を含む commit が見つかりません"
    }
}

switch ($PhaseId) {
    "1.1" {
        Test-FileExists "backend\app\main.py"
        Test-FileExists "backend\app\config.py"
        Test-FileExists "backend\pyproject.toml"
        Test-FileExists ".gitignore"
        Test-FileExists ".gitattributes"
        Test-FileExists "scripts\start-dev.ps1"
        Test-FileExists "scripts\setup.ps1"
    }
    "1.2" {
        Test-FileExists "backend\app\repositories"
        Test-FileExists "backend\app\models"
        Test-FileExists "backend\app\repositories\base.py"
    }
    "1.3" {
        Test-FileExists "backend\app\services\google_auth.py"
        Test-FileExists "backend\tests\test_google_auth.py"
        Test-TddCommit -PhaseId "1.3"
    }
    "2.0" {
        Test-FileExists "docs\forms_api_research.md"
    }
    "2.1" {
        Test-FileExists "backend\tests\test_project_api.py"
        Test-TddCommit -PhaseId "2.1"
    }
    "2.2" {
        Test-FileExists "backend\app\services\google_forms.py"
        Test-FileExists "backend\tests\test_google_forms_service.py"
        Test-TddCommit -PhaseId "2.2"
    }
    "2.3" {
        Test-FileExists "backend\app\services\polling.py"
        Test-FileExists "backend\tests\test_polling_service.py"
        Test-TddCommit -PhaseId "2.3"
    }
    "3.1" {
        Test-FileExists "backend\tests\test_rules_api.py"
        Test-TddCommit -PhaseId "3.1"
    }
    "3.2" {
        Test-FileExists "backend\app\services\scheduler.py"
        Test-FileExists "backend\tests\test_scheduler_hard.py"
        Test-TddCommit -PhaseId "3.2"
    }
    "3.3" {
        Test-FileExists "backend\tests\test_scheduler_soft.py"
        Test-FileExists "backend\tests\test_schedule_api.py"
        Test-TddCommit -PhaseId "3.3"
    }
    "3.4" {
        Test-FileExists "backend\tests\test_drafts_api.py"
        Test-TddCommit -PhaseId "3.4"
    }
    "4.1" {
        Test-FileExists "frontend\package.json"
        Test-FileExists "frontend\vite.config.ts"
        Test-FileExists "frontend\src\api"
    }
    { $_ -in "4.2", "4.3", "4.4" } {
        Test-TddCommit -PhaseId $PhaseId
    }
    "5.1" {
        Test-FileExists "backend\app\services\pdf_generator.py"
        Test-FileExists "backend\tests\test_pdf_generator.py"
        Test-FileExists "docs\pdf_decisions.md"
        Test-TddCommit -PhaseId "5.1"
    }
    "5.2" {
        Test-FileExists "backend\tests\test_pdf_api.py"
        Test-TddCommit -PhaseId "5.2"
    }
    "6.1" {
        Test-FileExists "docs\e2e_test.md"
        Test-FileExists "backend\app\logging_config.py"
    }
    "6.2" {
        Test-FileExists "README.md"
        Test-FileExists "docs\limitations.md"
        $releaseTag = git tag -l "v0.1.0-prototype" 2>$null
        if ($releaseTag) {
            Test-CheckPass "リリースタグ v0.1.0-prototype 存在"
        } else {
            Test-CheckFail "リリースタグ v0.1.0-prototype がありません"
        }
    }
    default {
        Write-Host "  (Phase $PhaseId 固有チェックは定義されていません。共通チェックのみ実施)"
    }
}

# ===== pytest 実行 =====
if (Test-Path "backend\pyproject.toml") {
    Write-Host "  pytest 実行中..."
    Push-Location "backend"
    try {
        $venvPython = Join-Path ".venv" "Scripts\python.exe"
        if (Test-Path $venvPython) {
            $pytestResult = & $venvPython -m pytest --tb=short -q 2>&1
            $pytestExit = $LASTEXITCODE
        } else {
            $pytestResult = & python -m pytest --tb=short -q 2>&1
            $pytestExit = $LASTEXITCODE
        }
        if ($pytestExit -eq 0) {
            Test-CheckPass "pytest 全パス"
        } else {
            Test-CheckFail "pytest が失敗しました"
            Write-Host $pytestResult
        }
    }
    finally {
        Pop-Location
    }
}

# ===== vitest 実行 (Phase 4.1 以降) =====
if ($PhaseId -in "4.1", "4.2", "4.3", "4.4", "5.2", "6.1", "6.2") {
    if (Test-Path "frontend\package.json") {
        Write-Host "  vitest 実行中..."
        Push-Location "frontend"
        try {
            $vitestResult = & npm test -- --run 2>&1
            $vitestExit = $LASTEXITCODE
            if ($vitestExit -eq 0) {
                Test-CheckPass "vitest 全パス"
            } else {
                Test-CheckFail "vitest が失敗しました"
            }
        }
        finally {
            Pop-Location
        }
    }
}

# ===== 集計 =====
Write-Host ""
if ($script:errors -eq 0) {
    Write-Host "Phase $PhaseId: 完了条件を満たしています" -ForegroundColor Green
    exit 0
} else {
    Write-Host "Phase $PhaseId: $($script:errors) 件の完了条件未達" -ForegroundColor Red
    exit 1
}
