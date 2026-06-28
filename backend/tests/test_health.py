"""ヘルスチェック ``GET /api/health`` のテスト。

requirements.md §6 / implementation_prompts_subdivided.md Phase 1.1 §テスト に従い、
- 200 応答
- ``{"status": "ok"}`` ボディ
- 起動時にデータディレクトリ（``config/``、``projects/``）が自動作成される
の3点を検証する。
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app


def test_health_returns_200_and_ok() -> None:
    """/api/health は 200 と ``{"status": "ok"}`` を返す。"""
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_startup_creates_data_directories(isolated_data_root: Path) -> None:
    """起動時に config/ と projects/ が自動作成される。"""
    app = create_app()
    with TestClient(app):
        settings = get_settings()
        assert settings.config_dir.exists()
        assert settings.config_dir.is_dir()
        assert settings.projects_dir.exists()
        assert settings.projects_dir.is_dir()
        # データルートが一時ディレクトリに向いていることも確認
        assert settings.app_data_root == isolated_data_root
