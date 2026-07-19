"""Phase 3.4: ドラフト保存・ロック管理 API のテスト。

requirements.md §3.2 / §4.7-4.9 / §6 および
implementation_prompts_subdivided.md Phase 3.4 §テストケース に従い、
以下を検証する。

1. ドラフト保存と取得（往復一致）
2. save → latest 取得で最新が返る（複数保存 → 最新のみ）
3. unlock 後の再保存が可能
4. status 遷移の正当性（不正遷移は拒否）
5. 並行保存のシリアライズ（同時 save が破綻しないこと）
6. 不存在プロジェクト → 404

テストは ``conftest.py`` の ``isolated_data_root`` フィクスチャを通じて
``%APPDATA%`` を汚さない（Phase 1.1 引き継ぎ事項）。

RED 段階では ``FileDraftRepository`` の各メソッドが ``NotImplementedError`` を
投げる / API ルータが未登録のため、全テストが失敗する想定。
"""

from __future__ import annotations

import threading
import time as _time
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from app.repositories.file_repository import FileDraftRepository


# ---------------------------------------------------------------------------
# ヘルパ / フィクスチャ
# ---------------------------------------------------------------------------

def _client() -> TestClient:
    """TestClient を生成するヘルパ。"""
    return TestClient(create_app())


def _minimal_create_payload(display_name: str = "テスト面談") -> dict:
    """最小限のプロジェクト作成リクエストペイロード。"""
    return {
        "display_name": display_name,
        "slot_minutes": 20,
        "candidate_dates": ["2026-07-15"],
        "candidate_time_slots": [
            {"start": "16:00", "end": "16:20"},
            {"start": "16:20", "end": "16:40"},
        ],
        "student_numbers": [1, 2, 3],
    }


def _draft_save_payload(
    *,
    assignments: list[dict] | None = None,
    unassigned_students: list[int] | None = None,
    violated_constraints: list[str] | None = None,
    locked_students: list[int] | None = None,
) -> dict:
    """ドラフト保存リクエストペイロード。"""
    return {
        "assignments": assignments or [
            {"student_number": 1, "date": "2026-07-15", "start": "16:00", "end": "16:20"},
            {"student_number": 2, "date": "2026-07-15", "start": "16:20", "end": "16:40"},
        ],
        "unassigned_students": unassigned_students or [3],
        "violated_constraints": violated_constraints or [],
        "locked_students": locked_students if locked_students is not None else [],
    }


@pytest.fixture
def client() -> TestClient:
    """TestClient フィクスチャ。"""
    return _client()


@pytest.fixture
def project_id(client: TestClient) -> str:
    """テスト用プロジェクトを作成して project_id を返す。"""
    resp = client.post("/api/projects", json=_minimal_create_payload())
    assert resp.status_code == 201, f"プロジェクト作成失敗: {resp.text}"
    return resp.json()["project_id"]


# ---------------------------------------------------------------------------
# 1. ドラフト保存 - 基本
# ---------------------------------------------------------------------------


class TestSaveDraft:
    """POST /api/projects/{id}/drafts のテスト。"""

    def test_save_draft_returns_201_with_locked_true(
        self, client: TestClient, project_id: str
    ) -> None:
        """ドラフト保存が 201 を返し、locked=True が設定される。"""
        payload = _draft_save_payload()
        resp = client.post(f"/api/projects/{project_id}/drafts", json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert body["locked"] is True
        assert body["project_id"] == project_id

    def test_save_draft_response_contains_all_fields(
        self, client: TestClient, project_id: str
    ) -> None:
        """保存レスポンスが Draft の全フィールドを持つ（往復一致）。"""
        payload = _draft_save_payload(
            assignments=[
                {"student_number": 1, "date": "2026-07-15", "start": "16:00", "end": "16:20"}
            ],
            unassigned_students=[5],
            violated_constraints=["生徒5は候補日時がありません"],
        )
        resp = client.post(f"/api/projects/{project_id}/drafts", json=payload)
        assert resp.status_code == 201
        body = resp.json()
        # Pydantic v2 は time を "HH:MM:SS" 形式でシリアライズする
        assert body["assignments"] == [
            {"student_number": 1, "date": "2026-07-15", "start": "16:00:00", "end": "16:20:00"}
        ]
        assert body["unassigned_students"] == [5]
        assert body["violated_constraints"] == ["生徒5は候補日時がありません"]

    def test_save_draft_persists_locked_students(
        self, client: TestClient, project_id: str
    ) -> None:
        """locked_students が保存・往復で保持される。"""
        payload = _draft_save_payload(locked_students=[1, 2])
        resp = client.post(f"/api/projects/{project_id}/drafts", json=payload)
        assert resp.status_code == 201
        assert resp.json()["locked_students"] == [1, 2]

        latest = client.get(f"/api/projects/{project_id}/drafts/latest")
        assert latest.json()["locked_students"] == [1, 2]

    def test_save_draft_locked_students_defaults_to_empty(
        self, client: TestClient, project_id: str
    ) -> None:
        """locked_students を省略した場合は空リストになる。"""
        payload = _draft_save_payload()
        del payload["locked_students"]
        resp = client.post(f"/api/projects/{project_id}/drafts", json=payload)
        assert resp.status_code == 201
        assert resp.json()["locked_students"] == []

    def test_save_draft_transitions_status_to_draft_saved(
        self, client: TestClient, project_id: str
    ) -> None:
        """ドラフト保存後にプロジェクトの status が draft_saved になる。"""
        payload = _draft_save_payload()
        client.post(f"/api/projects/{project_id}/drafts", json=payload)
        project_resp = client.get(f"/api/projects/{project_id}")
        assert project_resp.status_code == 200
        assert project_resp.json()["status"] == "draft_saved"

    def test_save_draft_when_status_draft_saved_returns_409(
        self, client: TestClient, project_id: str
    ) -> None:
        """status=draft_saved の状態で再保存しようとすると 409 を返す（ロック解除必要）。"""
        payload = _draft_save_payload()
        # 1回目は成功
        resp1 = client.post(f"/api/projects/{project_id}/drafts", json=payload)
        assert resp1.status_code == 201
        # 2回目はアンロックせずに保存 → 409
        resp2 = client.post(f"/api/projects/{project_id}/drafts", json=payload)
        assert resp2.status_code == 409

    def test_save_draft_project_not_found_returns_404(
        self, client: TestClient
    ) -> None:
        """存在しないプロジェクトへの保存で 404 を返す。"""
        resp = client.post(
            "/api/projects/nonexistent_project_id/drafts",
            json=_draft_save_payload(),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 2. 最新ドラフト取得
# ---------------------------------------------------------------------------


class TestGetLatestDraft:
    """GET /api/projects/{id}/drafts/latest のテスト。"""

    def test_get_latest_returns_saved_draft(
        self, client: TestClient, project_id: str
    ) -> None:
        """保存後に GET latest で同じデータが取得できる（往復一致）。"""
        payload = _draft_save_payload(
            assignments=[
                {"student_number": 1, "date": "2026-07-15", "start": "16:00", "end": "16:20"}
            ]
        )
        client.post(f"/api/projects/{project_id}/drafts", json=payload)
        resp = client.get(f"/api/projects/{project_id}/drafts/latest")
        assert resp.status_code == 200
        body = resp.json()
        assert body["locked"] is True
        # Pydantic v2 は time を "HH:MM:SS" 形式でシリアライズする
        assert body["assignments"] == [
            {"student_number": 1, "date": "2026-07-15", "start": "16:00:00", "end": "16:20:00"}
        ]

    def test_get_latest_returns_newest_after_multiple_saves(
        self, client: TestClient, project_id: str
    ) -> None:
        """複数保存後、最新のものが返される。"""
        # 1回目保存
        payload1 = _draft_save_payload(
            assignments=[
                {"student_number": 1, "date": "2026-07-15", "start": "16:00", "end": "16:20"}
            ]
        )
        client.post(f"/api/projects/{project_id}/drafts", json=payload1)

        # アンロック → 再保存
        client.post(f"/api/projects/{project_id}/drafts/unlock")

        payload2 = _draft_save_payload(
            assignments=[
                {"student_number": 2, "date": "2026-07-15", "start": "16:00", "end": "16:20"}
            ]
        )
        # 少し待って saved_at に差をつける（ファイル名のタイムスタンプ衝突を防ぐ）
        _time.sleep(0.01)
        client.post(f"/api/projects/{project_id}/drafts", json=payload2)

        # latest は2回目（student_number=2）のはず
        resp = client.get(f"/api/projects/{project_id}/drafts/latest")
        assert resp.status_code == 200
        body = resp.json()
        assert body["assignments"][0]["student_number"] == 2

    def test_get_latest_no_draft_returns_404(
        self, client: TestClient, project_id: str
    ) -> None:
        """ドラフトが1件もない場合 404 を返す。"""
        resp = client.get(f"/api/projects/{project_id}/drafts/latest")
        assert resp.status_code == 404

    def test_get_latest_project_not_found_returns_404(
        self, client: TestClient
    ) -> None:
        """存在しないプロジェクトへのアクセスで 404 を返す。"""
        resp = client.get("/api/projects/nonexistent_project_id/drafts/latest")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 3. アンロック
# ---------------------------------------------------------------------------


class TestUnlockDraft:
    """POST /api/projects/{id}/drafts/unlock のテスト。"""

    def test_unlock_sets_locked_false(
        self, client: TestClient, project_id: str
    ) -> None:
        """アンロックにより latest の locked が False になる。"""
        client.post(f"/api/projects/{project_id}/drafts", json=_draft_save_payload())
        resp = client.post(f"/api/projects/{project_id}/drafts/unlock")
        assert resp.status_code == 200
        assert resp.json()["locked"] is False

    def test_unlock_transitions_status_to_in_progress(
        self, client: TestClient, project_id: str
    ) -> None:
        """アンロック後にプロジェクトの status が in_progress に戻る。"""
        client.post(f"/api/projects/{project_id}/drafts", json=_draft_save_payload())
        client.post(f"/api/projects/{project_id}/drafts/unlock")
        project_resp = client.get(f"/api/projects/{project_id}")
        assert project_resp.json()["status"] == "in_progress"

    def test_unlock_no_draft_returns_404(
        self, client: TestClient, project_id: str
    ) -> None:
        """ドラフトが1件もない場合アンロック要求で 404 を返す。"""
        resp = client.post(f"/api/projects/{project_id}/drafts/unlock")
        assert resp.status_code == 404

    def test_unlock_project_not_found_returns_404(
        self, client: TestClient
    ) -> None:
        """存在しないプロジェクトへのアンロックで 404 を返す。"""
        resp = client.post("/api/projects/nonexistent_project_id/drafts/unlock")
        assert resp.status_code == 404

    def test_unlock_get_latest_shows_unlocked(
        self, client: TestClient, project_id: str
    ) -> None:
        """アンロック後 GET latest でも locked=False が返る。"""
        client.post(f"/api/projects/{project_id}/drafts", json=_draft_save_payload())
        client.post(f"/api/projects/{project_id}/drafts/unlock")
        resp = client.get(f"/api/projects/{project_id}/drafts/latest")
        assert resp.status_code == 200
        assert resp.json()["locked"] is False


# ---------------------------------------------------------------------------
# 4. アンロック後の再保存フロー
# ---------------------------------------------------------------------------


class TestResaveAfterUnlock:
    """save → unlock → re-save のフローが正常に動作することを検証する。"""

    def test_resave_after_unlock_succeeds(
        self, client: TestClient, project_id: str
    ) -> None:
        """アンロック後に再保存が成功する（201 を返す）。"""
        client.post(f"/api/projects/{project_id}/drafts", json=_draft_save_payload())
        client.post(f"/api/projects/{project_id}/drafts/unlock")
        resp = client.post(f"/api/projects/{project_id}/drafts", json=_draft_save_payload())
        assert resp.status_code == 201

    def test_resave_after_unlock_status_becomes_draft_saved_again(
        self, client: TestClient, project_id: str
    ) -> None:
        """アンロック後の再保存でプロジェクト status が draft_saved に再遷移する。"""
        client.post(f"/api/projects/{project_id}/drafts", json=_draft_save_payload())
        client.post(f"/api/projects/{project_id}/drafts/unlock")
        client.post(f"/api/projects/{project_id}/drafts", json=_draft_save_payload())
        project_resp = client.get(f"/api/projects/{project_id}")
        assert project_resp.json()["status"] == "draft_saved"


# ---------------------------------------------------------------------------
# 5. 並行保存のシリアライズ（同時 save が破綻しないこと）
# ---------------------------------------------------------------------------


class TestConcurrentSaves:
    """並行保存が破綻しないことを検証する。"""

    def test_concurrent_saves_to_different_projects_do_not_corrupt(
        self,
    ) -> None:
        """複数プロジェクトへの並行 save が JSON 破損を引き起こさない。

        TestClient での HTTP 並行テストは複雑なため、
        ``FileDraftRepository.save_draft()`` を直接複数スレッドから呼び出す。

        ``isolated_data_root`` (conftest.py autouse) により、get_settings() は
        テスト用一時ディレクトリを指す Settings を返す。
        """
        from app.config import get_settings
        from app.models.draft import Assignment, Draft
        import datetime as _dt

        settings = get_settings()
        settings.ensure_directories()
        repo = FileDraftRepository(settings)

        errors: list[str] = []
        threads_done: list[int] = []

        num_projects = 5
        num_saves_per_project = 4

        def save_many(project_id: str) -> None:
            # プロジェクトディレクトリを作成
            (settings.projects_dir / project_id / "drafts").mkdir(
                parents=True, exist_ok=True
            )
            for i in range(num_saves_per_project):
                draft = Draft(
                    project_id=project_id,
                    saved_at=_dt.datetime(2026, 7, 15, 12, 0, i, tzinfo=_dt.timezone.utc),
                    locked=True,
                    assignments=[
                        Assignment(
                            student_number=i + 1,
                            date=_dt.date(2026, 7, 15),
                            start=_dt.time(16, 0),
                            end=_dt.time(16, 20),
                        )
                    ],
                    unassigned_students=[],
                    violated_constraints=[],
                )
                try:
                    repo.save_draft(project_id, draft)
                except Exception as exc:
                    errors.append(f"{project_id}/{i}: {exc}")
            threads_done.append(1)

        project_ids = [f"proj_{n:03d}" for n in range(num_projects)]
        threads = [
            threading.Thread(target=save_many, args=(pid,))
            for pid in project_ids
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"並行保存でエラー: {errors}"
        assert len(threads_done) == num_projects

        # 各プロジェクトの全ドラフトが有効な JSON であることを確認
        import json

        for pid in project_ids:
            drafts_dir = settings.projects_dir / pid / "drafts"
            files = list(drafts_dir.glob("draft_*.json"))
            assert len(files) == num_saves_per_project, (
                f"{pid}: {len(files)} files, expected {num_saves_per_project}"
            )
            for f in files:
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    assert "project_id" in data
                except Exception as exc:
                    errors.append(f"{pid}/{f.name}: {exc}")

        assert not errors, f"ドラフトファイルに破損あり: {errors}"

    def test_concurrent_saves_to_same_project_produce_valid_files(
        self,
    ) -> None:
        """同一プロジェクトへの並行 save がいずれも有効な JSON を生成する。

        ``isolated_data_root`` (conftest.py autouse) により、get_settings() は
        テスト用一時ディレクトリを指す Settings を返す。
        """
        from app.config import get_settings
        from app.models.draft import Assignment, Draft
        import datetime as _dt
        import json

        settings = get_settings()
        settings.ensure_directories()
        repo = FileDraftRepository(settings)

        project_id = "concurrent_proj"
        (settings.projects_dir / project_id / "drafts").mkdir(
            parents=True, exist_ok=True
        )

        errors: list[str] = []
        num_threads = 8

        def save_one(idx: int) -> None:
            draft = Draft(
                project_id=project_id,
                saved_at=_dt.datetime(2026, 7, 15, 12, 0, idx, tzinfo=_dt.timezone.utc),
                locked=True,
                assignments=[
                    Assignment(
                        student_number=idx + 1,
                        date=_dt.date(2026, 7, 15),
                        start=_dt.time(16, 0),
                        end=_dt.time(16, 20),
                    )
                ],
                unassigned_students=[],
                violated_constraints=[],
            )
            try:
                repo.save_draft(project_id, draft)
            except Exception as exc:
                errors.append(f"thread {idx}: {exc}")

        threads = [threading.Thread(target=save_one, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"並行保存でエラー: {errors}"

        drafts_dir = settings.projects_dir / project_id / "drafts"
        files = list(drafts_dir.glob("draft_*.json"))
        assert len(files) == num_threads, f"期待 {num_threads} ファイル、実際 {len(files)}"
        for f in files:
            data = json.loads(f.read_text(encoding="utf-8"))
            assert "project_id" in data
