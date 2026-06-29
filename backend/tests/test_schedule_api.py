"""Phase 3.3b: スケジューラ API のテスト。

requirements.md §4.6 / §6 および implementation_prompts_subdivided.md の Phase 3.3b
指示に基づき、``POST /api/projects/{id}/schedule`` の振る舞いを検証する。

検証観点:
    - 正常系：受領済み回答に対してスケジューラが走り、SchedulingResult 相当の
      レスポンスを返すこと（`assignments` / `unassigned_students` /
      `violated_constraints` フィールドを含む）
    - 未受領生徒はスケジューリング対象外（assignments / unassigned のどちらにも
      含まれない）
    - 404 系：
        * プロジェクトが存在しない
        * form.json が未作成のプロジェクト
        * 受領済み回答が 0 件のプロジェクト
    - 任意で `solver_time_limit_seconds` を上書きできること
    - レスポンスが Phase 3.2/3.3a の SchedulingResult スキーマ
      （assignments の各要素は student_number/date/start/end）

TDD 順序:
    1. このファイルを RED コミット（API ルータ未実装で 404/AttributeError）
    2. test(phase3.3b): add schedule api test cases (RED)
    3. 実装で全 PASS（GREEN）
    4. feat(phase3.3b): implement schedule api endpoint (GREEN)
"""

from __future__ import annotations

from datetime import datetime, time, timezone
from pathlib import Path
from unittest.mock import patch

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
# 共通フィクスチャヘルパ
# ---------------------------------------------------------------------------


def _sample_project_payload() -> dict:
    """テスト用プロジェクト作成 payload。

    候補日 1 日 × 候補スロット 3 個 × 生徒 3 名のシンプルな構成。
    余裕があるため、3 名分の availability が揃っていれば全員配置される。
    """
    return {
        "display_name": "3年A組 7月面談",
        "slot_minutes": 20,
        "candidate_dates": ["2026-07-15"],
        "candidate_time_slots": [
            {"start": "16:00", "end": "16:20"},
            {"start": "16:20", "end": "16:40"},
            {"start": "16:40", "end": "17:00"},
        ],
        "student_numbers": [1, 2, 3],
    }


def _create_project_with_form_json(client: TestClient) -> str:
    """プロジェクトを作成し、form.json を直接配置（Form 作成 API を経由しない）。

    `form.json` の有無は API ハンドラのバリデーション分岐に関係するため、
    本テストでも明示的に作成する。
    """
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
        row_question_id_by_date={"2026-07-15": "QID_ROW_0"},
        time_slot_labels=["16:00-16:20", "16:20-16:40", "16:40-17:00"],
    )
    repo.save_form_info(project_id, form_info)
    return project_id


def _save_response_for(
    *,
    project_id: str,
    sn: int,
    slots: list[tuple[str, str, str]],
    response_id: str | None = None,
) -> None:
    """指定生徒の Response を Repository 経由で保存するヘルパ。

    Phase 2.3 の保存規約（``responses/<sn>/<YYYYMMDD_HHMMSS>.json``）に従う。
    """
    settings = get_settings()
    repo = FileResponseRepository(settings)
    response = Response(
        project_id=project_id,
        student_number=sn,
        submitted_at=datetime(2026, 6, 28, 12, sn % 60, 0, tzinfo=timezone.utc),
        google_form_response_id=response_id or f"R_{sn}",
        availability=[
            Availability(
                date=d,
                start=time.fromisoformat(s),
                end=time.fromisoformat(e),
            )
            for d, s, e in slots
        ],
    )
    repo.save_response(project_id, response)


# ---------------------------------------------------------------------------
# 1. 正常系：全員に availability があれば全員配置されレスポンス構造が正しい
# ---------------------------------------------------------------------------


def test_schedule_api_returns_assignments_for_all_received(
    isolated_data_root: Path,
) -> None:
    """全員受領済みで余裕があるケース：3 名全員が配置される。

    レスポンスは `assignments` / `unassigned_students` / `violated_constraints` を
    キーに持ち、`assignments` の各要素は student_number/date/start/end を持つ。
    """
    with TestClient(create_app()) as client:
        project_id = _create_project_with_form_json(client)

        # 3 名全員が候補スロット全部を「可」と申告
        for sn in (1, 2, 3):
            _save_response_for(
                project_id=project_id,
                sn=sn,
                slots=[
                    ("2026-07-15", "16:00", "16:20"),
                    ("2026-07-15", "16:20", "16:40"),
                    ("2026-07-15", "16:40", "17:00"),
                ],
            )

        resp = client.post(f"/api/projects/{project_id}/schedule")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    # SchedulingResult スキーマ
    assert "assignments" in body
    assert "unassigned_students" in body
    assert "violated_constraints" in body
    assignments = body["assignments"]
    # 3 名全員が配置される（候補スロットは 3 つで全員配置可能）
    assert len(assignments) == 3
    placed_sns = sorted(a["student_number"] for a in assignments)
    assert placed_sns == [1, 2, 3]
    # Assignment スキーマ
    for a in assignments:
        assert "student_number" in a
        assert "date" in a
        assert "start" in a
        assert "end" in a
    assert body["unassigned_students"] == []


# ---------------------------------------------------------------------------
# 2. 未受領生徒の除外：未受領は assignments / unassigned に含まれない
# ---------------------------------------------------------------------------


def test_schedule_api_excludes_pending_students(
    isolated_data_root: Path,
) -> None:
    """未受領生徒はスケジューリング対象外（requirements.md §4.6.1）。

    student_numbers=[1, 2, 3] のうち sn=1 のみ受領済みなら、API は sn=1 のみを
    対象に計算し、sn=2, 3 は assignments にも unassigned_students にも含まれない。
    """
    with TestClient(create_app()) as client:
        project_id = _create_project_with_form_json(client)
        # sn=1 のみ受領
        _save_response_for(
            project_id=project_id,
            sn=1,
            slots=[
                ("2026-07-15", "16:00", "16:20"),
            ],
        )

        resp = client.post(f"/api/projects/{project_id}/schedule")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    placed_sns = {a["student_number"] for a in body["assignments"]}
    # sn=1 は配置される、sn=2/3 は除外（未受領）
    assert placed_sns == {1}
    # unassigned は受領済みの中の未配置のみ → sn=1 は配置済みなので空
    assert body["unassigned_students"] == []


# ---------------------------------------------------------------------------
# 3. 404：プロジェクトが存在しない
# ---------------------------------------------------------------------------


def test_schedule_api_returns_404_for_unknown_project(
    isolated_data_root: Path,
) -> None:
    """存在しない project_id への呼び出しは 404。"""
    with TestClient(create_app()) as client:
        resp = client.post("/api/projects/nonexistent-project/schedule")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 4. 404：form.json が未作成（Form 未作成のプロジェクト）
# ---------------------------------------------------------------------------


def test_schedule_api_returns_404_when_form_not_configured(
    isolated_data_root: Path,
) -> None:
    """form.json が無いプロジェクトには 404 を返す。

    Form を作成していない（候補日時の聴取が始まっていない）プロジェクトで
    スケジューリングを試行されても、有意味な結果は出せないため 404 とする。
    """
    with TestClient(create_app()) as client:
        # プロジェクトを作成するが form.json は配置しない
        resp = client.post("/api/projects", json=_sample_project_payload())
        assert resp.status_code == 201
        project_id = resp.json()["project_id"]

        resp = client.post(f"/api/projects/{project_id}/schedule")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 5. 404：受領済み回答が 0 件
# ---------------------------------------------------------------------------


def test_schedule_api_returns_404_when_no_responses_received(
    isolated_data_root: Path,
) -> None:
    """form.json はあるが回答が 1 件も無いケースは 404。

    スケジューリング対象生徒がゼロなので意味のある計算ができない。
    フロントエンドには「先に回答取得を」と案内できるよう 404 を返す。
    """
    with TestClient(create_app()) as client:
        project_id = _create_project_with_form_json(client)
        # 回答を 1 件も保存しない
        resp = client.post(f"/api/projects/{project_id}/schedule")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 6. ハード制約のみで配置されないケース：unassigned_students と violated_constraints
# ---------------------------------------------------------------------------


def test_schedule_api_reports_unassigned_students_on_collision(
    isolated_data_root: Path,
) -> None:
    """候補スロットが 1 つしかなく 3 名全員が同じスロットしか「可」と
    申告していない場合、1 名のみ配置され他は unassigned_students に列挙される。
    """
    payload = {
        "display_name": "ぴったり面談",
        "slot_minutes": 20,
        "candidate_dates": ["2026-07-15"],
        "candidate_time_slots": [
            {"start": "16:00", "end": "16:20"},
        ],
        "student_numbers": [1, 2, 3],
    }
    with TestClient(create_app()) as client:
        resp = client.post("/api/projects", json=payload)
        assert resp.status_code == 201, resp.text
        project_id = resp.json()["project_id"]

        # form.json を直接配置
        settings = get_settings()
        repo = FileProjectRepository(settings)
        repo.save_form_info(
            project_id,
            FormInfo(
                form_id="FAKE_FORM_ID",
                responder_uri="https://example.com/viewform",
                edit_uri="https://example.com/edit",
                student_number_question_id="QID_SN",
                row_question_id_by_date={"2026-07-15": "QID_ROW_0"},
                time_slot_labels=["16:00-16:20"],
            ),
        )

        for sn in (1, 2, 3):
            _save_response_for(
                project_id=project_id,
                sn=sn,
                slots=[("2026-07-15", "16:00", "16:20")],
            )

        resp = client.post(f"/api/projects/{project_id}/schedule")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["assignments"]) == 1
    assert len(body["unassigned_students"]) == 2
    # 衝突系の説明文が含まれる
    assert any(
        "競合" in msg or "衝突" in msg
        for msg in body["violated_constraints"]
    )


# ---------------------------------------------------------------------------
# 7. ソルバ例外時：503 を返す（CP-SAT が想定外エラー）
# ---------------------------------------------------------------------------


def test_schedule_api_returns_503_on_solver_failure(
    isolated_data_root: Path,
) -> None:
    """scheduler.solve が例外を投げた場合、API は 503 を返す。

    実機で CP-SAT が予期せぬ例外を投げるケースはほぼ無いが、防御として
    503 マッピングを検証する。`app.api.schedule.solve` をモンキーパッチで
    例外送出するように差し替える。
    """
    with TestClient(create_app()) as client:
        project_id = _create_project_with_form_json(client)
        _save_response_for(
            project_id=project_id,
            sn=1,
            slots=[("2026-07-15", "16:00", "16:20")],
        )

        # API ハンドラが参照している solve 関数を例外送出に差し替え
        with patch(
            "app.api.schedule.solve",
            side_effect=RuntimeError("CP-SAT internal error"),
        ):
            resp = client.post(f"/api/projects/{project_id}/schedule")

    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# 8. solver_time_limit_seconds オプションの受領
# ---------------------------------------------------------------------------


def test_schedule_api_accepts_solver_time_limit_option(
    isolated_data_root: Path,
) -> None:
    """リクエストボディで `solver_time_limit_seconds` を渡せて、
    API ハンドラが scheduler.solve に伝達することを確認する。

    短いタイムリミット（5 秒）でも、小規模な問題（3 名 × 3 スロット）は
    十分に解けるはず。
    """
    with TestClient(create_app()) as client:
        project_id = _create_project_with_form_json(client)
        for sn in (1, 2, 3):
            _save_response_for(
                project_id=project_id,
                sn=sn,
                slots=[
                    ("2026-07-15", "16:00", "16:20"),
                    ("2026-07-15", "16:20", "16:40"),
                    ("2026-07-15", "16:40", "17:00"),
                ],
            )

        resp = client.post(
            f"/api/projects/{project_id}/schedule",
            json={"solver_time_limit_seconds": 5.0},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["assignments"]) == 3
