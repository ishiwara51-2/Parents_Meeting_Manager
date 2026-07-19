"""Excel 出力 API。

requirements.md §4.8 / §6 に従い、以下のエンドポイントを提供する。

- ``GET /api/projects/{id}/excel`` — ドラフトから xlsx を生成してダウンロード

処理フロー:
    1. プロジェクトを取得（不在 → 404）
    2. 最新ドラフトを取得（不在 → 404）
    3. excel_generator.generate_excel(project, draft) で bytes 生成
    4. Response で返却
       - Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
       - Content-Disposition: attachment; filename="<ascii_name>.xlsx"; filename*=UTF-8''<encoded>
"""

from __future__ import annotations

import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response

from app.dependencies import get_draft_repository, get_project_repository
from app.models.project import Project
from app.repositories.base import DraftRepository, ProjectRepository
from app.services.excel_generator import generate_excel

router = APIRouter(prefix="/api/projects", tags=["excel"])

_XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


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


def _build_content_disposition(project_name: str, project_id: str) -> str:
    """Content-Disposition ヘッダ値を構築する。

    RFC5987 に従い UTF-8 エンコードされた filename* と ASCII フォールバックの
    両方を返す。日本語プロジェクト名に対応する。
    """
    ascii_filename = f"schedule_{project_id}.xlsx"
    utf8_filename = f"{project_name}.xlsx"
    encoded = urllib.parse.quote(utf8_filename, safe="")
    return f'attachment; filename="{ascii_filename}"; filename*=UTF-8\'\'{encoded}'


@router.get(
    "/{project_id}/excel",
    summary="Excel 生成・ダウンロード",
    description=(
        "最新のドラフトから3シート構成（日程案（出席番号）／番号-氏名対応表／"
        "日程案（氏名））の xlsx を生成してダウンロードする。"
        "ドラフトが存在しない場合は 404 を返す。"
        "requirements.md §4.8 の「Excel出力」機能。"
    ),
    response_class=Response,
    responses={
        200: {
            "content": {_XLSX_MEDIA_TYPE: {}},
            "description": "xlsx ファイル",
        },
        404: {"description": "プロジェクトまたはドラフトが見つからない"},
    },
)
def download_excel(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repository),
    draft_repo: DraftRepository = Depends(get_draft_repository),
) -> Response:
    """最新ドラフトから xlsx を生成してダウンロードする。

    - プロジェクト不在 → 404
    - ドラフト不在 → 404
    """
    # 1. プロジェクト取得
    project = _get_project_or_404(project_id, project_repo)

    # 2. 最新ドラフト取得
    draft = draft_repo.get_latest(project_id)
    if draft is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"プロジェクト '{project_id}' のドラフトが見つかりません。先に日程案を保存してください。",
        )

    # 3. Excel 生成
    excel_bytes = generate_excel(project, draft)

    # 4. Content-Disposition ヘッダ構築（RFC5987 形式）
    content_disposition = _build_content_disposition(project.display_name, project_id)

    return Response(
        content=excel_bytes,
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": content_disposition},
    )
