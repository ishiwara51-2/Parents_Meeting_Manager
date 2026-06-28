"""FastAPI エントリポイント。

requirements.md §6 / §7 / §8.4 に従い、以下を担う。

- アプリ起動時にデータディレクトリ（``config/``、``projects/``）を自動作成
- ヘルスチェック ``GET /api/health`` の提供（``{"status": "ok"}``）
- OAuth 認証ルータ（Phase 1.3）の登録
- セッションミドルウェア（CSRF 対策の state 保存先、Phase 1.3）

ルータの追加は後続フェーズで `app/api/` 配下に実装する。
"""

from __future__ import annotations

import os
import secrets
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.api.auth import router as auth_router
from app.api.forms import router as forms_router
from app.api.projects import router as projects_router
from app.api.responses import router as responses_router
from app.api.rules import router as rules_router
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

    return application


app = create_app()
