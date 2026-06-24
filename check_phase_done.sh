#!/usr/bin/env bash
# check_phase_done.sh
# 指定サブステップの完了条件を機械的にチェックする。
#
# 使い方:
#   ./check_phase_done.sh <phase>
#   例: ./check_phase_done.sh 1.1

set -euo pipefail

PHASE="${1:-}"
if [[ -z "$PHASE" ]]; then
  echo "usage: $0 <phase>" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HANDOFF_FILE="docs/handoff_phase${PHASE//./_}.md"

errors=0

check_pass() { echo "  ✓ $*"; }
check_fail() { echo "  ✗ $*" >&2; errors=$((errors+1)); }

echo "Phase $PHASE 完了条件チェック"

# ===== 共通チェック =====

# 1. handoff ファイル存在
if [[ -f "$HANDOFF_FILE" ]]; then
  check_pass "handoff ファイル存在: $HANDOFF_FILE"
else
  check_fail "handoff ファイルがありません: $HANDOFF_FILE"
fi

# 2. git tag 存在
if git tag -l | grep -qx "phase${PHASE}-done"; then
  check_pass "git tag 存在: phase${PHASE}-done"
else
  check_fail "git tag がありません: phase${PHASE}-done"
fi

# 3. 未コミット変更がないこと
if [[ -z "$(git status --porcelain 2>/dev/null)" ]]; then
  check_pass "未コミットの変更なし"
else
  check_fail "未コミットの変更があります（git status で確認）"
fi

# ===== Phase 固有チェック =====

case "$PHASE" in
  "1.1")
    [[ -f "backend/app/main.py" ]]   && check_pass "backend/app/main.py 存在"   || check_fail "backend/app/main.py がありません"
    [[ -f "backend/app/config.py" ]] && check_pass "backend/app/config.py 存在" || check_fail "backend/app/config.py がありません"
    [[ -f "backend/pyproject.toml" ]] && check_pass "backend/pyproject.toml 存在" || check_fail "backend/pyproject.toml がありません"
    [[ -f ".gitignore" ]] && check_pass ".gitignore 存在" || check_fail ".gitignore がありません"
    ;;

  "1.2")
    [[ -d "backend/app/repositories" ]] && check_pass "repositories ディレクトリ存在" || check_fail "repositories ディレクトリがありません"
    [[ -d "backend/app/models" ]]       && check_pass "models ディレクトリ存在"       || check_fail "models ディレクトリがありません"
    [[ -f "backend/app/repositories/base.py" ]] && check_pass "base.py 存在" || check_fail "base.py がありません"
    ;;

  "1.3")
    [[ -f "backend/app/services/google_auth.py" ]] && check_pass "google_auth.py 存在" || check_fail "google_auth.py がありません"
    [[ -f "backend/tests/test_google_auth.py" ]]   && check_pass "test_google_auth.py 存在" || check_fail "test_google_auth.py がありません"
    # TDD: test commit が実装 commit より前にあるか
    if git log --oneline | grep -q "test(phase1.3)"; then
      check_pass "TDD: test commit が記録されている"
    else
      check_fail "TDD: 'test(phase1.3)' を含む commit が見つかりません"
    fi
    ;;

  "2.0")
    [[ -f "docs/forms_api_research.md" ]] && check_pass "forms_api_research.md 存在" || check_fail "forms_api_research.md がありません"
    ;;

  "2.1")
    [[ -f "backend/tests/test_project_api.py" ]] && check_pass "test_project_api.py 存在" || check_fail "test_project_api.py がありません"
    git log --oneline | grep -q "test(phase2.1)" && check_pass "TDD: test commit 記録あり" || check_fail "TDD: test commit が見つかりません"
    ;;

  "2.2")
    [[ -f "backend/app/services/google_forms.py" ]] && check_pass "google_forms.py 存在" || check_fail "google_forms.py がありません"
    [[ -f "backend/tests/test_google_forms_service.py" ]] && check_pass "test_google_forms_service.py 存在" || check_fail "test_google_forms_service.py がありません"
    git log --oneline | grep -q "test(phase2.2)" && check_pass "TDD: test commit 記録あり" || check_fail "TDD: test commit が見つかりません"
    ;;

  "2.3")
    [[ -f "backend/app/services/polling.py" ]] && check_pass "polling.py 存在" || check_fail "polling.py がありません"
    [[ -f "backend/tests/test_polling_service.py" ]] && check_pass "test_polling_service.py 存在" || check_fail "test_polling_service.py がありません"
    git log --oneline | grep -q "test(phase2.3)" && check_pass "TDD: test commit 記録あり" || check_fail "TDD: test commit が見つかりません"
    ;;

  "3.1")
    [[ -f "backend/tests/test_rules_api.py" ]] && check_pass "test_rules_api.py 存在" || check_fail "test_rules_api.py がありません"
    git log --oneline | grep -q "test(phase3.1)" && check_pass "TDD: test commit 記録あり" || check_fail "TDD: test commit が見つかりません"
    ;;

  "3.2")
    [[ -f "backend/app/services/scheduler.py" ]] && check_pass "scheduler.py 存在" || check_fail "scheduler.py がありません"
    [[ -f "backend/tests/test_scheduler_hard.py" ]] && check_pass "test_scheduler_hard.py 存在" || check_fail "test_scheduler_hard.py がありません"
    git log --oneline | grep -q "test(phase3.2)" && check_pass "TDD: test commit 記録あり" || check_fail "TDD: test commit が見つかりません"
    ;;

  "3.3")
    [[ -f "backend/tests/test_scheduler_soft.py" ]] && check_pass "test_scheduler_soft.py 存在" || check_fail "test_scheduler_soft.py がありません"
    [[ -f "backend/tests/test_schedule_api.py" ]] && check_pass "test_schedule_api.py 存在" || check_fail "test_schedule_api.py がありません"
    git log --oneline | grep -q "test(phase3.3)" && check_pass "TDD: test commit 記録あり" || check_fail "TDD: test commit が見つかりません"
    ;;

  "3.4")
    [[ -f "backend/tests/test_drafts_api.py" ]] && check_pass "test_drafts_api.py 存在" || check_fail "test_drafts_api.py がありません"
    git log --oneline | grep -q "test(phase3.4)" && check_pass "TDD: test commit 記録あり" || check_fail "TDD: test commit が見つかりません"
    ;;

  "4.1")
    [[ -f "frontend/package.json" ]]   && check_pass "frontend/package.json 存在"   || check_fail "frontend/package.json がありません"
    [[ -f "frontend/vite.config.ts" ]] && check_pass "frontend/vite.config.ts 存在" || check_fail "frontend/vite.config.ts がありません"
    [[ -d "frontend/src/api" ]]        && check_pass "frontend/src/api 存在"        || check_fail "frontend/src/api がありません"
    ;;

  "4.2"|"4.3"|"4.4")
    git log --oneline | grep -q "test(phase${PHASE})" && check_pass "TDD: test commit 記録あり" || check_fail "TDD: test commit が見つかりません"
    ;;

  "5.1")
    [[ -f "backend/app/services/pdf_generator.py" ]] && check_pass "pdf_generator.py 存在" || check_fail "pdf_generator.py がありません"
    [[ -f "backend/tests/test_pdf_generator.py" ]]   && check_pass "test_pdf_generator.py 存在" || check_fail "test_pdf_generator.py がありません"
    [[ -f "docs/pdf_decisions.md" ]] && check_pass "pdf_decisions.md 存在" || check_fail "pdf_decisions.md がありません"
    git log --oneline | grep -q "test(phase5.1)" && check_pass "TDD: test commit 記録あり" || check_fail "TDD: test commit が見つかりません"
    ;;

  "5.2")
    [[ -f "backend/tests/test_pdf_api.py" ]] && check_pass "test_pdf_api.py 存在" || check_fail "test_pdf_api.py がありません"
    git log --oneline | grep -q "test(phase5.2)" && check_pass "TDD: test commit 記録あり" || check_fail "TDD: test commit が見つかりません"
    ;;

  "6.1")
    [[ -f "docs/e2e_test.md" ]] && check_pass "e2e_test.md 存在" || check_fail "e2e_test.md がありません"
    [[ -f "backend/app/logging_config.py" ]] && check_pass "logging_config.py 存在" || check_fail "logging_config.py がありません"
    ;;

  "6.2")
    [[ -f "README.md" ]]          && check_pass "README.md 存在"            || check_fail "README.md がありません"
    [[ -f "docs/limitations.md" ]] && check_pass "limitations.md 存在"       || check_fail "limitations.md がありません"
    if git tag -l | grep -qx "v0.1.0-prototype"; then
      check_pass "リリースタグ v0.1.0-prototype 存在"
    else
      check_fail "リリースタグ v0.1.0-prototype がありません"
    fi
    ;;

  *)
    echo "  (Phase $PHASE 固有チェックは定義されていません。共通チェックのみ実施)"
    ;;
esac

# ===== pytest / vitest 実行 =====
# サブステップが進むほどテストは増えるが、すべてのテストが通る状態を保証する

if [[ -f "backend/pyproject.toml" ]]; then
  echo "  pytest 実行中..."
  if (cd backend && python -m pytest --tb=short -q 2>&1); then
    check_pass "pytest 全パス"
  else
    check_fail "pytest が失敗しました"
  fi
fi

# Phase 4.1 以降は vitest もチェック
case "$PHASE" in
  "4.1"|"4.2"|"4.3"|"4.4"|"5.2"|"6.1"|"6.2")
    if [[ -f "frontend/package.json" ]]; then
      echo "  vitest 実行中..."
      if (cd frontend && npm test -- --run 2>&1); then
        check_pass "vitest 全パス"
      else
        check_fail "vitest が失敗しました"
      fi
    fi
    ;;
esac

# ===== 集計 =====
echo
if [[ $errors -eq 0 ]]; then
  echo "Phase $PHASE: 完了条件を満たしています"
  exit 0
else
  echo "Phase $PHASE: $errors 件の完了条件未達"
  exit 1
fi
