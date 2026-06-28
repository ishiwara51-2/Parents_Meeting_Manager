"""Form 回答 API ルータ（Phase 2.3）。

requirements.md §6 のうち以下を担当する：

- ``POST /api/projects/{id}/responses/sync`` 回答ポーリング実行（同期処理）
- ``GET  /api/projects/{id}/responses``      受領済み回答一覧（最新版のみ）
- ``GET  /api/projects/{id}/responses/status`` 受領状況サマリ（受領済み/未受領 SN）

エラーマッピング:
    - 404: プロジェクト未存在 or ``form.json`` 未作成（``FormNotConfiguredError``）
    - 401: OAuth トークン未保存・リフレッシュ失敗（``GoogleAuthRequiredError``）
    - 503: 429/503 リトライ全消費（``PollingRetryExhaustedError``）
    - 200: 正常応答
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.dependencies import get_project_repository, get_response_repository
from app.models.response import Response as ResponseModel
from app.repositories.base import ProjectRepository, ResponseRepository
from app.repositories.file_repository import (
    FileProjectRepository,
    FileResponseRepository,
)
from app.services.google_forms import GoogleAuthRequiredError
from app.services.polling import (
    FormNotConfiguredError,
    PollingRetryExhaustedError,
    sync_responses,
)


router = APIRouter(prefix="/api/projects", tags=["responses"])


# ---------------------------------------------------------------------------
# レスポンスモデル
# ---------------------------------------------------------------------------


class SyncResponsesResult(BaseModel):
    """POST /responses/sync の結果。

    ``new_count``: 今回新規に保存した回答数。
    ``skipped_count``: 不正回答（出席番号が整数でない等）でスキップした数。
    ``errors``: スキップ・保存失敗の理由メッセージ一覧（プロトタイプ運用ではログ補助）。
    """

    model_config = ConfigDict(extra="forbid")

    new_count: int = Field(..., ge=0)
    skipped_count: int = Field(..., ge=0)
    errors: list[str] = Field(default_factory=list)


class ResponsesStatusResult(BaseModel):
    """GET /responses/status の結果。

    ``received`` / ``pending`` ともに出席番号昇順でソート済み。
    """

    model_config = ConfigDict(extra="forbid")

    project_id: str
    received: list[int]
    pending: list[int]


# ---------------------------------------------------------------------------
# ハンドラ
# ---------------------------------------------------------------------------


def _ensure_project_exists(
    project_id: str, project_repo: ProjectRepository
) -> None:
    """対象プロジェクトの存在をガードする（404 を共通化）。"""
    if project_repo.get(project_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"project '{project_id}' not found",
        )


@router.post(
    "/{project_id}/responses/sync",
    response_model=SyncResponsesResult,
    status_code=status.HTTP_200_OK,
)
def sync_project_responses(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repository),
) -> SyncResponsesResult:
    """指定プロジェクトの Form 回答をポーリング取得して保存する。

    レスポンスは ``new_count`` / ``skipped_count`` / ``errors`` のサマリ。
    """
    _ensure_project_exists(project_id, project_repo)

    try:
        result: dict[str, Any] = sync_responses(project_id)
    except FormNotConfiguredError as exc:
        # form.json 未作成 → 先に Form 作成 API を呼ぶよう案内
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except GoogleAuthRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    except PollingRetryExhaustedError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return SyncResponsesResult.model_validate(result)


@router.get(
    "/{project_id}/responses",
    response_model=list[ResponseModel],
)
def list_project_responses(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repository),
    response_repo: ResponseRepository = Depends(get_response_repository),
) -> list[ResponseModel]:
    """受領済み回答（出席番号ごとの最新版のみ）を返す。"""
    _ensure_project_exists(project_id, project_repo)
    return response_repo.list_latest_per_student(project_id)


@router.get(
    "/{project_id}/responses/status",
    response_model=ResponsesStatusResult,
)
def get_project_responses_status(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repository),
    response_repo: ResponseRepository = Depends(get_response_repository),
) -> ResponsesStatusResult:
    """受領状況サマリ（受領済み出席番号と未受領出席番号）を返す。"""
    _ensure_project_exists(project_id, project_repo)

    received = sorted(response_repo.get_received_student_numbers(project_id))
    pending = sorted(response_repo.get_pending_student_numbers(project_id))
    return ResponsesStatusResult(
        project_id=project_id,
        received=received,
        pending=pending,
    )


# 「FileXxxRepository 限定で扱う」前提が不要なため、抽象 Repository を DI に使う
# （Phase 1.2 の方針：将来 DB 化時に差し替え可能性を最大化）。
# FileProjectRepository / FileResponseRepository への直接依存は polling.py 内のみで完結。
_ = FileProjectRepository  # re-export 用の明示参照（lint 抑止）
_ = FileResponseRepository


__all__ = ["router"]
