"""Phase 2.2: Google Form 作成サービス・API のテスト。

requirements.md §4.3 / §5.1、`docs/forms_api_research.md` §2 / §8 で確定した
**matrix 方式（QuestionGroupItem + Grid + CHECKBOX）**での Form 生成と
``form.json`` 永続化、二重作成防止、`forms.get` フォールバックを検証する。

実 Google API は呼ばず、以下をモックする:

- ``app.services.google_forms.google_auth.get_valid_credentials``：偽 Credentials を返す
- ``app.services.google_forms.build``：偽 service オブジェクトを返す。
  service.forms() は ``FakeFormsApi`` インスタンスを返し、
  ``create / batchUpdate / get`` チェーン呼び出しを記録する

テストは ``conftest.py`` の ``isolated_data_root`` フィクスチャ経由で
``%APPDATA%`` を汚さない。
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app


# ---------------------------------------------------------------------------
# 共通ヘルパ
# ---------------------------------------------------------------------------


def _sample_create_payload() -> dict:
    """Phase 2.1 で実装済みの POST /api/projects 用ペイロード（最小）。

    候補日 2 日 × 時間枠 2 枠 のシンプルなプロジェクトを作る。
    """
    return {
        "display_name": "3年A組 7月面談",
        "slot_minutes": 20,
        "candidate_dates": ["2026-07-15", "2026-07-16"],
        "candidate_time_slots": [
            {"start": "16:00", "end": "16:20"},
            {"start": "16:20", "end": "16:40"},
        ],
        "student_numbers": [1, 2, 3],
    }


class FakeFormsApi:
    """``service.forms()`` 配下のチェーン呼び出しを偽装するヘルパ。

    ``forms.create() / batchUpdate() / get()`` の各呼び出しを記録し、
    テストから検証できるようにする。各メソッドは ``execute()`` を持つオブジェクトを返す
    （google-api-python-client の HttpRequest 風）。
    """

    def __init__(
        self,
        *,
        create_response: dict | None = None,
        batch_response: dict | None = None,
        get_response: dict | None = None,
    ) -> None:
        # forms.create() のデフォルト応答
        self.create_response = create_response or {
            "formId": "FAKE_FORM_ID",
            "responderUri": (
                "https://docs.google.com/forms/d/FAKE_FORM_ID/viewform"
            ),
            "info": {"title": "3年A組 7月面談"},
        }
        # forms.batchUpdate() のデフォルト応答。
        # **matrix の questionId は空配列**にして「forms.get フォールバック」を誘発
        self.batch_response = batch_response or {
            "replies": [
                {"createItem": {"itemId": "ITEM_SN", "questionId": ["QID_SN"]}},
                {"createItem": {"itemId": "ITEM_MATRIX", "questionId": []}},
            ]
        }
        # forms.get() のデフォルト応答（フォールバック用に各行 questionId を含む）
        self.get_response = get_response or {
            "formId": "FAKE_FORM_ID",
            "responderUri": (
                "https://docs.google.com/forms/d/FAKE_FORM_ID/viewform"
            ),
            "info": {"title": "3年A組 7月面談"},
            "items": [
                {
                    "itemId": "ITEM_SN",
                    "title": "出席番号（半角数字）",
                    "questionItem": {
                        "question": {
                            "questionId": "QID_SN",
                            "required": True,
                            "textQuestion": {"paragraph": False},
                        }
                    },
                },
                {
                    "itemId": "ITEM_MATRIX",
                    "title": (
                        "参加可能な日時にチェックを入れてください（複数選択可）"
                    ),
                    "questionGroupItem": {
                        "grid": {
                            "columns": {
                                "type": "CHECKBOX",
                                "options": [
                                    {"value": "16:00-16:20"},
                                    {"value": "16:20-16:40"},
                                ],
                            }
                        },
                        "questions": [
                            {
                                "questionId": "QID_ROW_0",
                                "required": False,
                                "rowQuestion": {"title": "2026-07-15"},
                            },
                            {
                                "questionId": "QID_ROW_1",
                                "required": False,
                                "rowQuestion": {"title": "2026-07-16"},
                            },
                        ],
                    },
                },
            ],
        }

        # 呼び出し記録
        self.create_called_with: dict | None = None
        self.batch_update_called_with: dict | None = None
        self.get_called_count: int = 0
        self.get_called_with: str | None = None

    def create(self, *, body):  # noqa: ANN001
        self.create_called_with = body
        req = MagicMock()
        req.execute.return_value = self.create_response
        return req

    def batchUpdate(self, *, formId, body):  # noqa: ANN001, N803
        self.batch_update_called_with = {"formId": formId, "body": body}
        req = MagicMock()
        req.execute.return_value = self.batch_response
        return req

    def get(self, *, formId):  # noqa: ANN001, N803
        self.get_called_count += 1
        self.get_called_with = formId
        req = MagicMock()
        req.execute.return_value = self.get_response
        return req


def _make_service(fake_forms_api: FakeFormsApi) -> MagicMock:
    """``googleapiclient.discovery.build`` の偽戻り値を返す。"""
    service = MagicMock()
    service.forms.return_value = fake_forms_api
    return service


@pytest.fixture
def fake_creds() -> object:
    """ダミーの Credentials 相当オブジェクト。

    実 Google API へ通信させないため、型と中身は問わない。
    ``app.services.google_forms.build()`` の ``credentials`` 引数として
    そのまま渡されるが、本テストではモックされる。
    """
    return MagicMock(name="FakeCredentials")


def _create_project(client: TestClient) -> str:
    """テスト用プロジェクトを作成し ``project_id`` を返す。"""
    resp = client.post("/api/projects", json=_sample_create_payload())
    assert resp.status_code == 201, resp.text
    return resp.json()["project_id"]


# ---------------------------------------------------------------------------
# 1. batchUpdate に正しい構造（matrix + TextQuestion）が含まれる
# ---------------------------------------------------------------------------


def test_create_form_sends_correct_batch_update_requests(
    isolated_data_root: Path, fake_creds: object
) -> None:
    """POST /api/projects/{id}/form は

    - ``forms.create`` を ``info.title`` 付きで呼ぶ
    - ``forms.batchUpdate`` で 2 件の ``createItem`` を送る
        1. 出席番号 ``TextQuestion(paragraph=False)`` + ``required=True``
        2. matrix ``QuestionGroupItem`` + ``Grid(columns.type=CHECKBOX)``
    """
    fake_api = FakeFormsApi()

    with TestClient(create_app()) as client:
        project_id = _create_project(client)
        with (
            patch(
                "app.services.google_forms.google_auth.get_valid_credentials",
                return_value=fake_creds,
            ),
            patch(
                "app.services.google_forms.build",
                return_value=_make_service(fake_api),
            ),
        ):
            resp = client.post(f"/api/projects/{project_id}/form")

    assert resp.status_code in (200, 201), resp.text

    # forms.create: タイトルが渡されている
    assert fake_api.create_called_with is not None, "forms.create が呼ばれていない"
    info = fake_api.create_called_with.get("info") or {}
    assert info.get("title"), "info.title が空"

    # forms.batchUpdate: 2 件の createItem
    assert fake_api.batch_update_called_with is not None, (
        "forms.batchUpdate が呼ばれていない"
    )
    body = fake_api.batch_update_called_with["body"]
    requests = body["requests"]
    assert len(requests) == 2, (
        f"createItem は 2 件（TextQuestion + matrix）であるべき: {requests}"
    )

    # 1 件目: 出席番号 TextQuestion
    sn_req = requests[0]["createItem"]
    sn_question = sn_req["item"]["questionItem"]["question"]
    assert sn_question["required"] is True
    assert sn_question["textQuestion"]["paragraph"] is False

    # 2 件目: matrix（QuestionGroupItem + Grid + CHECKBOX）
    matrix_req = requests[1]["createItem"]
    qgi = matrix_req["item"]["questionGroupItem"]
    assert qgi["grid"]["columns"]["type"] == "CHECKBOX"


# ---------------------------------------------------------------------------
# 2. 候補日時枠（rows / columns）の形式が requirements.md §4 に準拠
# ---------------------------------------------------------------------------


def test_matrix_rows_and_columns_match_project_definition(
    isolated_data_root: Path, fake_creds: object
) -> None:
    """matrix の rows = 候補日（ISO 文字列）、columns = ``HH:MM-HH:MM`` ラベル。

    requirements.md §4.3「候補日 × 時間枠のチェックボックスマトリクス」と
    `forms_api_research.md` §2 のサンプル JSON に準拠する。
    """
    fake_api = FakeFormsApi()

    with TestClient(create_app()) as client:
        project_id = _create_project(client)
        with (
            patch(
                "app.services.google_forms.google_auth.get_valid_credentials",
                return_value=fake_creds,
            ),
            patch(
                "app.services.google_forms.build",
                return_value=_make_service(fake_api),
            ),
        ):
            client.post(f"/api/projects/{project_id}/form")

    matrix_req = fake_api.batch_update_called_with["body"]["requests"][1]
    qgi = matrix_req["createItem"]["item"]["questionGroupItem"]

    # columns: 時間枠ラベルが HH:MM-HH:MM 形式で順序通り
    column_values = [c["value"] for c in qgi["grid"]["columns"]["options"]]
    assert column_values == ["16:00-16:20", "16:20-16:40"]

    # rows: 候補日が ISO 文字列で順序通り、各 row は required=False
    # （0 枠の日を許容するため。すべての日が空でも回答送信可能）
    questions = qgi["questions"]
    row_titles = [q["rowQuestion"]["title"] for q in questions]
    assert row_titles == ["2026-07-15", "2026-07-16"]
    for q in questions:
        assert q["required"] is False, "0 枠の日を許容するため各行は required=False"


# ---------------------------------------------------------------------------
# 3. forms.get フォールバック：batchUpdate 応答に行 questionId が無い場合
# ---------------------------------------------------------------------------


def test_forms_get_called_to_resolve_row_question_ids(
    isolated_data_root: Path, fake_creds: object
) -> None:
    """matrix の行 questionId が batchUpdate 応答に含まれない場合、
    ``forms.get`` を呼び出して各行の questionId を解決し、
    ``row_question_id_by_date`` を組み立て ``form.json`` に保存する。

    （`docs/forms_api_research.md` §8 リスク表に明記された防御的実装）
    """
    fake_api = FakeFormsApi()  # default: matrix questionId は空配列

    with TestClient(create_app()) as client:
        project_id = _create_project(client)
        with (
            patch(
                "app.services.google_forms.google_auth.get_valid_credentials",
                return_value=fake_creds,
            ),
            patch(
                "app.services.google_forms.build",
                return_value=_make_service(fake_api),
            ),
        ):
            resp = client.post(f"/api/projects/{project_id}/form")
    assert resp.status_code in (200, 201), resp.text

    # forms.get が呼ばれている
    assert fake_api.get_called_count >= 1, (
        "matrix 行 questionId が batchUpdate に無い場合、forms.get で読み直すべき"
    )
    assert fake_api.get_called_with == "FAKE_FORM_ID"

    # form.json の row_question_id_by_date が forms.get 応答から構築される
    settings = get_settings()
    form_json_path = settings.projects_dir / project_id / "form.json"
    assert form_json_path.is_file()
    saved = json.loads(form_json_path.read_text(encoding="utf-8"))
    assert saved["row_question_id_by_date"] == {
        "2026-07-15": "QID_ROW_0",
        "2026-07-16": "QID_ROW_1",
    }


# ---------------------------------------------------------------------------
# 4. batchUpdate 応答に行 questionId が含まれている場合は forms.get を省略
# ---------------------------------------------------------------------------


def test_forms_get_skipped_when_batch_response_includes_row_question_ids(
    isolated_data_root: Path, fake_creds: object
) -> None:
    """batchUpdate 応答の ``createItem.questionId[]`` に matrix 行 ID が
    全て含まれていれば、追加の ``forms.get`` 呼び出しは不要。

    （フォールバック判断のもう一方の分岐。タスク指示の
    「もし `batchUpdate` レスポンスに直接 row questionId が含まれていた場合は
    `forms.get` 呼び出しを省略しても良い」に対応）
    """
    fake_api = FakeFormsApi(
        batch_response={
            "replies": [
                {"createItem": {"itemId": "ITEM_SN", "questionId": ["QID_SN"]}},
                {
                    "createItem": {
                        "itemId": "ITEM_MATRIX",
                        "questionId": ["QID_ROW_A", "QID_ROW_B"],
                    }
                },
            ]
        }
    )

    with TestClient(create_app()) as client:
        project_id = _create_project(client)
        with (
            patch(
                "app.services.google_forms.google_auth.get_valid_credentials",
                return_value=fake_creds,
            ),
            patch(
                "app.services.google_forms.build",
                return_value=_make_service(fake_api),
            ),
        ):
            client.post(f"/api/projects/{project_id}/form")

    # forms.get は呼ばれない
    assert fake_api.get_called_count == 0, (
        "batchUpdate に行 questionId が揃っていれば forms.get は不要"
    )

    settings = get_settings()
    saved = json.loads(
        (settings.projects_dir / project_id / "form.json").read_text(
            encoding="utf-8"
        )
    )
    # batchUpdate 応答から（候補日順に）マッピングが組まれる
    assert saved["row_question_id_by_date"] == {
        "2026-07-15": "QID_ROW_A",
        "2026-07-16": "QID_ROW_B",
    }


# ---------------------------------------------------------------------------
# 5. form.json に formId, responderUri, editUri, row_question_id_by_date を保存
# ---------------------------------------------------------------------------


def test_form_json_persisted_with_required_fields(
    isolated_data_root: Path, fake_creds: object
) -> None:
    """``<project_dir>/form.json`` に以下を保存する：

    - ``formId`` (Forms API レスポンス)
    - ``responderUri`` (同上)
    - ``editUri`` (formId から構築。Forms API は直接返さない)
    - ``student_number_question_id``
    - ``row_question_id_by_date``
    """
    fake_api = FakeFormsApi()

    with TestClient(create_app()) as client:
        project_id = _create_project(client)
        with (
            patch(
                "app.services.google_forms.google_auth.get_valid_credentials",
                return_value=fake_creds,
            ),
            patch(
                "app.services.google_forms.build",
                return_value=_make_service(fake_api),
            ),
        ):
            resp = client.post(f"/api/projects/{project_id}/form")
    assert resp.status_code in (200, 201), resp.text

    settings = get_settings()
    form_json_path = settings.projects_dir / project_id / "form.json"
    assert form_json_path.is_file()
    saved = json.loads(form_json_path.read_text(encoding="utf-8"))

    assert saved["formId"] == "FAKE_FORM_ID"
    assert (
        saved["responderUri"]
        == "https://docs.google.com/forms/d/FAKE_FORM_ID/viewform"
    )
    # editUri は Forms API が返さないため、本サービスが formId から構築する
    assert "FAKE_FORM_ID" in saved["editUri"]
    assert "/edit" in saved["editUri"]

    assert saved["student_number_question_id"] == "QID_SN"
    assert saved["row_question_id_by_date"]
    assert set(saved["row_question_id_by_date"].keys()) == {
        "2026-07-15",
        "2026-07-16",
    }


# ---------------------------------------------------------------------------
# 6. 二重作成防止：既存 form.json で再呼び出し → 409 / Google API は呼ばない
# ---------------------------------------------------------------------------


def test_create_form_twice_returns_409_conflict(
    isolated_data_root: Path, fake_creds: object
) -> None:
    """同じ project_id に対し 2 度目の POST /form は 409 Conflict を返し、
    Google API（``forms.create`` 等）は再度呼ばれない。
    """
    fake_api_1 = FakeFormsApi()

    with TestClient(create_app()) as client:
        project_id = _create_project(client)
        with (
            patch(
                "app.services.google_forms.google_auth.get_valid_credentials",
                return_value=fake_creds,
            ),
            patch(
                "app.services.google_forms.build",
                return_value=_make_service(fake_api_1),
            ),
        ):
            first = client.post(f"/api/projects/{project_id}/form")
            assert first.status_code in (200, 201), first.text

        # 2 度目は別の FakeFormsApi に差し替えて、API が呼ばれていないことを検証
        fake_api_2 = FakeFormsApi()
        with (
            patch(
                "app.services.google_forms.google_auth.get_valid_credentials",
                return_value=fake_creds,
            ),
            patch(
                "app.services.google_forms.build",
                return_value=_make_service(fake_api_2),
            ),
        ):
            second = client.post(f"/api/projects/{project_id}/form")

    assert second.status_code == 409
    assert fake_api_2.create_called_with is None, (
        "二重作成防止に該当した場合、Google API は呼ばれてはならない"
    )
    assert fake_api_2.batch_update_called_with is None
    assert fake_api_2.get_called_count == 0


# ---------------------------------------------------------------------------
# 7. GET /api/projects/{id}/form：form.json が無ければ 404、あれば 200 + info
# ---------------------------------------------------------------------------


def test_get_form_returns_404_when_not_created(
    isolated_data_root: Path,
) -> None:
    """form.json が未作成のプロジェクトに対する GET は 404 を返す。"""
    with TestClient(create_app()) as client:
        project_id = _create_project(client)
        resp = client.get(f"/api/projects/{project_id}/form")
    assert resp.status_code == 404


def test_get_form_returns_form_info_when_created(
    isolated_data_root: Path, fake_creds: object
) -> None:
    """form.json があるプロジェクトに対する GET は 200 + form 情報を返す。"""
    fake_api = FakeFormsApi()
    with TestClient(create_app()) as client:
        project_id = _create_project(client)
        with (
            patch(
                "app.services.google_forms.google_auth.get_valid_credentials",
                return_value=fake_creds,
            ),
            patch(
                "app.services.google_forms.build",
                return_value=_make_service(fake_api),
            ),
        ):
            client.post(f"/api/projects/{project_id}/form")

        resp = client.get(f"/api/projects/{project_id}/form")

    assert resp.status_code == 200
    body = resp.json()
    assert body["formId"] == "FAKE_FORM_ID"
    assert "responderUri" in body
    assert "editUri" in body
    assert body["row_question_id_by_date"]
    assert body["student_number_question_id"] == "QID_SN"
