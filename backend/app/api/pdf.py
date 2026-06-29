"""PDF 出力 API。

requirements.md §4.8 / §6 に従い、以下のエンドポイントを提供する。

- ``GET /api/projects/{id}/pdf`` — ドラフトから PDF を生成してダウンロード

処理フロー:
    1. プロジェクトを取得（不在 → 404）
    2. 最新ドラフトを取得（不在 → 404）
    3. pdf_generator.generate_pdf(project, draft) で bytes 生成
    4. StreamingResponse または Response で返却
       - Content-Type: application/pdf
       - Content-Disposition: attachment; filename="<ascii_name>.pdf"; filename*=UTF-8''<encoded>

Phase 5.1 で実装された generate_pdf のシグネチャ:
    pdf_bytes: bytes = generate_pdf(project, draft)
"""

from __future__ import annotations

import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response

from app.dependencies import get_draft_repository, get_project_repository
from app.models.project import Project
from app.repositories.base import DraftRepository, ProjectRepository
from app.services.pdf_generator import generate_pdf

router = APIRouter(prefix="/api/projects", tags=["pdf"])


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

    Args:
        project_name: プロジェクト表示名（日本語含む可能性あり）
        project_id: プロジェクト ID（ASCII フォールバック用）

    Returns:
        Content-Disposition ヘッダ値文字列
    """
    # ASCII フォールバック（ブラウザ互換性のため）
    ascii_filename = f"schedule_{project_id}.pdf"
    # RFC5987 エンコーディング（日本語ファイル名対応）
    utf8_filename = f"{project_name}.pdf"
    encoded = urllib.parse.quote(utf8_filename, safe="")
    return f'attachment; filename="{ascii_filename}"; filename*=UTF-8\'\'{encoded}'


@router.get(
    "/{project_id}/pdf",
    summary="PDF 生成・ダウンロード",
    description=(
        "最新のドラフトから A4 縦・マトリクス形式の PDF を生成してダウンロードする。"
        "ドラフトが存在しない場合は 404 を返す。"
        "requirements.md §4.8 の「PDF出力」機能。"
    ),
    response_class=Response,
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "PDF ファイル",
        },
        404: {"description": "プロジェクトまたはドラフトが見つからない"},
    },
)
def download_pdf(
    project_id: str,
    project_repo: ProjectRepository = Depends(get_project_repository),
    draft_repo: DraftRepository = Depends(get_draft_repository),
) -> Response:
    """最新ドラフトから PDF を生成してダウンロードする。

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

    # 3. PDF 生成
    pdf_bytes = generate_pdf(project, draft)

    # 4. Content-Disposition ヘッダ構築（RFC5987 形式）
    content_disposition = _build_content_disposition(project.display_name, project_id)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": content_disposition},
    )
