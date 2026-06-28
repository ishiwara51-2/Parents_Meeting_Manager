"""Phase 3.1: ルール管理 API のテスト。

requirements.md §3.2 (rules.json スキーマ) / §4.5 (ルール設定) /
§4.6.2 (制約分類) / §6 (API設計) に基づく。

TDD 順序:
    1. このファイルを作成（テストケース追加）
    2. pytest が失敗することを確認（RED）
    3. test(phase3.1): add rules api test cases (RED) でコミット
    4. 実装してテストを通す（GREEN）
    5. feat(phase3.1): implement rules api (GREEN) でコミット

テストケース:
    1. グローバルルール初期化（初回 GET で既定値が返る）
    2. グローバルルール更新の永続化
    3. プロジェクト作成時のグローバルルールコピー
    4. プロジェクトルール更新がグローバルに伝播しない（独立性）
    5. 重み範囲外バリデーション（weight > 10 および weight < 0）
    6. 不正な制約タイプバリデーション
    7. プロジェクトルール GET/PUT 基本動作
    8. 存在しないプロジェクトへのルール操作は 404
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


def _client() -> TestClient:
    """TestClient を生成するヘルパ。"""
    return TestClient(create_app())


def _minimal_project_payload(display_name: str = "テスト面談") -> dict:
    """最小限のプロジェクト作成リクエストペイロード。"""
    return {
        "display_name": display_name,
        "slot_minutes": 20,
        "candidate_dates": ["2026-07-15"],
        "candidate_time_slots": [{"start": "16:00", "end": "16:20"}],
        "student_numbers": [1, 2, 3],
    }


def _valid_rules_payload(max_consecutive: int = 3) -> dict:
    """有効なルールペイロード。"""
    return {
        "global_constraints": {
            "max_consecutive_slots": max_consecutive,
            "forced_break_slots": 1,
            "max_slots_per_day": 10,
            "teacher_unavailable": [],
        },
        "student_constraints": [],
    }


# ---------------------------------------------------------------------------
# 1. グローバルルール初期化：初回 GET で既定値が返る
# ---------------------------------------------------------------------------


def test_get_global_rules_returns_defaults(isolated_data_root: Path) -> None:
    """GET /api/global-rules で既定値のルールが返る。

    global_rules.json が存在しない状態でも 200 を返し、
    requirements.md §3.2 の ``global_constraints`` 構造を持つこと。
    """
    with _client() as client:
        resp = client.get("/api/global-rules")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "global_constraints" in body
    assert "student_constraints" in body
    gc = body["global_constraints"]
    # requirements.md §3.2 の必須フィールド
    assert "max_consecutive_slots" in gc
    assert "forced_break_slots" in gc
    assert "max_slots_per_day" in gc
    assert "teacher_unavailable" in gc
    assert isinstance(body["student_constraints"], list)


# ---------------------------------------------------------------------------
# 2. グローバルルール更新の永続化
# ---------------------------------------------------------------------------


def test_put_global_rules_persists(isolated_data_root: Path) -> None:
    """PUT /api/global-rules で更新後、GET で同じ値が返ること（永続化確認）。"""
    new_rules = {
        "global_constraints": {
            "max_consecutive_slots": 3,
            "forced_break_slots": 2,
            "max_slots_per_day": 8,
            "teacher_unavailable": [
                {"date": "2026-07-16", "start": "18:00", "end": "19:00"}
            ],
        },
        "student_constraints": [
            {"type": "pairing", "student_numbers": [5, 12], "weight": 8},
        ],
    }
    with _client() as client:
        put_resp = client.put("/api/global-rules", json=new_rules)
        assert put_resp.status_code == 200, put_resp.text
        put_body = put_resp.json()
        assert put_body["global_constraints"]["max_consecutive_slots"] == 3
        assert put_body["global_constraints"]["forced_break_slots"] == 2
        assert len(put_body["student_constraints"]) == 1

        # 再取得して永続化確認
        get_resp = client.get("/api/global-rules")

    assert get_resp.status_code == 200
    get_body = get_resp.json()
    assert get_body["global_constraints"]["max_consecutive_slots"] == 3
    assert get_body["global_constraints"]["forced_break_slots"] == 2
    assert len(get_body["global_constraints"]["teacher_unavailable"]) == 1
    assert get_body["global_constraints"]["teacher_unavailable"][0]["date"] == "2026-07-16"
    assert len(get_body["student_constraints"]) == 1
    assert get_body["student_constraints"][0]["type"] == "pairing"
    assert get_body["student_constraints"][0]["weight"] == 8


# ---------------------------------------------------------------------------
# 3. プロジェクト作成時のグローバルルールコピー
# ---------------------------------------------------------------------------


def test_project_creation_copies_global_rules(isolated_data_root: Path) -> None:
    """グローバルルールを変更後にプロジェクトを作成すると、
    プロジェクトルールにグローバルルールがコピーされる（requirements.md §4.5.1）。
    """
    custom_rules = {
        "global_constraints": {
            "max_consecutive_slots": 2,
            "forced_break_slots": 1,
            "max_slots_per_day": 6,
            "teacher_unavailable": [],
        },
        "student_constraints": [
            {"type": "pairing", "student_numbers": [1, 2], "weight": 5},
        ],
    }
    with _client() as client:
        # グローバルルールを更新
        put_resp = client.put("/api/global-rules", json=custom_rules)
        assert put_resp.status_code == 200, put_resp.text

        # プロジェクト作成
        create_resp = client.post("/api/projects", json=_minimal_project_payload())
        assert create_resp.status_code == 201, create_resp.text
        project_id = create_resp.json()["project_id"]

        # プロジェクトルールを取得
        rules_resp = client.get(f"/api/projects/{project_id}/rules")

    assert rules_resp.status_code == 200, rules_resp.text
    project_rules = rules_resp.json()
    # グローバルルールがコピーされていること
    assert project_rules["global_constraints"]["max_consecutive_slots"] == 2
    assert project_rules["global_constraints"]["max_slots_per_day"] == 6
    assert len(project_rules["student_constraints"]) == 1
    assert project_rules["student_constraints"][0]["type"] == "pairing"


# ---------------------------------------------------------------------------
# 4. プロジェクトルール更新がグローバルに伝播しない（独立性）
# ---------------------------------------------------------------------------


def test_project_rules_independent_from_global(isolated_data_root: Path) -> None:
    """プロジェクトルールを変更しても、グローバルルールは変わらない。

    requirements.md §4.5.2「グローバルルールを複製した状態から開始」であり、
    プロジェクトルールとグローバルルールは独立して管理される。
    """
    with _client() as client:
        # グローバルルールを明示的に設定
        global_rules = _valid_rules_payload(max_consecutive=4)
        client.put("/api/global-rules", json=global_rules)

        # プロジェクト作成
        create_resp = client.post("/api/projects", json=_minimal_project_payload())
        assert create_resp.status_code == 201
        project_id = create_resp.json()["project_id"]

        # プロジェクトルールを異なる値で更新
        modified_project_rules = _valid_rules_payload(max_consecutive=9)
        proj_put_resp = client.put(
            f"/api/projects/{project_id}/rules", json=modified_project_rules
        )
        assert proj_put_resp.status_code == 200, proj_put_resp.text

        # グローバルルールを再取得
        global_resp = client.get("/api/global-rules")

    assert global_resp.status_code == 200
    global_body = global_resp.json()
    # グローバルルールは変わっていない（4 のまま）
    assert global_body["global_constraints"]["max_consecutive_slots"] == 4


# ---------------------------------------------------------------------------
# 5. 重み範囲外バリデーション
# ---------------------------------------------------------------------------


def test_put_global_rules_weight_too_large_returns_422(isolated_data_root: Path) -> None:
    """weight > 10（上限超過）で PUT すると 422 が返る（requirements.md §4.5.2 重み 0〜10）。"""
    invalid_rules = {
        "global_constraints": {
            "max_consecutive_slots": 3,
            "forced_break_slots": 1,
            "max_slots_per_day": 10,
            "teacher_unavailable": [],
        },
        "student_constraints": [
            {"type": "pairing", "student_numbers": [1, 2], "weight": 11},  # 上限超過
        ],
    }
    with _client() as client:
        resp = client.put("/api/global-rules", json=invalid_rules)
    assert resp.status_code == 422


def test_put_global_rules_negative_weight_returns_422(isolated_data_root: Path) -> None:
    """weight < 0（下限未満）で PUT すると 422 が返る（requirements.md §4.5.2 重み 0〜10）。"""
    invalid_rules = {
        "global_constraints": {
            "max_consecutive_slots": 3,
            "forced_break_slots": 1,
            "max_slots_per_day": 10,
            "teacher_unavailable": [],
        },
        "student_constraints": [
            {"type": "pairing", "student_numbers": [1, 2], "weight": -1},  # 下限未満
        ],
    }
    with _client() as client:
        resp = client.put("/api/global-rules", json=invalid_rules)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 6. 不正な制約タイプバリデーション
# ---------------------------------------------------------------------------


def test_put_global_rules_invalid_constraint_type_returns_422(isolated_data_root: Path) -> None:
    """存在しない ``type`` で PUT すると 422 が返る。

    discriminated union の ``type`` に登録外の値を渡した場合、
    Pydantic が ValidationError を送出し FastAPI が 422 を返す。
    """
    invalid_rules = {
        "global_constraints": {
            "max_consecutive_slots": 3,
            "forced_break_slots": 1,
            "max_slots_per_day": 10,
            "teacher_unavailable": [],
        },
        "student_constraints": [
            {"type": "unknown_constraint_xyz", "student_number": 1, "weight": 5},
        ],
    }
    with _client() as client:
        resp = client.put("/api/global-rules", json=invalid_rules)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 7. プロジェクトルール GET/PUT 基本動作
# ---------------------------------------------------------------------------


def test_get_project_rules_returns_rules(isolated_data_root: Path) -> None:
    """GET /api/projects/{id}/rules がルールを返す。"""
    with _client() as client:
        create_resp = client.post("/api/projects", json=_minimal_project_payload())
        assert create_resp.status_code == 201
        project_id = create_resp.json()["project_id"]

        rules_resp = client.get(f"/api/projects/{project_id}/rules")

    assert rules_resp.status_code == 200, rules_resp.text
    body = rules_resp.json()
    assert "global_constraints" in body
    assert "student_constraints" in body


def test_put_project_rules_persists(isolated_data_root: Path) -> None:
    """PUT /api/projects/{id}/rules で更新後、GET で同じ値が返る（永続化確認）。"""
    with _client() as client:
        create_resp = client.post("/api/projects", json=_minimal_project_payload())
        assert create_resp.status_code == 201
        project_id = create_resp.json()["project_id"]

        new_rules = {
            "global_constraints": {
                "max_consecutive_slots": 2,
                "forced_break_slots": 0,
                "max_slots_per_day": 5,
                "teacher_unavailable": [],
            },
            "student_constraints": [
                {
                    "type": "avoid_time",
                    "student_number": 3,
                    "avoid_after": "18:00",
                    "weight": 7,
                }
            ],
        }
        put_resp = client.put(f"/api/projects/{project_id}/rules", json=new_rules)
        assert put_resp.status_code == 200, put_resp.text

        get_resp = client.get(f"/api/projects/{project_id}/rules")

    assert get_resp.status_code == 200
    body = get_resp.json()
    assert body["global_constraints"]["max_consecutive_slots"] == 2
    assert body["global_constraints"]["max_slots_per_day"] == 5
    assert len(body["student_constraints"]) == 1
    assert body["student_constraints"][0]["type"] == "avoid_time"
    assert body["student_constraints"][0]["weight"] == 7


def test_put_project_rules_with_all_constraint_types(isolated_data_root: Path) -> None:
    """PUT でサポートされている全制約タイプを含むルールを保存・復元できる。"""
    with _client() as client:
        create_resp = client.post("/api/projects", json=_minimal_project_payload())
        assert create_resp.status_code == 201
        project_id = create_resp.json()["project_id"]

        # requirements.md §3.2 のサンプルに近い制約セット
        all_constraints_rules = {
            "global_constraints": {
                "max_consecutive_slots": 3,
                "forced_break_slots": 1,
                "max_slots_per_day": 10,
                "teacher_unavailable": [
                    {"date": "2026-07-16", "start": "18:00", "end": "19:00"}
                ],
            },
            "student_constraints": [
                {"type": "pairing", "student_numbers": [5, 12], "weight": 8},
                {"type": "avoid_time", "student_number": 7, "avoid_after": "18:00", "weight": 5},
                {"type": "prefer_time", "student_number": 3, "prefer_before": "17:00", "weight": 5},
                {"type": "duration_multiplier", "student_number": 9, "multiplier": 2},
            ],
        }
        put_resp = client.put(
            f"/api/projects/{project_id}/rules", json=all_constraints_rules
        )
        assert put_resp.status_code == 200, put_resp.text

        get_resp = client.get(f"/api/projects/{project_id}/rules")

    assert get_resp.status_code == 200
    body = get_resp.json()
    assert len(body["student_constraints"]) == 4
    types = [c["type"] for c in body["student_constraints"]]
    assert "pairing" in types
    assert "avoid_time" in types
    assert "prefer_time" in types
    assert "duration_multiplier" in types


# ---------------------------------------------------------------------------
# 8. 存在しないプロジェクトへのルール操作は 404
# ---------------------------------------------------------------------------


def test_get_project_rules_nonexistent_project_returns_404(isolated_data_root: Path) -> None:
    """存在しない project_id のルール GET は 404。"""
    with _client() as client:
        resp = client.get("/api/projects/nonexistent-project-id/rules")
    assert resp.status_code == 404


def test_put_project_rules_nonexistent_project_returns_404(isolated_data_root: Path) -> None:
    """存在しない project_id のルール PUT は 404。"""
    with _client() as client:
        resp = client.put(
            "/api/projects/nonexistent-project-id/rules",
            json=_valid_rules_payload(),
        )
    assert resp.status_code == 404
