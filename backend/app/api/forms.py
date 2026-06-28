"""Form 作成・取得 API ルータ（Phase 2.2）。

requirements.md §6 のうち以下を担当する：

- ``POST /api/projects/{id}/form``  プロジェクトの候補日時から Google Form を生成
- ``GET  /api/projects/{id}/form``  生成済み ``form.json`` の取得

Phase 2.2 の決定事項（``docs/handoff_phase2_0.md`` §採用方式まとめ）：

- **二重作成防止**：既に ``form.json`` が存在する場合は 409 Conflict を返し、
  Google API を再度呼ばない（実 Form がゴミとして残るのを防ぐ）
- **認証**：``app.services.google_forms.create_form`` 内部で
  ``google_auth.get_valid_credentials()`` を呼ぶ。トークン未保存・リフレッシュ失敗時は
  ``GoogleAuthRequiredError`` が投げられるので、本ハンドラで 401 に変換
- **404**：プロジェクト自体が存在しない場合（Phase 2.1 と同じ挙動）
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_project_repository
from app.models.form import FormInfo
from app.repositories.file_repository import FileProjectRepository
from app.services.google_forms import GoogleAuthRequiredError, create_form


router = APIRouter(prefix="/api/projects", tags=["forms"])


def _get_file_project_repository(
    repo: FileProjectRepository = Depends(get_project_repository),
) -> FileProjectRepository:
    """``FileProjectRepository`` 限定で取得するヘルパ。

    本ルータは ``has_form`` / ``get_form_info`` / ``save_form_info`` を呼ぶため、
    抽象 ``ProjectRepository`` ではなく ``FileProjectRepository`` 具象に依存する。
    将来 DB 実装に切り替える場合は ``FormRepository`` 抽象を別途切り出す前提
    （Phase 1.2 の Repository 抽象方針に沿う暫定実装）。
    """
    if not isinstance(repo, FileProjectRepository):
        # DI override で別実装が差し込まれた場合の防御
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="form API は FileProjectRepository を前提とする",
        )
    return repo


@router.post(
    "/{project_id}/form",
    response_model=FormInfo,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
def create_project_form(
    project_id: str,
    repo: FileProjectRepository = Depends(_get_file_project_repository),
) -> FormInfo:
    """プロジェクトから Google Form を生成し ``form.json`` に保存する。

    - 404: プロジェクト未存在
    - 409: 既に ``form.json`` が存在（二重作成防止）
    - 401: OAuth トークン未保存・リフレッシュ失敗
    - 201: 作成成功、FormInfo を返す
    """
    project = repo.get(project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"project '{project_id}' not found",
        )

    # 二重作成防止：Google API 呼び出し前に判定する
    if repo.has_form(project_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"form already exists for project '{project_id}'",
        )

    try:
        form_info = create_form(project)
    except GoogleAuthRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    repo.save_form_info(project_id, form_info)
    return form_info


@router.get(
    "/{project_id}/form",
    response_model=FormInfo,
    response_model_by_alias=True,
)
def get_project_form(
    project_id: str,
    repo: FileProjectRepository = Depends(_get_file_project_repository),
) -> FormInfo:
    """生成済み ``form.json`` を返す。

    - 404: プロジェクト未存在 / ``form.json`` 未生成
    - 200: ``FormInfo`` を返す
    """
    if repo.get(project_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"project '{project_id}' not found",
        )

    form_info = repo.get_form_info(project_id)
    if form_info is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"form not yet created for project '{project_id}'",
        )
    return form_info


__all__ = ["router"]
