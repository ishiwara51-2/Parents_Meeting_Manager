"""Phase 2.3: 回答 API と FileResponseRepository のテスト。

API:
    - POST /api/projects/{id}/responses/sync
    - GET  /api/projects/{id}/responses
    - GET  /api/projects/{id}/responses/status

Repository:
    - FileResponseRepository.save_response / list_latest_per_student /
      list_all / get_received_student_numbers / get_pending_student_numbers /
      get_known_form_response_ids

requirements.md §4.4「最新版のみ後続処理で使用」/ §6 API 設計に対応する。
"""

from __future__ import annotations

from datetime import datetime, time, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from app.models.form import FormInfo
from app.models.response import Availability, Response
from app.repositories.file_repository import (
    FileProjectRepository,
    FileResponseRepository,
)


# ---------------------------------------------------------------------------
# 共通フィクスチャ
# ---------------------------------------------------------------------------


def _sample_project_payload() -> dict:
    return {
        "display_name": "3年A組 7月面談",
        "slot_minutes": 20,
        "candidate_dates": ["2026-07-15", "2026-07-16"],
        "candidate_time_slots": [
            {"start": "16:00", "end": "16:20"},
            {"start": "16:20", "end": "16:40"},
        ],
        "student_numbers": [1, 2, 3, 4],
    }


def _create_project_and_form_json(client: TestClient) -> str:
    """プロジェクトを作成し form.json を直接配置（Form 作成 API 経由ではない）。"""
    resp = client.post("/api/projects", json=_sample_project_payload())
    assert resp.status_code == 201, resp.text
    project_id = resp.json()["project_id"]

    settings = get_settings()
    repo = FileProjectRepository(settings)
    form_info = FormInfo(
        form_id="FAKE_FORM_ID",
        responder_uri="https://docs.google.com/forms/d/FAKE_FORM_ID/viewform",
        edit_uri="https://docs.google.com/forms/d/FAKE_FORM_ID/edit",
        student_number_question_id="QID_SN",
        row_question_id_by_date={
            "2026-07-15": "QID_ROW_0",
            "2026-07-16": "QID_ROW_1",
        },
        time_slot_labels=["16:00-16:20", "16:20-16:40"],
    )
    repo.save_form_info(project_id, form_info)
    return project_id


def _make_response(
    *,
    project_id: str,
    sn: int,
    response_id: str,
    submitted_at: datetime,
) -> Response:
    return Response(
        project_id=project_id,
        student_number=sn,
        submitted_at=submitted_at,
        google_form_response_id=response_id,
        availability=[
            Availability(date="2026-07-15", start=time(16, 0), end=time(16, 20)),
        ],
    )


@pytest.fixture
def fake_creds() -> object:
    return MagicMock(name="FakeCredentials")


# ---------------------------------------------------------------------------
# 9. FileResponseRepository.list_latest_per_student：各生徒の最新ファイルを返す
# ---------------------------------------------------------------------------


def test_repository_returns_latest_response_per_student(
    isolated_data_root: Path,
) -> None:
    """同一生徒の複数回答のうち、``submitted_at`` 最新のものだけ返す。

    requirements.md §4.4「後続処理では最新のものを使用」
    """
    settings = get_settings()
    settings.ensure_directories()

    with TestClient(create_app()) as client:
        client.post("/api/projects", json=_sample_project_payload())  # 何でもOK
        proj_resp = client.get("/api/projects")
        project_id = proj_resp.json()[0]["project_id"]

    repo = FileResponseRepository(settings)

    # 同一 sn=1 の 2 回答（古 / 新）
    older = _make_response(
        project_id=project_id,
        sn=1,
        response_id="R1",
        submitted_at=datetime(2026, 6, 28, 10, 0, 0, tzinfo=timezone.utc),
    )
    newer = _make_response(
        project_id=project_id,
        sn=1,
        response_id="R2",
        submitted_at=datetime(2026, 6, 28, 12, 0, 0, tzinfo=timezone.utc),
    )
    # 別生徒 sn=2 の 1 回答
    other = _make_response(
        project_id=project_id,
        sn=2,
        response_id="R3",
        submitted_at=datetime(2026, 6, 28, 11, 0, 0, tzinfo=timezone.utc),
    )

    repo.save_response(project_id, older)
    repo.save_response(project_id, newer)
    repo.save_response(project_id, other)

    latest = repo.list_latest_per_student(project_id)
    by_sn = {r.student_number: r for r in latest}

    assert set(by_sn.keys()) == {1, 2}
    assert by_sn[1].google_form_response_id == "R2", (
        "sn=1 は新しい R2 が選ばれるべき"
    )
    assert by_sn[2].google_form_response_id == "R3"


# ---------------------------------------------------------------------------
# 10. 未受領出席番号計算（プロジェクトの全生徒 − 受領済み）
# ---------------------------------------------------------------------------


def test_responses_status_api_returns_pending_students(
    isolated_data_root: Path,
) -> None:
    """``GET /api/projects/{id}/responses/status`` が

    - ``received``: 受領済み出席番号のソート済みリスト
    - ``pending``:  ``Project.student_numbers`` − ``received`` のソート済みリスト

    を返す。
    """
    settings = get_settings()

    with TestClient(create_app()) as client:
        project_id = _create_project_and_form_json(client)
        # student_numbers = [1, 2, 3, 4]、うち 1, 3 のみ受領済み
        repo = FileResponseRepository(settings)
        for sn, rid in [(1, "R1"), (3, "R3")]:
            repo.save_response(
                project_id,
                _make_response(
                    project_id=project_id,
                    sn=sn,
                    response_id=rid,
                    submitted_at=datetime(
                        2026, 6, 28, 10, 0, 0, tzinfo=timezone.utc
                    ),
                ),
            )

        resp = client.get(f"/api/projects/{project_id}/responses/status")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert sorted(body["received"]) == [1, 3]
    assert sorted(body["pending"]) == [2, 4]


# ---------------------------------------------------------------------------
# 11. GET /api/projects/{id}/responses：最新回答一覧を返す
# ---------------------------------------------------------------------------


def test_get_responses_endpoint_returns_latest_per_student(
    isolated_data_root: Path,
) -> None:
    """``GET /api/projects/{id}/responses`` は各出席番号の最新回答1件のみ
    のリストを返す（同一 sn の古い回答は含まない）。
    """
    settings = get_settings()

    with TestClient(create_app()) as client:
        project_id = _create_project_and_form_json(client)
        repo = FileResponseRepository(settings)

        # sn=1 に 2 回答（古/新）と sn=2 に 1 回答
        repo.save_response(
            project_id,
            _make_response(
                project_id=project_id,
                sn=1,
                response_id="R1",
                submitted_at=datetime(
                    2026, 6, 28, 10, 0, 0, tzinfo=timezone.utc
                ),
            ),
        )
        repo.save_response(
            project_id,
            _make_response(
                project_id=project_id,
                sn=1,
                response_id="R2",
                submitted_at=datetime(
                    2026, 6, 28, 12, 0, 0, tzinfo=timezone.utc
                ),
            ),
        )
        repo.save_response(
            project_id,
            _make_response(
                project_id=project_id,
                sn=2,
                response_id="R3",
                submitted_at=datetime(
                    2026, 6, 28, 11, 0, 0, tzinfo=timezone.utc
                ),
            ),
        )

        resp = client.get(f"/api/projects/{project_id}/responses")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert isinstance(body, list)
    # 2 件（sn=1 最新と sn=2）
    assert len(body) == 2
    by_sn = {item["student_number"]: item for item in body}
    assert by_sn[1]["google_form_response_id"] == "R2"
    assert by_sn[2]["google_form_response_id"] == "R3"
