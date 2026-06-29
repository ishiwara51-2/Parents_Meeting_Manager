"""Phase 6.1: エラーメッセージとロギング設定のテスト。

テスト対象:
1. configure_logging() を呼んでもエラーにならないこと
2. 存在しないプロジェクト ID への GET が 404 を返すこと
3. 404 レスポンスに 'detail' フィールドが含まれること

RED フェーズ: `app.logging_config` が未実装のためインポートエラーで全テスト失敗する想定。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.logging_config import configure_logging  # RED: 未実装モジュール
from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    """TestClient を返すフィクスチャ。"""
    return TestClient(create_app())


class TestLoggingConfig:
    """ロギング設定のテスト。"""

    def test_configure_logging_does_not_raise(self) -> None:
        """configure_logging() を呼んでもエラーにならないこと。"""
        configure_logging()  # 例外が上がらなければ PASS


class TestErrorMessages:
    """エラーメッセージのテスト。"""

    def test_get_nonexistent_project_returns_404(self, client: TestClient) -> None:
        """存在しないプロジェクト ID への GET が 404 を返すこと。"""
        resp = client.get("/api/projects/nonexistent-project-id-xyz")
        assert resp.status_code == 404

    def test_get_nonexistent_project_returns_detail_message(
        self, client: TestClient
    ) -> None:
        """404 レスポンスに 'detail' フィールドが含まれること。"""
        resp = client.get("/api/projects/nonexistent-project-id-xyz")
        body = resp.json()
        assert "detail" in body
        assert body["detail"] != ""
