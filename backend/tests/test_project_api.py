"""Phase 2.1: プロジェクト管理 API のテスト。

requirements.md §3.1 / §3.2 / §6 および implementation_prompts_subdivided.md
Phase 2.1 §テスト駆動 に従い、以下を検証する。

1. POST /api/projects がプロジェクトディレクトリと project.json と
   サブディレクトリ（responses/, drafts/, output/）と rules.json を生成する
2. GET /api/projects が作成日時降順で一覧を返す
3. GET /api/projects/{id} がプロジェクト詳細を正しいスキーマで返す
4. PUT /api/projects/{id} がプロジェクトメタを更新する
5. DELETE /api/projects/{id} がディレクトリごと削除する
6. 必須項目欠落で 422 / 存在しない id で 404 を返す（バリデーション）

テストは ``conftest.py`` の ``isolated_data_root`` フィクスチャを通じて
``%APPDATA%`` を汚さない（Phase 1.1 引き継ぎ事項）。

本フェーズの RED 段階では ``FileProjectRepository`` の各メソッドが
``NotImplementedError`` を投げる/API ルータが未登録のため、
全テストが失敗する想定。
"""

from __future__ import annotations

import json
import time as _time
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app


def _client() -> TestClient:
    """TestClient を生成するヘルパ。"""
    return TestClient(create_app())


def _minimal_create_payload(display_name: str = "3年A組 7月面談") -> dict:
    """最小限のプロジェクト作成リクエストペイロード。

    requirements.md §3.2 の project.json スキーマに準拠。
    project_id と created_at と status はサーバ側で採番・既定値を入れる想定。
    """
    return {
        "display_name": display_name,
        "slot_minutes": 20,
        "candidate_dates": ["2026-07-15", "2026-07-16"],
        "candidate_time_slots": [
            {"start": "16:00", "end": "16:20"},
            {"start": "16:20", "end": "16:40"},
        ],
        "student_numbers": [1, 2, 3, 4, 5],
    }


# ---------------------------------------------------------------------------
# 1. 作成API：ディレクトリ・project.json・サブディレクトリ・rules.json を生成
# ---------------------------------------------------------------------------


def test_create_project_creates_directory_and_files(isolated_data_root: Path) -> None:
    """POST /api/projects が完全なプロジェクト構造を作る。

    - <projects_dir>/<project_id>/ ディレクトリ
    - project.json
    - responses/ サブディレクトリ
    - drafts/ サブディレクトリ
    - output/ サブディレクトリ
    - rules.json
    """
    with _client() as client:
        resp = client.post("/api/projects", json=_minimal_create_payload())
    assert resp.status_code == 201, resp.text

    body = resp.json()
    assert "project_id" in body and body["project_id"]
    assert "created_at" in body and body["created_at"]
    assert body["display_name"] == "3年A組 7月面談"
    assert body["status"] == "in_progress"
    assert body["slot_minutes"] == 20
    assert body["candidate_dates"] == ["2026-07-15", "2026-07-16"]
    assert body["student_numbers"] == [1, 2, 3, 4, 5]

    project_id = body["project_id"]
    settings = get_settings()
    project_dir = settings.projects_dir / project_id

    # ディレクトリ存在
    assert project_dir.is_dir()
    assert (project_dir / "responses").is_dir()
    assert (project_dir / "drafts").is_dir()
    assert (project_dir / "output").is_dir()

    # project.json
    project_json_path = project_dir / "project.json"
    assert project_json_path.is_file()
    saved = json.loads(project_json_path.read_text(encoding="utf-8"))
    assert saved["project_id"] == project_id
    assert saved["display_name"] == "3年A組 7月面談"

    # rules.json（デフォルト rules）
    rules_json_path = project_dir / "rules.json"
    assert rules_json_path.is_file()
    rules = json.loads(rules_json_path.read_text(encoding="utf-8"))
    assert "global_constraints" in rules
    assert "student_constraints" in rules
    assert rules["student_constraints"] == []
    # teacher_unavailable は空リストで初期化される
    assert rules["global_constraints"]["teacher_unavailable"] == []


# ---------------------------------------------------------------------------
# 2. 一覧API：作成日時降順
# ---------------------------------------------------------------------------


def test_list_projects_returns_created_at_descending_order(
    isolated_data_root: Path,
) -> None:
    """GET /api/projects が作成日時降順で返す。

    複数プロジェクトを連続作成し、最後に作成したものが先頭にくることを確認。
    """
    with _client() as client:
        ids = []
        for i, name in enumerate(["最初", "二番目", "三番目"]):
            resp = client.post(
                "/api/projects",
                json=_minimal_create_payload(display_name=name),
            )
            assert resp.status_code == 201, resp.text
            ids.append(resp.json()["project_id"])
            # created_at の解像度がマイクロ秒未満で衝突しないよう微小スリープ
            _time.sleep(0.01)

        list_resp = client.get("/api/projects")
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert isinstance(items, list)
    assert len(items) == 3
    # 作成日時降順 = 後に作成したものが先頭
    returned_names = [it["display_name"] for it in items]
    assert returned_names == ["三番目", "二番目", "最初"]


# ---------------------------------------------------------------------------
# 3. 詳細API：正しいスキーマで返す
# ---------------------------------------------------------------------------


def test_get_project_returns_correct_schema(isolated_data_root: Path) -> None:
    """GET /api/projects/{id} が requirements.md §3.2 のスキーマを返す。"""
    with _client() as client:
        create_resp = client.post(
            "/api/projects", json=_minimal_create_payload("詳細取得テスト")
        )
        assert create_resp.status_code == 201
        project_id = create_resp.json()["project_id"]

        get_resp = client.get(f"/api/projects/{project_id}")
    assert get_resp.status_code == 200
    body = get_resp.json()

    # requirements.md §3.2 project.json の必須キー
    expected_keys = {
        "project_id",
        "display_name",
        "created_at",
        "status",
        "slot_minutes",
        "candidate_dates",
        "candidate_time_slots",
        "student_numbers",
    }
    assert expected_keys.issubset(set(body.keys()))
    assert body["project_id"] == project_id
    assert body["display_name"] == "詳細取得テスト"
    assert body["status"] in {"in_progress", "draft_saved", "finalized"}
    # candidate_time_slots は dict のリスト
    assert isinstance(body["candidate_time_slots"], list)
    assert all("start" in s and "end" in s for s in body["candidate_time_slots"])


# ---------------------------------------------------------------------------
# 4. 更新API：変更が反映される
# ---------------------------------------------------------------------------


def test_update_project_persists_changes(isolated_data_root: Path) -> None:
    """PUT /api/projects/{id} がメタ情報を更新する。"""
    with _client() as client:
        create_resp = client.post(
            "/api/projects", json=_minimal_create_payload("旧名称")
        )
        assert create_resp.status_code == 201
        project_id = create_resp.json()["project_id"]
        original_created_at = create_resp.json()["created_at"]

        update_payload = {
            "display_name": "新名称",
            "slot_minutes": 30,
            "candidate_dates": ["2026-08-01"],
            "candidate_time_slots": [{"start": "17:00", "end": "17:30"}],
            "student_numbers": [10, 11, 12],
            "status": "draft_saved",
        }
        put_resp = client.put(
            f"/api/projects/{project_id}", json=update_payload
        )
        assert put_resp.status_code == 200, put_resp.text
        updated = put_resp.json()
        assert updated["display_name"] == "新名称"
        assert updated["slot_minutes"] == 30
        assert updated["status"] == "draft_saved"
        assert updated["student_numbers"] == [10, 11, 12]
        # project_id と created_at は不変
        assert updated["project_id"] == project_id
        assert updated["created_at"] == original_created_at

        # 再取得して永続化を確認
        get_resp = client.get(f"/api/projects/{project_id}")
    assert get_resp.status_code == 200
    persisted = get_resp.json()
    assert persisted["display_name"] == "新名称"
    assert persisted["slot_minutes"] == 30


# ---------------------------------------------------------------------------
# 5. 削除API：ディレクトリごと削除
# ---------------------------------------------------------------------------


def test_delete_project_removes_directory(isolated_data_root: Path) -> None:
    """DELETE /api/projects/{id} がディレクトリと配下を全て削除する。"""
    with _client() as client:
        create_resp = client.post(
            "/api/projects", json=_minimal_create_payload("削除テスト")
        )
        assert create_resp.status_code == 201
        project_id = create_resp.json()["project_id"]

        settings = get_settings()
        project_dir = settings.projects_dir / project_id
        # 削除前は存在
        assert project_dir.is_dir()
        assert (project_dir / "project.json").is_file()
        # 削除前にサブディレクトリ内にダミーファイルを置いても消えること
        (project_dir / "responses" / "dummy.txt").write_text(
            "dummy", encoding="utf-8"
        )

        del_resp = client.delete(f"/api/projects/{project_id}")
    assert del_resp.status_code in (200, 204), del_resp.text

    # 削除後はディレクトリごと消滅
    assert not project_dir.exists()

    # その後の GET は 404
    with _client() as client:
        get_resp = client.get(f"/api/projects/{project_id}")
    assert get_resp.status_code == 404


# ---------------------------------------------------------------------------
# 6. バリデーション：必須項目欠落 → 422、存在しない id → 404
# ---------------------------------------------------------------------------


def test_create_project_missing_required_returns_422(
    isolated_data_root: Path,
) -> None:
    """display_name 欠落で 422（FastAPI 標準のバリデーションエラー）。"""
    bad_payload = {
        # display_name を欠落
        "slot_minutes": 20,
        "candidate_dates": [],
        "candidate_time_slots": [],
        "student_numbers": [],
    }
    with _client() as client:
        resp = client.post("/api/projects", json=bad_payload)
    assert resp.status_code == 422


def test_get_nonexistent_project_returns_404(isolated_data_root: Path) -> None:
    """存在しない project_id を GET すると 404。"""
    with _client() as client:
        resp = client.get("/api/projects/does-not-exist-xxxx")
    assert resp.status_code == 404


def test_update_nonexistent_project_returns_404(
    isolated_data_root: Path,
) -> None:
    """存在しない project_id を PUT すると 404。"""
    update_payload = {
        "display_name": "新名称",
        "slot_minutes": 30,
        "candidate_dates": ["2026-08-01"],
        "candidate_time_slots": [{"start": "17:00", "end": "17:30"}],
        "student_numbers": [1],
        "status": "in_progress",
    }
    with _client() as client:
        resp = client.put(
            "/api/projects/does-not-exist-xxxx", json=update_payload
        )
    assert resp.status_code == 404


def test_delete_nonexistent_project_returns_404(
    isolated_data_root: Path,
) -> None:
    """存在しない project_id を DELETE すると 404。"""
    with _client() as client:
        resp = client.delete("/api/projects/does-not-exist-xxxx")
    assert resp.status_code == 404
