#!/usr/bin/env bash
# orchestrator.sh
# 保護者面談調整ツール プロトタイプ実装の自動進行スクリプト
#
# 使い方:
#   ./orchestrator.sh                    # 最初から実行
#   ./orchestrator.sh --resume phase3.2  # 指定サブステップから再開
#   ./orchestrator.sh --only phase2.1    # 単一サブステップのみ実行
#   ./orchestrator.sh --dry-run          # 実行計画だけ表示
#   ./orchestrator.sh --list             # サブステップ一覧表示

set -euo pipefail

# ===================== 設定 =====================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROMPTS_FILE="${SCRIPT_DIR}/implementation_prompts_subdivided.md"
REQUIREMENTS_FILE="${SCRIPT_DIR}/requirements.md"
LOG_DIR="${SCRIPT_DIR}/logs"
STATE_FILE="${SCRIPT_DIR}/.orchestrator_state"
CHECK_SCRIPT="${SCRIPT_DIR}/check_phase_done.sh"

# サブステップ一覧（順序通り）
PHASES=(
  "1.1"   # プロジェクト初期化と FastAPI 骨格
  "1.2"   # Repository 抽象化の骨格
  "1.3"   # Google OAuth2 認証フロー
  "2.0"   # Forms API 仕様調査
  "2.1"   # プロジェクト管理 API
  "2.2"   # Google Form 作成
  "2.3"   # 回答ポーリングと変換
  "3.1"   # ルール管理 API
  "3.2"   # スケジューラ（ハード制約のみ）
  "3.3"   # スケジューラ（ソフト制約追加）と API
  "3.4"   # ドラフト保存・ロック管理
  "4.1"   # フロントエンド初期化とAPIクライアント
  "4.2"   # ホーム画面とプロジェクト一覧
  "4.3"   # プロジェクト画面とForm連携UI
  "4.4"   # 日程案表示画面（ドラッグ&ドロップ）
  "5.1"   # PDF生成サービス
  "5.2"   # PDF出力API・UI
  "6.1"   # E2E 動作確認とログ整備
  "6.2"   # README とリリース準備
)

# ユーザー承認が必要なサブステップ（自動進行を停止）
APPROVAL_PHASES=(
  "2.0"   # Forms API 調査結果の確認
  "3.3"   # ソフト制約の挙動確認（解の品質を実データで確認したい）
  "4.4"   # DnD画面の完成確認
  "5.1"   # PDF レイアウトの確認
)

# ===================== ユーティリティ =====================
COLOR_RESET='\033[0m'
COLOR_INFO='\033[1;34m'
COLOR_OK='\033[1;32m'
COLOR_WARN='\033[1;33m'
COLOR_ERR='\033[1;31m'

log_info()  { echo -e "${COLOR_INFO}[INFO]${COLOR_RESET}  $*"; }
log_ok()    { echo -e "${COLOR_OK}[OK]${COLOR_RESET}    $*"; }
log_warn()  { echo -e "${COLOR_WARN}[WARN]${COLOR_RESET}  $*"; }
log_err()   { echo -e "${COLOR_ERR}[ERROR]${COLOR_RESET} $*" >&2; }

needs_approval() {
  local phase="$1"
  for p in "${APPROVAL_PHASES[@]}"; do
    [[ "$p" == "$phase" ]] && return 0
  done
  return 1
}

# ===================== 前提チェック =====================
preflight_check() {
  log_info "前提チェック中..."

  if ! command -v claude >/dev/null 2>&1; then
    log_err "claude コマンドが見つかりません。Claude Code をインストールしてください。"
    exit 1
  fi

  if ! command -v git >/dev/null 2>&1; then
    log_err "git コマンドが見つかりません。"
    exit 1
  fi

  if [[ ! -f "$PROMPTS_FILE" ]]; then
    log_err "プロンプトファイルが見つかりません: $PROMPTS_FILE"
    exit 1
  fi

  if [[ ! -f "$REQUIREMENTS_FILE" ]]; then
    log_err "要件定義ファイルが見つかりません: $REQUIREMENTS_FILE"
    exit 1
  fi

  if [[ ! -x "$CHECK_SCRIPT" ]]; then
    log_err "完了チェックスクリプトが見つからないか実行権限がありません: $CHECK_SCRIPT"
    exit 1
  fi

  # gitリポジトリが初期化されているか
  if ! git rev-parse --git-dir >/dev/null 2>&1; then
    log_warn "gitリポジトリが初期化されていません。初期化します。"
    git init
    git add "$REQUIREMENTS_FILE" "$PROMPTS_FILE" 2>/dev/null || true
    git commit -m "chore: initial commit with requirements and prompts" --allow-empty
  fi

  mkdir -p "$LOG_DIR"

  log_ok "前提チェック完了"
}

# ===================== サブステップ実行 =====================
run_phase() {
  local phase="$1"
  local log_file="${LOG_DIR}/phase_${phase}_$(date +%Y%m%d_%H%M%S).log"
  local prompt

  log_info "============================================================"
  log_info "Phase $phase 開始"
  log_info "============================================================"

  # 既に完了済みかチェック
  if git tag -l | grep -qx "phase${phase}-done"; then
    log_warn "Phase $phase は既に完了タグが存在します。スキップしますか？"
    read -r -p "(y=スキップ / n=再実行 / q=中断): " choice
    case "$choice" in
      y|Y) log_info "Phase $phase をスキップ"; return 0 ;;
      q|Q) log_info "ユーザーにより中断"; exit 0 ;;
      *)   log_info "Phase $phase を再実行" ;;
    esac
  fi

  # プロンプト構築
  prompt=$(cat <<EOF
implementation_prompts_subdivided.md の Phase ${phase} を実装してください。

開始前に以下を実施:
1. requirements.md を通読
2. 当該フェーズの先行サブステップの docs/handoff_*.md を通読
3. 「Phase ${phase} に着手します」と宣言してから実装開始

テスト駆動の指示があるサブステップでは、
テストファースト → RED確認 → test commit → 実装 → GREEN確認 → implementation commit
の順序を厳守してください。

完了時:
- 完了条件チェックリストを報告
- docs/handoff_phase${phase//./_}.md を作成
- git tag phase${phase}-done を打つ
EOF
)

  log_info "Claude Code を起動します（headlessモード）..."
  log_info "ログ出力先: $log_file"

  # Claude Code を headless モードで実行
  # --dangerously-skip-permissions は自動進行のため必要だが、内容理解の上で使うこと
  if ! claude -p "$prompt" \
      --output-format stream-json \
      --verbose \
      --dangerously-skip-permissions \
      2>&1 | tee "$log_file"; then
    log_err "Phase $phase 実行中にエラー"
    return 1
  fi

  log_info "Phase $phase 実行終了。完了条件チェック..."

  # 完了条件チェック
  if ! "$CHECK_SCRIPT" "$phase"; then
    log_err "Phase $phase の完了条件を満たしていません"
    log_err "ログを確認してください: $log_file"
    return 1
  fi

  # 承認ポイントの場合、ユーザー確認
  if needs_approval "$phase"; then
    log_warn "Phase $phase は承認ポイントです"
    show_approval_info "$phase"
    read -r -p "次のサブステップに進んでよいですか？ (y/n/q): " approval
    case "$approval" in
      y|Y) log_ok "承認されました" ;;
      q|Q) log_info "ユーザーにより中断"; exit 0 ;;
      *)   log_err "承認されませんでした。中断します。"; exit 1 ;;
    esac
  fi

  log_ok "Phase $phase 完了"
  echo "$phase" > "$STATE_FILE"
}

show_approval_info() {
  local phase="$1"
  case "$phase" in
    "2.0")
      log_warn "=== Phase 2.0 承認確認事項 ==="
      log_warn "docs/forms_api_research.md を確認してください"
      log_warn "特にチェックボックスグリッドの対応状況と、代替案の妥当性を確認"
      [[ -f "docs/forms_api_research.md" ]] && cat docs/forms_api_research.md | head -50
      ;;
    "3.3")
      log_warn "=== Phase 3.3 承認確認事項 ==="
      log_warn "スケジューラのソフト制約挙動を確認してください"
      log_warn "テスト出力やサンプル実行結果を確認"
      ;;
    "4.4")
      log_warn "=== Phase 4.4 承認確認事項 ==="
      log_warn "DnD画面を実機で操作確認してください"
      log_warn "起動: cd backend && uvicorn app.main:app --reload"
      log_warn "      cd frontend && npm run dev"
      ;;
    "5.1")
      log_warn "=== Phase 5.1 承認確認事項 ==="
      log_warn "生成されたサンプルPDFを確認してください"
      log_warn "テスト出力ディレクトリに sample.pdf が生成されているはず"
      ;;
  esac
}

# ===================== 状態管理 =====================
get_last_completed_phase() {
  [[ -f "$STATE_FILE" ]] && cat "$STATE_FILE" || echo ""
}

find_phase_index() {
  local target="$1"
  for i in "${!PHASES[@]}"; do
    [[ "${PHASES[$i]}" == "$target" ]] && echo "$i" && return 0
  done
  echo "-1"
}

# ===================== コマンドハンドリング =====================
cmd_list() {
  log_info "サブステップ一覧:"
  for phase in "${PHASES[@]}"; do
    local marker=""
    if git tag -l 2>/dev/null | grep -qx "phase${phase}-done"; then
      marker="${COLOR_OK}✓${COLOR_RESET}"
    fi
    local approval=""
    if needs_approval "$phase"; then
      approval=" ${COLOR_WARN}[要承認]${COLOR_RESET}"
    fi
    echo -e "  Phase ${phase}${approval} ${marker}"
  done
}

cmd_dry_run() {
  local start_idx="${1:-0}"
  log_info "実行計画（dry-run）:"
  for ((i=start_idx; i<${#PHASES[@]}; i++)); do
    local phase="${PHASES[$i]}"
    local approval=""
    needs_approval "$phase" && approval=" [要承認]"
    echo "  $((i+1)). Phase ${phase}${approval}"
  done
}

cmd_run() {
  local start_idx="${1:-0}"
  local only_idx="${2:--1}"

  preflight_check

  if [[ "$only_idx" -ge 0 ]]; then
    run_phase "${PHASES[$only_idx]}"
    return
  fi

  for ((i=start_idx; i<${#PHASES[@]}; i++)); do
    if ! run_phase "${PHASES[$i]}"; then
      log_err "Phase ${PHASES[$i]} で失敗。中断します。"
      log_info "再開コマンド: $0 --resume ${PHASES[$i]}"
      exit 1
    fi
  done

  log_ok "============================================================"
  log_ok "全サブステップ完了"
  log_ok "============================================================"
}

usage() {
  cat <<EOF
使い方:
  $0                       全サブステップを最初から実行
  $0 --resume <phase>      指定サブステップから再開（例: --resume 3.2）
  $0 --only <phase>        単一サブステップのみ実行
  $0 --dry-run [--resume <phase>]  実行計画を表示
  $0 --list                サブステップ一覧と完了状態を表示
  $0 --help                このメッセージを表示
EOF
}

# ===================== エントリポイント =====================
main() {
  local mode="run"
  local target_phase=""

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --resume) mode="resume"; target_phase="$2"; shift 2 ;;
      --only)   mode="only";   target_phase="$2"; shift 2 ;;
      --dry-run) mode="dry-run"; shift ;;
      --list)   mode="list"; shift ;;
      --help|-h) usage; exit 0 ;;
      *) log_err "未知のオプション: $1"; usage; exit 1 ;;
    esac
  done

  case "$mode" in
    list)
      cmd_list
      ;;
    dry-run)
      local idx=0
      [[ -n "$target_phase" ]] && idx=$(find_phase_index "$target_phase")
      [[ "$idx" -lt 0 ]] && { log_err "不明なサブステップ: $target_phase"; exit 1; }
      cmd_dry_run "$idx"
      ;;
    resume)
      local idx=$(find_phase_index "$target_phase")
      [[ "$idx" -lt 0 ]] && { log_err "不明なサブステップ: $target_phase"; exit 1; }
      cmd_run "$idx"
      ;;
    only)
      local idx=$(find_phase_index "$target_phase")
      [[ "$idx" -lt 0 ]] && { log_err "不明なサブステップ: $target_phase"; exit 1; }
      cmd_run 0 "$idx"
      ;;
    run)
      cmd_run 0
      ;;
  esac
}

main "$@"
