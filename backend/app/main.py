"""FastAPI エントリポイント。

requirements.md §6 / §7 / §8.4 に従い、以下を担う。

- アプリ起動時にデータディレクトリ（``config/``、``projects/``）を自動作成
- ヘルスチェック ``GET /api/health`` の提供（``{"status": "ok"}``）
- OAuth 認証ルータ（Phase 1.3）の登録
- セッションミドルウェア（CSRF 対策の state 保存先、Phase 1.3）
- ビルド済みフロントエンドの静的ファイル配信（Phase 4.1）

ルータの追加は後続フェーズで `app/api/` 配下に実装する。
"""

from __future__ import annotations

import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api.auth import router as auth_router
from app.api.drafts import router as drafts_router
from app.api.forms import router as forms_router
from app.api.pdf import router as pdf_router
from app.api.projects import router as projects_router
from app.api.responses import router as responses_router
from app.api.rules import router as rules_router
from app.api.schedule import router as schedule_router
from app.config import get_settings


ENV_SESSION_SECRET = "MEETING_SCHEDULER_SESSION_SECRET"


def _resolve_session_secret() -> str:
    """セッション署名鍵を解決する。

    優先順位:
        1. 環境変数 ``MEETING_SCHEDULER_SESSION_SECRET``
        2. プロセス起動時に ``secrets.token_urlsafe(32)`` で都度生成

    プロセス再起動でセッションは無効化される（プロトタイプ運用として許容）。
    """
    explicit = os.getenv(ENV_SESSION_SECRET)
    if explicit:
        return explicit
    return secrets.token_urlsafe(32)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """アプリのライフサイクルフック。

    起動時にデータディレクトリを冪等に作成する。
    """
    settings = get_settings()
    settings.ensure_directories()
    yield


def create_app() -> FastAPI:
    """FastAPI アプリのファクトリ。

    テストから差し替えやすいよう、生成ロジックを関数化している。
    """
    application = FastAPI(
        title="保護者面談調整ツール API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CSRF 対策の state を保存するためのセッションミドルウェア
    # （requirements.md §2.1, Phase 1.3）
    application.add_middleware(
        SessionMiddleware,
        secret_key=_resolve_session_secret(),
        # http://localhost 運用のため secure=False（既定）。https_only も無効。
        same_site="lax",
    )

    @application.get("/api/health", tags=["health"])
    async def health() -> dict[str, str]:
        """ヘルスチェック。常に ``{"status": "ok"}`` を返す。"""
        return {"status": "ok"}

    application.include_router(auth_router)
    application.include_router(projects_router)
    application.include_router(forms_router)
    application.include_router(responses_router)
    application.include_router(rules_router)
    application.include_router(schedule_router)
    application.include_router(drafts_router)
    application.include_router(pdf_router)

    # ===== フロントエンド静的ファイル配信（Phase 4.1）=====
    # requirements.md §2.2 の本番モード起動（start.ps1）で使用。
    # frontend/dist が存在する場合のみ配信を有効化する。
    # Vite のビルド出力先が frontend/dist であることを前提とする。
    _frontend_dist = (
        Path(__file__).resolve().parent.parent.parent.parent
        / "frontend"
        / "dist"
    )
    if _frontend_dist.is_dir():
        # /assets などの静的リソースを配信
        application.mount(
            "/assets",
            StaticFiles(directory=str(_frontend_dist / "assets")),
            name="assets",
        )

        # SPA フォールバック: /api/* 以外のすべてのリクエストに index.html を返す
        @application.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str) -> FileResponse:  # noqa: ARG001
            """SPA（Single Page Application）のフォールバック。

            React Router がクライアントサイドルーティングを担うため、
            `/api/` に一致しないパスはすべて ``index.html`` を返す。
            """
            index_html = _frontend_dist / "index.html"
            return FileResponse(str(index_html))

    return application


app = create_app()
