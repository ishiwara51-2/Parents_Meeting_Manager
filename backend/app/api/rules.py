"""ルール管理 API ルータ（Phase 3.1）。

requirements.md §6 のエンドポイント定義に対応する。

API 一覧:

- ``GET  /api/global-rules``                グローバルルール取得（未設定時は既定値で初期化）
- ``PUT  /api/global-rules``                グローバルルール更新
- ``GET  /api/projects/{project_id}/rules`` プロジェクトルール取得
- ``PUT  /api/projects/{project_id}/rules`` プロジェクトルール更新

設計上の決定（Phase 3.1）:

- グローバルルールは ``<config_dir>/global_rules.json`` に永続化
- プロジェクトルールは ``<project_dir>/rules.json`` に永続化
- バリデーション（重み 0〜10、有効な制約タイプ）は Pydantic モデル側で担保
  → 不正値は FastAPI が 422 を自動返答
- プロジェクト存在確認は ``ProjectRepository.get()`` で行い、非存在時は 404 を返す
- ルール操作の抽象化は ``RuleRepository`` （DI で注入）
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_project_repository, get_rule_repository
from app.models.rules import Rules
from app.repositories.base import ProjectRepository, RuleRepository

router = APIRouter(tags=["rules"])


# ---------------------------------------------------------------------------
# グローバルルール
# ---------------------------------------------------------------------------


@router.get("/api/global-rules", response_model=Rules)
def get_global_rules(
    rule_repo: RuleRepository = Depends(get_rule_repository),
) -> Rules:
    """グローバルルールを取得する。

    ``global_rules.json`` が存在しない場合（初回アクセス）は既定値で初期化してから返す。
    プロジェクト作成時のコピー元になるルール（requirements.md §4.5.1）。
    """
    return rule_repo.get_global_rules()


@router.put("/api/global-rules", response_model=Rules)
def put_global_rules(
    rules: Rules,
    rule_repo: RuleRepository = Depends(get_rule_repository),
) -> Rules:
    """グローバルルールを更新する。

    バリデーション（重み 0〜10、有効な制約タイプ）は ``Rules`` モデル（Pydantic）が行う。
    不正な値は FastAPI が 422 を自動返答する。
    """
    return rule_repo.set_global_rules(rules)


# ---------------------------------------------------------------------------
# プロジェクトルール
# ---------------------------------------------------------------------------


@router.get("/api/projects/{project_id}/rules", response_model=Rules)
def get_project_rules(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repository),
    rule_repo: RuleRepository = Depends(get_rule_repository),
) -> Rules:
    """指定プロジェクトのルールを取得する。

    プロジェクトが存在しない場合は 404。
    ``rules.json`` が存在しない場合も 404（プロジェクト作成時に必ず生成されるため
    通常は発生しないが、ファイルが手動削除された等の異常系の保険として 404 を返す）。
    """
    if project_repo.get(project_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"project '{project_id}' not found",
        )
    try:
        return rule_repo.get_project_rules(project_id)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"rules for project '{project_id}' not found",
        )


@router.put("/api/projects/{project_id}/rules", response_model=Rules)
def put_project_rules(
    project_id: str,
    rules: Rules,
    project_repo: ProjectRepository = Depends(get_project_repository),
    rule_repo: RuleRepository = Depends(get_rule_repository),
) -> Rules:
    """指定プロジェクトのルールを更新する。

    プロジェクトが存在しない場合は 404。
    バリデーション（重み範囲・制約タイプ）は Pydantic が 422 で自動処理する。
    グローバルルールには影響しない（独立した永続化先）。
    """
    if project_repo.get(project_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"project '{project_id}' not found",
        )
    try:
        return rule_repo.set_project_rules(project_id, rules)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"project '{project_id}' not found",
        )


__all__ = ["router"]
