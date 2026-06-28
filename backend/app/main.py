"""FastAPI エントリポイント。

requirements.md §6 / §7 / §8.4 に従い、以下を担う。

- アプリ起動時にデータディレクトリ（``config/``、``projects/``）を自動作成
- ヘルスチェック ``GET /api/health`` の提供（``{"status": "ok"}``）

ルータの追加は後続フェーズで `app/api/` 配下に実装する。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app.config import get_settings


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

    @application.get("/api/health", tags=["health"])
    async def health() -> dict[str, str]:
        """ヘルスチェック。常に ``{"status": "ok"}`` を返す。"""
        return {"status": "ok"}

    return application


app = create_app()
