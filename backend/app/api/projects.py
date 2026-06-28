"""プロジェクト管理 API ルータ。

requirements.md §6 のエンドポイント定義に対応する。Phase 2.1 で
``POST /api/projects`` 〜 ``DELETE /api/projects/{id}`` の CRUD を実装する。

API 一覧:

- ``POST   /api/projects``       プロジェクト作成（``project_id`` 自動採番）
- ``GET    /api/projects``       プロジェクト一覧（作成日時降順）
- ``GET    /api/projects/{id}``  プロジェクト詳細
- ``PUT    /api/projects/{id}``  プロジェクトメタ全置換
- ``DELETE /api/projects/{id}``  プロジェクト削除（ディレクトリごと）

設計上の決定（Phase 2.1）:

- ``project_id`` は UUID4 を採番する。理由：
  ディレクトリ名として使うため衝突回避が容易で、複数同時作成時もロック不要
- ``created_at`` はサーバ生成。タイムゾーンは ``datetime.now(timezone.utc).astimezone()`` で
  ローカルタイムゾーン付き ISO 8601 に正規化
- ``status`` は新規作成時 ``in_progress`` 既定
- 更新 (PUT) は全置換。``project_id`` と ``created_at`` はサーバ管理で不変。
  リクエストボディに含めても無視する
- 422（バリデーション）は FastAPI / Pydantic v2 が自動応答
- 404 は本ハンドラで明示的に投げる
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.dependencies import get_project_repository
from app.models.project import Project, ProjectStatus, TimeSlot
from app.repositories.base import ProjectRepository


router = APIRouter(prefix="/api/projects", tags=["projects"])


# ---------------------------------------------------------------------------
# リクエストモデル
# ---------------------------------------------------------------------------


class ProjectCreateRequest(BaseModel):
    """プロジェクト作成リクエスト。

    ``project_id`` と ``created_at`` はサーバ採番のため受け付けない。
    ``status`` は省略時 ``in_progress``。
    """

    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(..., min_length=1, description="UI 表示用名")
    slot_minutes: int = Field(..., gt=0, description="1コマの長さ（分）")
    candidate_dates: list[date] = Field(default_factory=list)
    candidate_time_slots: list[TimeSlot] = Field(default_factory=list)
    student_numbers: list[int] = Field(default_factory=list)
    status: ProjectStatus = Field(default="in_progress")


class ProjectUpdateRequest(BaseModel):
    """プロジェクト全置換更新リクエスト。

    ``project_id`` と ``created_at`` は不変のため受け付けない（含まれても無視）。
    """

    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(..., min_length=1)
    slot_minutes: int = Field(..., gt=0)
    candidate_dates: list[date] = Field(default_factory=list)
    candidate_time_slots: list[TimeSlot] = Field(default_factory=list)
    student_numbers: list[int] = Field(default_factory=list)
    status: ProjectStatus


# ---------------------------------------------------------------------------
# ハンドラ
# ---------------------------------------------------------------------------


def _generate_project_id() -> str:
    """新規 ``project_id`` を採番する。

    Phase 2.1 決定事項：UUID4 16進無印形式（例 ``ab12cd34ef5...``）。
    ディレクトリ名安全性のためハイフンも除去している。
    """
    return uuid.uuid4().hex


def _now_local_aware() -> datetime:
    """ローカルタイムゾーン付きの現在時刻を返す。

    ``Project.created_at`` のスキーマ（TZ 付き ISO 8601、requirements.md §3.2）を満たす。
    """
    return datetime.now(timezone.utc).astimezone()


@router.post(
    "",
    response_model=Project,
    status_code=status.HTTP_201_CREATED,
)
def create_project(
    payload: ProjectCreateRequest,
    repo: ProjectRepository = Depends(get_project_repository),
) -> Project:
    """新規プロジェクトを作成する。

    ``project_id`` と ``created_at`` はサーバが採番・付与する。
    プロジェクトディレクトリ・サブディレクトリ（responses/, drafts/, output/）と
    ``rules.json`` の初期化は ``FileProjectRepository.create()`` の責務。
    """
    project = Project(
        project_id=_generate_project_id(),
        display_name=payload.display_name,
        created_at=_now_local_aware(),
        status=payload.status,
        slot_minutes=payload.slot_minutes,
        candidate_dates=payload.candidate_dates,
        candidate_time_slots=payload.candidate_time_slots,
        student_numbers=payload.student_numbers,
    )
    return repo.create(project)


@router.get("", response_model=list[Project])
def list_projects(
    repo: ProjectRepository = Depends(get_project_repository),
) -> list[Project]:
    """全プロジェクトを ``created_at`` 降順で返す。"""
    return repo.list_all()


@router.get("/{project_id}", response_model=Project)
def get_project(
    project_id: str,
    repo: ProjectRepository = Depends(get_project_repository),
) -> Project:
    """指定 ID のプロジェクト詳細を返す。存在しなければ 404。"""
    project = repo.get(project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"project '{project_id}' not found",
        )
    return project


@router.put("/{project_id}", response_model=Project)
def update_project(
    project_id: str,
    payload: ProjectUpdateRequest,
    repo: ProjectRepository = Depends(get_project_repository),
) -> Project:
    """プロジェクトメタを全置換更新する。

    ``project_id`` / ``created_at`` は不変（URL 上の ID とディスク既存値を使う）。
    対象が存在しなければ 404。
    """
    existing = repo.get(project_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"project '{project_id}' not found",
        )

    updated = Project(
        project_id=existing.project_id,
        display_name=payload.display_name,
        created_at=existing.created_at,  # 不変
        status=payload.status,
        slot_minutes=payload.slot_minutes,
        candidate_dates=payload.candidate_dates,
        candidate_time_slots=payload.candidate_time_slots,
        student_numbers=payload.student_numbers,
    )
    return repo.update(updated)


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_project(
    project_id: str,
    repo: ProjectRepository = Depends(get_project_repository),
) -> Response:
    """プロジェクトを削除する。ディレクトリ配下も再帰削除する。

    存在しなければ 404。
    """
    if repo.get(project_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"project '{project_id}' not found",
        )
    repo.delete(project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
