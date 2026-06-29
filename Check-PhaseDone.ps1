<#
.SYNOPSIS
  指定サブステップの完了条件を機械的にチェックし、結果をJSONファイルに出力する（v3）

.DESCRIPTION
  チェック結果は以下に出力される:
    - コンソール（人間の目視確認用）
    - .\check_results\phase_<id>_<timestamp>.json（事後 audit trail 用）
    - 失敗時は .\check_results\phase_<id>_<timestamp>.pytest.log 等の詳細ログも

  本スクリプトは「事後 audit trail」を目的としており、
  Claude Code による完全な改竄防止は構造的に保証していない。
  すべてのチェック実行は git commit され、git log で追跡可能とすることで
  事後検証可能性を確保する。

.PARAMETER PhaseId
  チェック対象のサブステップID（例: "1.1"）

.PARAMETER LastCheckCommit
  直前の Check-PhaseDone.ps1 実行時の HEAD コミットハッシュ（省略可）
  指定された場合、そのコミットから現在の HEAD までの check_results\ と Check-PhaseDone.ps1 の
  変更履歴を確認し、不審なコミットがないか検証する

.EXAMPLE
  .\Check-PhaseDone.ps1 -PhaseId 1.1
  .\Check-PhaseDone.ps1 -PhaseId 1.2 -LastCheckCommit abc123
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$PhaseId,
    [string]$LastCheckCommit = ""
)

$ErrorActionPreference = "Continue"
$script:errors = 0
$script:checks = @()
$script:detailLogs = @{}

# ===== 承認ポイント定義 =====
$ApprovalPhases = @("2.0", "3.3b", "4.4c", "5.1")
$IsApprovalPhase = $ApprovalPhases -contains $PhaseId

# ===== 出力ファイル準備 =====
$resultDir = Join-Path $PWD "check_results"
if (-not (Test-Path $resultDir)) {
    New-Item -ItemType Directory -Path $resultDir | Out-Null
}

$approvalsDir = Join-Path $resultDir "approvals"
if (-not (Test-Path $approvalsDir)) {
    New-Item -ItemType Directory -Path $approvalsDir | Out-Null
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$resultFile = Join-Path $resultDir "phase_${PhaseId}_${timestamp}.json"
$pytestLogFile = Join-Path $resultDir "phase_${PhaseId}_${timestamp}.pytest.log"
$vitestLogFile = Join-Path $resultDir "phase_${PhaseId}_${timestamp}.vitest.log"

function Test-CheckPass {
    param([string]$Name, [string]$Detail = "")
    Write-Host "  [OK] $Name $Detail" -ForegroundColor Green
    $script:checks += @{
        name = $Name
        result = "PASS"
        detail = $Detail
    }
}

function Test-CheckFail {
    param([string]$Name, [string]$Detail = "", [string]$LogFile = "")
    Write-Host "  [NG] $Name $Detail" -ForegroundColor Red
    $script:errors++
    $check = @{
        name = $Name
        result = "FAIL"
        detail = $Detail
    }
    if ($LogFile -ne "") {
        $check.log_file = $LogFile
    }
    $script:checks += $check
}

Write-Host "Phase $PhaseId 完了条件チェック (v3)" -ForegroundColor Cyan
if ($IsApprovalPhase) {
    Write-Host "  [承認ポイント] このサブステップは PASS 後もユーザー承認が必要です" -ForegroundColor Yellow
}

$phaseIdEscaped = $PhaseId -replace '\.', '_'
$handoffFile = Join-Path "docs" "handoff_phase${phaseIdEscaped}.md"

# ===== 監査トレイル整合性チェック =====
# 直前 Check 実行時の HEAD から現在の HEAD までで、check_results\ と Check-PhaseDone.ps1 への
# 不審な変更がないかを確認する。
if ($LastCheckCommit -ne "") {
    $changesInRange = git log --oneline "${LastCheckCommit}..HEAD" -- check_results\ Check-PhaseDone.ps1 2>$null
    if ($changesInRange) {
        # 正規プレフィックス: chore(check): は自動コミット、fix(check): はユーザー承認済みの修正、chore(approval): は承認ファイル
        $suspiciousCommits = $changesInRange | Where-Object {
            $_ -notmatch "chore\(check\):" -and
            $_ -notmatch "fix\(check\):" -and
            $_ -notmatch "chore\(approval\):"
        }
        if ($suspiciousCommits) {
            Test-CheckFail "audit_trail_integrity" "Suspicious commits affecting check_results\ or Check-PhaseDone.ps1: $($suspiciousCommits -join '; ')"
        } else {
            Test-CheckPass "audit_trail_integrity" "All changes in range use legitimate prefixes (chore(check), fix(check), chore(approval))"
        }
    } else {
        Test-CheckPass "audit_trail_integrity" "No changes in audit-protected paths"
    }
}

# Check-PhaseDone.ps1 自身に未コミット変更がないか
$scriptDiff = git diff HEAD -- Check-PhaseDone.ps1 2>$null
if ([string]::IsNullOrWhiteSpace($scriptDiff)) {
    Test-CheckPass "check_script_unmodified" "Check-PhaseDone.ps1 has no uncommitted changes"
} else {
    Test-CheckFail "check_script_unmodified" "Check-PhaseDone.ps1 has uncommitted changes"
}

# ===== 共通チェック =====

# 1. handoff ファイル存在
if (Test-Path $handoffFile) {
    Test-CheckPass "handoff_file_exists" "$handoffFile"
} else {
    Test-CheckFail "handoff_file_exists" "$handoffFile not found"
}

# 2. git tag 存在
$existingTag = git tag -l "phase${PhaseId}-done" 2>$null
if ($existingTag) {
    Test-CheckPass "git_tag_exists" "phase${PhaseId}-done"

    # タグが HEAD を指していること（タグ後は fix(check):/chore(check):/chore(approval): のみ許容）
    $tagCommit = git rev-list -n 1 "phase${PhaseId}-done" 2>$null
    $headCommit = git rev-parse HEAD 2>$null
    if ($tagCommit -eq $headCommit) {
        Test-CheckPass "tag_at_head" "tag matches HEAD"
    } else {
        # タグから HEAD までのコミットが正規プレフィックスのみであれば許容（audit_trail_integrity と整合）
        $commitsAfterTag = git log --oneline "${tagCommit}..HEAD" 2>$null
        $illegitimateAfterTag = $commitsAfterTag | Where-Object {
            $_ -notmatch "chore\(check\):" -and
            $_ -notmatch "fix\(check\):" -and
            $_ -notmatch "chore\(approval\):"
        }
        if ($illegitimateAfterTag) {
            Test-CheckFail "tag_at_head" "tag is not at HEAD and illegitimate commits exist after tag: $($illegitimateAfterTag -join '; ')"
        } else {
            Test-CheckPass "tag_at_head" "tag is not at HEAD but only audit-prefix commits follow (tag=$tagCommit, head=$headCommit)"
        }
    }
} else {
    Test-CheckFail "git_tag_exists" "phase${PhaseId}-done not found"
}

# 3. 未コミット変更がないこと（check_results 配下とログファイルは除外）
$gitStatus = git status --porcelain 2>$null | Where-Object {
    $_ -notmatch '^.{2}\s+check_results[\\/]'
}
if ([string]::IsNullOrWhiteSpace($gitStatus)) {
    Test-CheckPass "no_uncommitted_changes"
} else {
    Test-CheckFail "no_uncommitted_changes" "Uncommitted changes: $($gitStatus -join '; ')"
}

# ===== Phase 固有チェック =====

function Test-FileExists {
    param([string]$RelativePath, [string]$CheckName = "file_exists")
    if (Test-Path $RelativePath) {
        Test-CheckPass $CheckName "$RelativePath"
    } else {
        Test-CheckFail $CheckName "$RelativePath not found"
    }
}

function Test-FileContainsAll {
    param([string]$RelativePath, [string[]]$Keywords, [string]$CheckName = "file_contains")
    if (-not (Test-Path $RelativePath)) {
        Test-CheckFail $CheckName "$RelativePath not found"
        return
    }
    $content = Get-Content -Path $RelativePath -Raw -Encoding UTF8
    $missing = @()
    foreach ($kw in $Keywords) {
        if ($content -notmatch [regex]::Escape($kw)) {
            $missing += $kw
        }
    }
    if ($missing.Count -eq 0) {
        Test-CheckPass $CheckName "$RelativePath contains all required keywords"
    } else {
        Test-CheckFail $CheckName "$RelativePath missing keywords: $($missing -join ', ')"
    }
}

function Test-TddCommitOrder {
    param([string]$PhaseId)
    # 直前タグから HEAD までの範囲で test/feat コミットの順序を確認
    # 直前タグが特定できない場合は最近のコミット履歴で確認
    $prevTag = $null
    $allTags = git tag -l "phase*-done" 2>$null | Sort-Object
    $currentTagIndex = -1
    for ($i = 0; $i -lt $allTags.Count; $i++) {
        if ($allTags[$i] -eq "phase${PhaseId}-done") {
            $currentTagIndex = $i
            break
        }
    }
    if ($currentTagIndex -gt 0) {
        $prevTag = $allTags[$currentTagIndex - 1]
    }

    $range = if ($prevTag) { "${prevTag}..phase${PhaseId}-done" } else { "phase${PhaseId}-done" }
    $commits = git log --reverse --format="%H %s" $range 2>$null
    if (-not $commits) {
        Test-CheckFail "tdd_commit_exists" "no commits in range $range"
        return
    }

    $testCommitIndex = -1
    $featCommitIndex = -1
    $testCommitHash = $null
    $idx = 0
    foreach ($line in $commits) {
        if ($line -match "test\(phase$([regex]::Escape($PhaseId))\)") {
            if ($testCommitIndex -eq -1) {
                $testCommitIndex = $idx
                $testCommitHash = ($line -split " ")[0]
            }
        }
        if ($line -match "feat\(phase$([regex]::Escape($PhaseId))\)") {
            if ($featCommitIndex -eq -1) {
                $featCommitIndex = $idx
            }
        }
        $idx++
    }

    if ($testCommitIndex -eq -1) {
        Test-CheckFail "tdd_test_commit" "test(phase$PhaseId) not found in range $range"
        return
    }
    Test-CheckPass "tdd_test_commit" "test(phase$PhaseId) found at index $testCommitIndex"

    if ($featCommitIndex -eq -1) {
        Test-CheckFail "tdd_feat_commit" "feat(phase$PhaseId) not found in range $range"
        return
    }

    if ($testCommitIndex -lt $featCommitIndex) {
        Test-CheckPass "tdd_order" "test commit (idx=$testCommitIndex) before feat commit (idx=$featCommitIndex)"
    } else {
        Test-CheckFail "tdd_order" "test commit must come before feat commit"
    }

    # TDD 厳格検証: test commit 時点でテストが失敗していたことを確認
    # test commit で追加されたテストファイル所在 (backend/ or frontend/) を判定し、
    # それぞれ pytest / vitest を実行する
    if ($testCommitHash) {
        $testFilesAdded = git diff-tree --no-commit-id --name-only -r $testCommitHash 2>$null |
            Where-Object { $_ -match "(^|/)tests?/.*\.(py|ts|tsx)$" }
        $hasBackendTests = @($testFilesAdded | Where-Object { $_ -match "^backend/" }).Count -gt 0
        $hasFrontendTests = @($testFilesAdded | Where-Object { $_ -match "^frontend/" }).Count -gt 0

        Write-Host "    TDD strict verification (checkout test commit and run tests)..."
        $currentBranch = git rev-parse --abbrev-ref HEAD 2>$null
        $currentCommit = git rev-parse HEAD 2>$null
        try {
            git stash push --include-untracked --keep-index -m "phase-check-stash" 2>&1 | Out-Null
            git checkout $testCommitHash 2>&1 | Out-Null

            $tddExit = 0
            if ($hasBackendTests -and (Test-Path "backend\pyproject.toml")) {
                Push-Location "backend"
                try {
                    $venvPython = Join-Path ".venv" "Scripts\python.exe"
                    if (Test-Path $venvPython) {
                        & $venvPython -m pytest --tb=no -q 2>&1 | Out-Null
                    } else {
                        & python -m pytest --tb=no -q 2>&1 | Out-Null
                    }
                    if ($LASTEXITCODE -ne 0) { $tddExit = 1 }
                }
                finally {
                    Pop-Location
                }
            }
            if ($hasFrontendTests -and (Test-Path "frontend\package.json")) {
                Push-Location "frontend"
                try {
                    & npm test -- --run 2>&1 | Out-Null
                    if ($LASTEXITCODE -ne 0) { $tddExit = 1 }
                }
                finally {
                    Pop-Location
                }
            }

            git checkout $currentCommit 2>&1 | Out-Null
            git stash pop 2>&1 | Out-Null

            if ($tddExit -ne 0) {
                Test-CheckPass "tdd_strict_red" "tests failed at test commit (as expected for TDD RED)"
            } else {
                Test-CheckFail "tdd_strict_red" "tests passed at test commit (TDD violation: tests must fail at RED)"
            }
        } catch {
            # checkout 失敗時は元に戻す
            git checkout $currentCommit 2>&1 | Out-Null
            git stash pop 2>&1 | Out-Null
            Test-CheckFail "tdd_strict_red" "verification failed: $($_.Exception.Message)"
        }
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

        # 実機動作確認: uvicorn 起動 → /api/health 叩く
        Write-Host "    Phase 1.1 動作確認: uvicorn 起動 + ヘルスチェック..."
        $testPort = 18000
        $procStarted = $false
        try {
            $proc = Start-Process -FilePath "powershell" `
                -ArgumentList "-NoProfile","-Command","cd backend; .\.venv\Scripts\python.exe -m uvicorn app.main:app --port $testPort" `
                -PassThru -WindowStyle Hidden -ErrorAction Stop
            $procStarted = $true
            Start-Sleep -Seconds 6

            try {
                $r = Invoke-WebRequest "http://localhost:${testPort}/api/health" -UseBasicParsing -TimeoutSec 5
                if ($r.StatusCode -eq 200) {
                    Test-CheckPass "health_endpoint_200" "GET /api/health returned 200"
                } else {
                    Test-CheckFail "health_endpoint_200" "got status $($r.StatusCode)"
                }
            } catch {
                Test-CheckFail "health_endpoint_200" $_.Exception.Message
            }
        } catch {
            Test-CheckFail "uvicorn_startup" "could not start uvicorn: $($_.Exception.Message)"
        }
        finally {
            if ($procStarted -and $proc) {
                try { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue } catch {}
            }
        }
    }
    "1.2" {
        Test-FileExists "backend\app\repositories"
        Test-FileExists "backend\app\models"
        Test-FileExists "backend\app\repositories\base.py"
    }
    "1.3" {
        Test-FileExists "backend\app\services\google_auth.py"
        Test-FileExists "backend\tests\test_google_auth.py"
        Test-TddCommitOrder -PhaseId "1.3"
        # OAuth state パラメータの実装確認
        Test-FileContainsAll "backend\app\services\google_auth.py" @("state") -CheckName "oauth_state_param_implemented"
        Test-FileContainsAll "backend\tests\test_google_auth.py" @("state") -CheckName "oauth_state_param_tested"
    }
    "2.0" {
        Test-FileExists "docs\forms_api_research.md"
        # 必須キーワード grep
        Test-FileContainsAll "docs\forms_api_research.md" @(
            "matrix", "代替", "responses.list", "整数", "クォータ", "scope", "採用方式"
        ) -CheckName "forms_api_research_completeness"
    }
    "2.1" {
        Test-FileExists "backend\tests\test_project_api.py"
        Test-TddCommitOrder -PhaseId "2.1"
    }
    "2.2" {
        Test-FileExists "backend\app\services\google_forms.py"
        Test-FileExists "backend\tests\test_google_forms_service.py"
        Test-TddCommitOrder -PhaseId "2.2"
    }
    "2.3" {
        Test-FileExists "backend\app\services\polling.py"
        Test-FileExists "backend\tests\test_polling_service.py"
        Test-TddCommitOrder -PhaseId "2.3"
    }
    "3.1" {
        Test-FileExists "backend\tests\test_rules_api.py"
        Test-TddCommitOrder -PhaseId "3.1"
    }
    "3.2" {
        Test-FileExists "backend\app\services\scheduler.py"
        Test-FileExists "backend\tests\test_scheduler_hard.py"
        Test-TddCommitOrder -PhaseId "3.2"
    }
    "3.3a" {
        Test-FileExists "backend\tests\test_scheduler_soft.py"
        Test-TddCommitOrder -PhaseId "3.3a"
    }
    "3.3b" {
        Test-FileExists "backend\tests\test_schedule_api.py"
        Test-TddCommitOrder -PhaseId "3.3b"
    }
    "3.4" {
        Test-FileExists "backend\tests\test_drafts_api.py"
        Test-TddCommitOrder -PhaseId "3.4"
    }
    "4.1" {
        Test-FileExists "frontend\package.json"
        Test-FileExists "frontend\vite.config.ts"
        Test-FileExists "frontend\src\api"
        # vitest 設定確認
        Test-FileContainsAll "frontend\package.json" @("vitest", "test") -CheckName "vitest_configured"
    }
    "4.2" {
        # 実コンポーネントファイル存在チェック
        Test-FileExists "frontend\src\pages\HomePage.tsx"
        Test-FileExists "frontend\src\pages\ProjectNewPage.tsx"
        Test-FileExists "frontend\src\pages\GlobalRulesPage.tsx"
        Test-TddCommitOrder -PhaseId "4.2"
    }
    "4.3" {
        Test-FileExists "frontend\src\pages\ProjectPage.tsx"
        Test-FileExists "frontend\src\pages\ProjectRulesPage.tsx"
        Test-TddCommitOrder -PhaseId "4.3"
    }
    "4.4a" {
        Test-FileExists "frontend\src\pages\SchedulePage.tsx"
        Test-TddCommitOrder -PhaseId "4.4a"
    }
    "4.4b" {
        # DnD と警告の実装確認
        Test-FileContainsAll "frontend\src\pages\SchedulePage.tsx" @("dnd-kit", "DndContext") -CheckName "dnd_implementation"
        Test-TddCommitOrder -PhaseId "4.4b"
    }
    "4.4c" {
        Test-FileExists "frontend\src\pages\SavedPage.tsx"
        Test-TddCommitOrder -PhaseId "4.4c"
    }
    "5.1" {
        Test-FileExists "backend\app\services\pdf_generator.py"
        Test-FileExists "backend\tests\test_pdf_generator.py"
        Test-FileExists "docs\pdf_decisions.md"
        Test-TddCommitOrder -PhaseId "5.1"
    }
    "5.2" {
        Test-FileExists "backend\tests\test_pdf_api.py"
        Test-TddCommitOrder -PhaseId "5.2"
    }
    "6.1" {
        Test-FileExists "docs\e2e_test.md"
        Test-FileExists "backend\app\logging_config.py"
        Test-FileContainsAll "backend\app\logging_config.py" @("RotatingFileHandler") -CheckName "log_rotation_configured"
    }
    "6.2" {
        Test-FileExists "README.md"
        Test-FileExists "docs\limitations.md"
        $releaseTag = git tag -l "v0.1.0-prototype" 2>$null
        if ($releaseTag) {
            Test-CheckPass "release_tag_exists" "v0.1.0-prototype"
        } else {
            Test-CheckFail "release_tag_exists" "v0.1.0-prototype not found"
        }
    }
    default {
        Write-Host "  (Phase $PhaseId 固有チェックは定義されていません)"
    }
}

# ===== pytest 実行 =====
$pytestCollected = 0
$pytestPassed = 0
if (Test-Path "backend\pyproject.toml") {
    Write-Host "  pytest 実行中..."
    Push-Location "backend"
    try {
        $venvPython = Join-Path ".venv" "Scripts\python.exe"
        if (Test-Path $venvPython) {
            $pytestOutput = & $venvPython -m pytest --tb=short -v 2>&1 | Out-String
        } else {
            $pytestOutput = & python -m pytest --tb=short -v 2>&1 | Out-String
        }
        $pytestExit = $LASTEXITCODE

        # collected と passed の数を抽出（複数 variation 対応）
        if ($pytestOutput -match "collected (\d+) item") {
            $pytestCollected = [int]$Matches[1]
        }
        if ($pytestOutput -match "(?:^|\s)(\d+)\s+passed(?:\s|,|$)") {
            $pytestPassed = [int]$Matches[1]
        }

        # 失敗時は詳細ログを保存
        if ($pytestExit -ne 0 -or $pytestCollected -eq 0) {
            $logContent = $pytestOutput -split "`n" | Select-Object -Last 80 | Out-String
            [System.IO.File]::WriteAllText($pytestLogFile, $logContent, [System.Text.UTF8Encoding]::new($false))
            $script:detailLogs["pytest"] = $pytestLogFile
        }

        if ($pytestExit -eq 0 -and $pytestCollected -gt 0) {
            Test-CheckPass "pytest" "collected=$pytestCollected, passed=$pytestPassed"
        } elseif ($pytestCollected -eq 0) {
            Test-CheckFail "pytest" "no tests collected" -LogFile $pytestLogFile
        } else {
            Test-CheckFail "pytest" "tests failed (exit=$pytestExit)" -LogFile $pytestLogFile
        }
    }
    finally {
        Pop-Location
    }
}

# ===== vitest 実行 (Phase 4.1 以降) =====
$vitestCollected = 0
$vitestPassed = 0
$frontendPhases = @("4.1", "4.2", "4.3", "4.4a", "4.4b", "4.4c", "5.2", "6.1", "6.2")
if ($PhaseId -in $frontendPhases) {
    if (Test-Path "frontend\package.json") {
        Write-Host "  vitest 実行中..."
        Push-Location "frontend"
        try {
            $vitestOutput = & npm test -- --run 2>&1 | Out-String
            $vitestExit = $LASTEXITCODE

            if ($vitestOutput -match "Tests\s+(\d+) passed") {
                $vitestPassed = [int]$Matches[1]
                $vitestCollected = $vitestPassed
            }

            # 失敗時は詳細ログ保存
            if ($vitestExit -ne 0 -or $vitestPassed -eq 0) {
                $logContent = $vitestOutput -split "`n" | Select-Object -Last 80 | Out-String
                [System.IO.File]::WriteAllText($vitestLogFile, $logContent, [System.Text.UTF8Encoding]::new($false))
                $script:detailLogs["vitest"] = $vitestLogFile
            }

            if ($vitestExit -eq 0 -and $vitestPassed -gt 0) {
                Test-CheckPass "vitest" "passed=$vitestPassed"
            } elseif ($vitestPassed -eq 0) {
                Test-CheckFail "vitest" "no tests collected" -LogFile $vitestLogFile
            } else {
                Test-CheckFail "vitest" "tests failed (exit=$vitestExit)" -LogFile $vitestLogFile
            }
        }
        finally {
            Pop-Location
        }
    }
}

# ===== 結果集計 =====
$overall = if ($script:errors -eq 0) { "PASS" } else { "FAIL" }

$result = @{
    phase_id = $PhaseId
    checked_at = (Get-Date -Format "yyyy-MM-ddTHH:mm:sszzz")
    overall_result = $overall
    errors_count = $script:errors
    approval_required = $IsApprovalPhase
    git_head_at_check = (git rev-parse HEAD 2>$null)
    pytest_collected = $pytestCollected
    pytest_passed = $pytestPassed
    vitest_collected = $vitestCollected
    vitest_passed = $vitestPassed
    detail_logs = $script:detailLogs
    checks = $script:checks
}

# 承認ポイントで PASS の場合、approval_required フラグ付きで次フェーズブロック
if ($IsApprovalPhase -and $overall -eq "PASS") {
    $approvalFile = Join-Path $approvalsDir "phase_${PhaseId}.approved"
    if (Test-Path $approvalFile) {
        $result.approval_status = "approved"
        $result.next_phase_blocked = $false
    } else {
        $result.approval_status = "pending"
        $result.next_phase_blocked = $true
    }
}

# JSON 出力（BOM なし UTF-8）
$jsonOutput = $result | ConvertTo-Json -Depth 10
[System.IO.File]::WriteAllText($resultFile, $jsonOutput, [System.Text.UTF8Encoding]::new($false))

Write-Host ""
Write-Host "結果ファイル: $resultFile" -ForegroundColor Cyan
if ($script:detailLogs.Count -gt 0) {
    Write-Host "詳細ログ:" -ForegroundColor Cyan
    foreach ($key in $script:detailLogs.Keys) {
        Write-Host "  $key`: $($script:detailLogs[$key])" -ForegroundColor Cyan
    }
}

# ===== git commit で audit trail を残す =====
try {
    git add $resultFile 2>&1 | Out-Null
    foreach ($logFile in $script:detailLogs.Values) {
        if (Test-Path $logFile) {
            git add $logFile 2>&1 | Out-Null
        }
    }
    $commitMsg = "chore(check): phase $PhaseId result $overall ($($script:errors) errors)"
    git commit -m $commitMsg 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $commitHash = git rev-parse HEAD 2>$null
        Write-Host "結果を git にコミットしました: $commitHash" -ForegroundColor Gray
        Write-Host "次回チェック時の -LastCheckCommit 引数として上記ハッシュを渡すこと" -ForegroundColor Gray
    }
} catch {
    Write-Host "警告: git commit に失敗しました（手動で確認してください）" -ForegroundColor Yellow
}

# ===== コンソール集計 =====
Write-Host ""
if ($script:errors -eq 0) {
    if ($IsApprovalPhase) {
        if ($result.approval_status -eq "approved") {
            Write-Host "Phase ${PhaseId}: 完了条件を満たしています [PASS, APPROVED]" -ForegroundColor Green
        } else {
            Write-Host "Phase ${PhaseId}: 完了条件を満たしています [PASS, APPROVAL REQUIRED]" -ForegroundColor Yellow
            Write-Host "  次フェーズに進むには以下を実行してください:" -ForegroundColor Yellow
            Write-Host "    New-Item '$approvalsDir\phase_${PhaseId}.approved' -ItemType File" -ForegroundColor Yellow
            Write-Host "    git add '$approvalsDir\phase_${PhaseId}.approved'; git commit -m 'chore(approval): phase $PhaseId approved'" -ForegroundColor Yellow
        }
    } else {
        Write-Host "Phase ${PhaseId}: 完了条件を満たしています [PASS]" -ForegroundColor Green
    }
    exit 0
} else {
    Write-Host "Phase ${PhaseId}: $($script:errors) 件の完了条件未達 [FAIL]" -ForegroundColor Red
    exit 1
}
