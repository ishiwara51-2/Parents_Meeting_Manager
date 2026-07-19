"""Excel 出力 API のテスト。

GET /api/projects/{id}/excel エンドポイントを検証する。

テストケース:
1. ドラフトが存在するプロジェクト: 200, Content-Type が xlsx の media type, body が PK で始まる
2. ドラフト未保存のプロジェクト: 404
3. Content-Disposition ヘッダに 'attachment' が含まれること
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _create_project(client: TestClient, display_name: str = "テスト面談") -> str:
    """テスト用プロジェクトを作成し project_id を返す。"""
    resp = client.post(
        "/api/projects",
        json={
            "display_name": display_name,
            "slot_minutes": 20,
            "candidate_dates": ["2026-07-15"],
            "candidate_time_slots": [
                {"start": "16:00", "end": "16:20"},
                {"start": "16:20", "end": "16:40"},
            ],
            "student_numbers": [1, 2, 3],
        },
    )
    assert resp.status_code == 201, f"プロジェクト作成失敗: {resp.text}"
    return resp.json()["project_id"]


def _save_draft(client: TestClient, project_id: str) -> None:
    """テスト用ドラフトを保存する。"""
    resp = client.post(
        f"/api/projects/{project_id}/drafts",
        json={
            "assignments": [
                {
                    "student_number": 1,
                    "date": "2026-07-15",
                    "start": "16:00",
                    "end": "16:20",
                },
                {
                    "student_number": 2,
                    "date": "2026-07-15",
                    "start": "16:20",
                    "end": "16:40",
                },
            ],
            "unassigned_students": [3],
            "violated_constraints": [],
        },
    )
    assert resp.status_code == 201, f"ドラフト保存失敗: {resp.text}"


@pytest.fixture
def client() -> TestClient:
    """TestClient を返すフィクスチャ。"""
    return TestClient(create_app())


class TestExcelApi:
    """GET /api/projects/{id}/excel のテスト群。"""

    def test_excel_returns_200_and_xlsx_content_type(self, client: TestClient) -> None:
        """ドラフトが存在するプロジェクトに対して 200 と xlsx の Content-Type が返ること。"""
        project_id = _create_project(client)
        _save_draft(client, project_id)

        resp = client.get(f"/api/projects/{project_id}/excel")

        assert resp.status_code == 200, f"期待 200、実際 {resp.status_code}: {resp.text}"
        assert _XLSX_MEDIA_TYPE in resp.headers.get("content-type", ""), (
            f"Content-Type が xlsx でない: {resp.headers.get('content-type')}"
        )

    def test_excel_response_body_starts_with_zip_magic_bytes(
        self, client: TestClient
    ) -> None:
        """レスポンスボディが PK で始まること（xlsx=ZIP形式のマジックバイト確認）。"""
        project_id = _create_project(client)
        _save_draft(client, project_id)

        resp = client.get(f"/api/projects/{project_id}/excel")

        assert resp.status_code == 200
        assert resp.content[:2] == b"PK", f"先頭 2 バイトが PK でない: {resp.content[:8]!r}"

    def test_excel_no_draft_returns_404(self, client: TestClient) -> None:
        """ドラフト未保存のプロジェクトに対して 404 を返すこと。"""
        project_id = _create_project(client)
        # ドラフトは保存しない

        resp = client.get(f"/api/projects/{project_id}/excel")

        assert resp.status_code == 404, (
            f"ドラフト未保存時に 404 を期待、実際 {resp.status_code}: {resp.text}"
        )

    def test_excel_project_not_found_returns_404(self, client: TestClient) -> None:
        """存在しないプロジェクトに対して 404 を返すこと。"""
        resp = client.get("/api/projects/nonexistent-project/excel")

        assert resp.status_code == 404

    def test_excel_content_disposition_contains_attachment(
        self, client: TestClient
    ) -> None:
        """Content-Disposition ヘッダに 'attachment' が含まれること。"""
        project_id = _create_project(client, display_name="3年A組 7月面談")
        _save_draft(client, project_id)

        resp = client.get(f"/api/projects/{project_id}/excel")

        assert resp.status_code == 200
        content_disposition = resp.headers.get("content-disposition", "")
        assert "attachment" in content_disposition, (
            f"Content-Disposition ヘッダに 'attachment' が含まれない: {content_disposition!r}"
        )
