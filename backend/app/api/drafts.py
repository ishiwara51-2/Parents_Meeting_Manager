"""ドラフト保存・ロック管理 API。

requirements.md §4.7-4.9 / §6 に従い、以下のエンドポイントを提供する。

- ``POST /api/projects/{id}/drafts``    — ドラフト保存（ロック）
- ``POST /api/projects/{id}/drafts/unlock`` — ロック解除
- ``GET  /api/projects/{id}/drafts/latest`` — 最新ドラフト取得

ステータス遷移（requirements.md §3.2 / §4.7-4.9 の状態機械）:

    in_progress --[POST /drafts]--> draft_saved
    draft_saved --[POST /drafts/unlock]--> in_progress

不正遷移（例: draft_saved 状態での再保存）は 409 を返す。
``finalized`` への遷移は Phase 5.x（PDF 出力）で行う。

ドラフト変換責務:
    ``POST /drafts`` リクエストボディ（``DraftSaveRequest``）は
    ``SchedulingResult`` と同じフィールド構造（``assignments``,
    ``unassigned_students``, ``violated_constraints``）を持ち、
    API ハンドラ層で ``Draft`` モデルに変換する。
    Phase 3.2 引き継ぎの型不整合（``violated_constraints: list[str]`` vs
    ``list[dict]``）は Draft モデルを ``list[str]`` に統一することで解消した。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.dependencies import get_draft_repository, get_project_repository
from app.models.draft import Assignment, Draft
from app.models.project import Project, ProjectStatus
from app.repositories.base import DraftRepository, ProjectRepository
from app.repositories.file_repository import FileProjectRepository

router = APIRouter(prefix="/api/projects", tags=["drafts"])


# ---------------------------------------------------------------------------
# リクエスト / レスポンス モデル
# ---------------------------------------------------------------------------


class DraftSaveRequest(BaseModel):
    """ドラフト保存リクエストボディ。

    ``SchedulingResult`` と同一構造を採用し、スケジューラ API レスポンスを
    そのままフロントエンドからドラフト保存 API に転送できるようにする。
    """

    model_config = ConfigDict(extra="forbid")

    assignments: list[Assignment] = Field(default_factory=list)
    unassigned_students: list[int] = Field(default_factory=list)
    violated_constraints: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# ヘルパ
# ---------------------------------------------------------------------------


def _now_utc() -> datetime:
    """UTC の現在時刻（TZ 付き）を返す。"""
    return datetime.now(timezone.utc)


def _get_project_or_404(
    project_id: str,
    project_repo: ProjectRepository,
) -> Project:
    """プロジェクトを取得し、存在しない場合は 404 を返す。"""
    project = project_repo.get(project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"プロジェクト '{project_id}' が見つかりません",
        )
    return project


def _update_project_status(
    project: Project,
    new_status: ProjectStatus,
    project_repo: ProjectRepository,
) -> Project:
    """プロジェクトの status を更新する。"""
    updated = project.model_copy(update={"status": new_status})
    project_repo.update(updated)
    return updated


# ---------------------------------------------------------------------------
# エンドポイント
# ---------------------------------------------------------------------------


@router.post(
    "/{project_id}/drafts",
    response_model=Draft,
    status_code=status.HTTP_201_CREATED,
    summary="ドラフト保存（ロック）",
    description=(
        "スケジューリング結果をドラフトとして保存しロックする。"
        "プロジェクトの status を `draft_saved` に遷移させる。"
        "status が `draft_saved` の状態（未解除）では 409 を返す。"
    ),
)
def save_draft(
    project_id: str,
    body: DraftSaveRequest,
    project_repo: ProjectRepository = Depends(get_project_repository),
    draft_repo: DraftRepository = Depends(get_draft_repository),
) -> Draft:
    """ドラフトを保存してロックする。

    status 遷移: ``in_progress`` → ``draft_saved``

    - プロジェクト不在 → 404
    - status が ``draft_saved`` → 409（アンロック後に再保存してください）
    """
    project = _get_project_or_404(project_id, project_repo)

    # 不正遷移チェック: draft_saved ならアンロックが必要
    if project.status == "draft_saved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"プロジェクト '{project_id}' は既にドラフトが保存されています。"
                "再編集する場合は先に /drafts/unlock を呼んでください。"
            ),
        )

    # Draft オブジェクトを構築（保存時刻はサーバ側で付与）
    draft = Draft(
        project_id=project_id,
        saved_at=_now_utc(),
        locked=True,
        assignments=body.assignments,
        unassigned_students=body.unassigned_students,
        violated_constraints=body.violated_constraints,
    )

    draft_repo.save_draft(project_id, draft)

    # プロジェクト status を draft_saved に遷移
    _update_project_status(project, "draft_saved", project_repo)

    return draft


@router.post(
    "/{project_id}/drafts/unlock",
    response_model=Draft,
    status_code=status.HTTP_200_OK,
    summary="ドラフトのロック解除",
    description=(
        "最新ドラフトのロックを解除し、再編集可能状態に戻す。"
        "プロジェクトの status を `in_progress` に遷移させる。"
    ),
)
def unlock_draft(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repository),
    draft_repo: DraftRepository = Depends(get_draft_repository),
) -> Draft:
    """最新ドラフトをアンロックする。

    status 遷移: ``draft_saved`` → ``in_progress``

    - プロジェクト不在 → 404
    - ドラフト不在 → 404
    """
    project = _get_project_or_404(project_id, project_repo)

    # ドラフトをアンロック（存在しない場合は FileNotFoundError → 404）
    try:
        unlocked = draft_repo.unlock_latest(project_id)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"プロジェクト '{project_id}' のドラフトが見つかりません",
        )

    # プロジェクト status を in_progress に遷移
    _update_project_status(project, "in_progress", project_repo)

    return unlocked


@router.get(
    "/{project_id}/drafts/latest",
    response_model=Draft,
    status_code=status.HTTP_200_OK,
    summary="最新ドラフト取得",
    description=(
        "最新のドラフトを取得する。"
        "PDF 出力（Phase 5.x）やフロントエンドの再編集開始時に使用する。"
    ),
)
def get_latest_draft(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repository),
    draft_repo: DraftRepository = Depends(get_draft_repository),
) -> Draft:
    """最新ドラフトを取得する。

    - プロジェクト不在 → 404
    - ドラフト不在 → 404
    """
    _get_project_or_404(project_id, project_repo)

    draft = draft_repo.get_latest(project_id)
    if draft is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"プロジェクト '{project_id}' のドラフトが見つかりません",
        )

    return draft
