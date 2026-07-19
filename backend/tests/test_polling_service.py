"""Phase 2.3: 回答ポーリング・パースサービスのテスト。

requirements.md §4.4 / §5.2、`docs/forms_api_research.md` §4 / §5 / §6 / §8、
`docs/handoff_phase2_0.md` / `docs/handoff_phase2_2.md` で確定した

- 全件取得 + 集合差分による未取得 ``responseId`` 検出（順序非依存）
- matrix 行 questionId による ``availability`` 組み立て
- ``int(value.strip())`` による出席番号バリデーション（失敗時スキップ + ログ）
- 429 / 503 受領時の truncated exponential backoff リトライ

を検証する。実 Google API は呼ばず、``app.services.polling`` 内の
``build`` / ``google_auth.get_valid_credentials`` / ``time.sleep`` を
``unittest.mock.patch`` で差し替える。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import httplib2
import pytest
from fastapi.testclient import TestClient
from googleapiclient.errors import HttpError

from app.config import get_settings
from app.main import create_app
from app.models.form import FormInfo
from app.models.project import Project, TimeSlot
from app.repositories.file_repository import FileProjectRepository


# ---------------------------------------------------------------------------
# 共通フィクスチャ・ヘルパ
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
        "student_numbers": [1, 2, 3],
    }


def _create_project_and_form_json(
    client: TestClient, *, with_select_all_row: bool = False
) -> str:
    """テスト用プロジェクトを作成し、`form.json` を直接ディスクに置く。

    Form 作成 API はモックが大変なので、本テストでは ``FileProjectRepository.save_form_info``
    を直接呼び出して `form.json` を保存しておく（Phase 2.2 で動作確認済み）。

    ``with_select_all_row=True`` の場合、matrix 末尾の「すべての日」一括選択行
    （questionId=``QID_ROW_ALL``）を ``form.json`` に含める。
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
        row_question_id_by_date={
            "2026-07-15": "QID_ROW_0",
            "2026-07-16": "QID_ROW_1",
        },
        time_slot_labels=["16:00-16:20", "16:20-16:40"],
        select_all_dates_row_question_id="QID_ROW_ALL" if with_select_all_row else None,
    )
    repo.save_form_info(project_id, form_info)
    return project_id


def _make_form_response(
    *,
    response_id: str,
    student_number: str = "1",
    submitted_at: str = "2026-06-28T15:30:12.000Z",
    row0_slots: list[str] | None = None,
    row1_slots: list[str] | None = None,
    row_all_slots: list[str] | None = None,
) -> dict[str, Any]:
    """Forms API の ``forms.responses.list`` 風レスポンス1件を組み立てる。

    `forms_api_research.md` §4 の構造に準拠：

    - ``answers[<qid>].textAnswers.answers[]`` に ``{value: ...}`` が並ぶ
    - CHECKBOX 行は複数値、TextQuestion は 1 値

    ``row_all_slots`` は matrix 末尾の「すべての日」一括選択行
    （questionId=``QID_ROW_ALL``）への回答。
    """
    answers: dict[str, Any] = {
        "QID_SN": {
            "questionId": "QID_SN",
            "textAnswers": {"answers": [{"value": student_number}]},
        },
        "QID_ROW_0": {
            "questionId": "QID_ROW_0",
            "textAnswers": {
                "answers": [{"value": v} for v in (row0_slots or [])]
            },
        },
        "QID_ROW_1": {
            "questionId": "QID_ROW_1",
            "textAnswers": {
                "answers": [{"value": v} for v in (row1_slots or [])]
            },
        },
    }
    if row_all_slots is not None:
        answers["QID_ROW_ALL"] = {
            "questionId": "QID_ROW_ALL",
            "textAnswers": {"answers": [{"value": v} for v in row_all_slots]},
        }
    return {
        "formId": "FAKE_FORM_ID",
        "responseId": response_id,
        "createTime": submitted_at,
        "lastSubmittedTime": submitted_at,
        "answers": answers,
    }


def _make_http_error(
    status_code: int,
    *,
    retry_after: str | None = None,
    content: bytes = b'{"error":{"message":"mocked"}}',
) -> HttpError:
    """googleapiclient.errors.HttpError を組み立てる（リトライ系テスト用）。"""
    headers: dict[str, str] = {"status": str(status_code)}
    if retry_after is not None:
        headers["retry-after"] = retry_after
    resp = httplib2.Response(headers)
    return HttpError(resp=resp, content=content)


class _FakeResponsesResource:
    """``service.forms().responses()`` の偽実装。

    ``execute_side_effects`` に与えた各要素を ``list().execute()`` の戻り値として
    順次返す。HttpError インスタンスを与えた場合はそれを送出する。
    """

    def __init__(self, execute_side_effects: list[object]) -> None:
        self._side_effects = list(execute_side_effects)
        self.list_calls: list[dict[str, Any]] = []

    def list(self, **kwargs: Any) -> Any:  # noqa: D401
        self.list_calls.append(kwargs)
        req = MagicMock()
        # MagicMock.side_effect が exception を含めばそれを送出、辞書なら return する
        # 1呼び出し1要素を消費したいので pop 形式
        if not self._side_effects:
            req.execute.return_value = {"responses": []}
        else:
            item = self._side_effects.pop(0)

            def _execute(_item=item):  # type: ignore[no-untyped-def]
                if isinstance(_item, Exception):
                    raise _item
                return _item

            req.execute.side_effect = _execute
        return req


def _make_service_with_responses(resp_resource: _FakeResponsesResource) -> MagicMock:
    """``app.services.polling.build`` の偽戻り値（service）を返す。

    service.forms().responses() → 与えた _FakeResponsesResource を返す。
    """
    service = MagicMock()
    forms_api = MagicMock()
    forms_api.responses.return_value = resp_resource
    service.forms.return_value = forms_api
    return service


@pytest.fixture
def fake_creds() -> object:
    return MagicMock(name="FakeCredentials")


# ---------------------------------------------------------------------------
# 1. 新規回答のみ保存（既知 responseId は重複保存しない）
# ---------------------------------------------------------------------------


def test_sync_responses_saves_only_new_responses(
    isolated_data_root: Path, fake_creds: object
) -> None:
    """既に保存済みの responseId は再保存しない。新規分のみ書き出す。"""
    from app.services import polling

    # 1 回目: 2 件保存
    resp_resource_1 = _FakeResponsesResource(
        [
            {
                "responses": [
                    _make_form_response(
                        response_id="R1",
                        student_number="1",
                        row0_slots=["16:00-16:20"],
                    ),
                    _make_form_response(
                        response_id="R2",
                        student_number="2",
                        row1_slots=["16:20-16:40"],
                    ),
                ]
            }
        ]
    )

    with TestClient(create_app()) as client:
        project_id = _create_project_and_form_json(client)

        with (
            patch(
                "app.services.polling.google_auth.get_valid_credentials",
                return_value=fake_creds,
            ),
            patch(
                "app.services.polling.build",
                return_value=_make_service_with_responses(resp_resource_1),
            ),
            patch("app.services.polling.time.sleep"),
        ):
            result_1 = polling.sync_responses(project_id)

        assert result_1["new_count"] == 2

        # 2 回目: 既存 R1 / R2 + 新規 R3
        resp_resource_2 = _FakeResponsesResource(
            [
                {
                    "responses": [
                        _make_form_response(
                            response_id="R1",
                            student_number="1",
                            row0_slots=["16:00-16:20"],
                        ),
                        _make_form_response(
                            response_id="R2",
                            student_number="2",
                            row1_slots=["16:20-16:40"],
                        ),
                        _make_form_response(
                            response_id="R3",
                            student_number="3",
                            row0_slots=["16:20-16:40"],
                        ),
                    ]
                }
            ]
        )
        with (
            patch(
                "app.services.polling.google_auth.get_valid_credentials",
                return_value=fake_creds,
            ),
            patch(
                "app.services.polling.build",
                return_value=_make_service_with_responses(resp_resource_2),
            ),
            patch("app.services.polling.time.sleep"),
        ):
            result_2 = polling.sync_responses(project_id)

    assert result_2["new_count"] == 1, "新規 R3 のみ保存されるべき"

    # ディスク上のファイル数：sn=1, sn=2 が 1 件ずつ、sn=3 が 1 件
    settings = get_settings()
    responses_dir = settings.projects_dir / project_id / "responses"
    sn1 = list((responses_dir / "1").glob("*.json"))
    sn2 = list((responses_dir / "2").glob("*.json"))
    sn3 = list((responses_dir / "3").glob("*.json"))
    assert len(sn1) == 1
    assert len(sn2) == 1
    assert len(sn3) == 1


# ---------------------------------------------------------------------------
# 2. 同一出席番号からの複数回答が別ファイル保存
# ---------------------------------------------------------------------------


def test_sync_responses_same_student_multiple_submissions_separate_files(
    isolated_data_root: Path, fake_creds: object
) -> None:
    """同一生徒（出席番号同じ）の 2 回答（response_id 違い）は別ファイルとして併存する。

    requirements.md §4.4 「同一出席番号から複数回答があった場合、すべて別ファイルとして保存」
    """
    from app.services import polling

    resp_resource = _FakeResponsesResource(
        [
            {
                "responses": [
                    _make_form_response(
                        response_id="R1",
                        student_number="1",
                        submitted_at="2026-06-28T10:00:00.000Z",
                        row0_slots=["16:00-16:20"],
                    ),
                    _make_form_response(
                        response_id="R2",
                        student_number="1",
                        submitted_at="2026-06-28T11:00:00.000Z",
                        row0_slots=["16:20-16:40"],
                    ),
                ]
            }
        ]
    )

    with TestClient(create_app()) as client:
        project_id = _create_project_and_form_json(client)
        with (
            patch(
                "app.services.polling.google_auth.get_valid_credentials",
                return_value=fake_creds,
            ),
            patch(
                "app.services.polling.build",
                return_value=_make_service_with_responses(resp_resource),
            ),
            patch("app.services.polling.time.sleep"),
        ):
            result = polling.sync_responses(project_id)

    assert result["new_count"] == 2

    settings = get_settings()
    sn1_dir = settings.projects_dir / project_id / "responses" / "1"
    files = sorted(sn1_dir.glob("*.json"))
    assert len(files) == 2, (
        "同一生徒の 2 回答は別ファイルとして併存すべき: "
        f"{[f.name for f in files]}"
    )


# ---------------------------------------------------------------------------
# 3. 順序非依存：レスポンスが新→古でも古→新でも集合差分で動作
# ---------------------------------------------------------------------------


def test_sync_responses_order_independent_set_diff(
    isolated_data_root: Path, fake_creds: object
) -> None:
    """`forms.responses.list` の並び順（昇順/降順）に依存せず、
    既知 ``responseId`` 集合との差分で新規を抽出する。

    (Phase 2.2 引き継ぎ：「matrix の textAnswers.answers[] の順序は保護者が
    チェックした順になる可能性があり、順序に依存しない実装が必要」)
    """
    from app.services import polling

    # 1 回目で R1 のみ保存
    resp_resource_1 = _FakeResponsesResource(
        [
            {
                "responses": [
                    _make_form_response(
                        response_id="R1",
                        student_number="1",
                        row0_slots=["16:00-16:20"],
                    ),
                ]
            }
        ]
    )

    with TestClient(create_app()) as client:
        project_id = _create_project_and_form_json(client)
        with (
            patch(
                "app.services.polling.google_auth.get_valid_credentials",
                return_value=fake_creds,
            ),
            patch(
                "app.services.polling.build",
                return_value=_make_service_with_responses(resp_resource_1),
            ),
            patch("app.services.polling.time.sleep"),
        ):
            polling.sync_responses(project_id)

        # 2 回目：API が【新→古】の順で R3, R2, R1 を返す
        # （R1 は既存。本来の昇順想定と逆だが、新規 R3 / R2 が漏れず保存されることを検証）
        resp_resource_2 = _FakeResponsesResource(
            [
                {
                    "responses": [
                        _make_form_response(
                            response_id="R3",
                            student_number="3",
                            submitted_at="2026-06-28T13:00:00.000Z",
                            row0_slots=["16:00-16:20"],
                        ),
                        _make_form_response(
                            response_id="R2",
                            student_number="2",
                            submitted_at="2026-06-28T12:00:00.000Z",
                            row1_slots=["16:20-16:40"],
                        ),
                        _make_form_response(
                            response_id="R1",
                            student_number="1",
                            submitted_at="2026-06-28T11:00:00.000Z",
                            row0_slots=["16:00-16:20"],
                        ),
                    ]
                }
            ]
        )
        with (
            patch(
                "app.services.polling.google_auth.get_valid_credentials",
                return_value=fake_creds,
            ),
            patch(
                "app.services.polling.build",
                return_value=_make_service_with_responses(resp_resource_2),
            ),
            patch("app.services.polling.time.sleep"),
        ):
            result_2 = polling.sync_responses(project_id)

    assert result_2["new_count"] == 2, "新規 R2 と R3 のみ保存（順序非依存）"

    settings = get_settings()
    responses_dir = settings.projects_dir / project_id / "responses"
    # sn=2 と sn=3 のディレクトリにそれぞれ 1 件
    assert len(list((responses_dir / "2").glob("*.json"))) == 1
    assert len(list((responses_dir / "3").glob("*.json"))) == 1
    # sn=1 はそのまま 1 件
    assert len(list((responses_dir / "1").glob("*.json"))) == 1


# ---------------------------------------------------------------------------
# 4. matrix 回答のパース（form.json の row_question_id_by_date 経由）
# ---------------------------------------------------------------------------


def test_sync_responses_parses_matrix_via_row_question_id_map(
    isolated_data_root: Path, fake_creds: object
) -> None:
    """form.json の ``row_question_id_by_date`` を使い、各行 questionId に対する
    複数選択回答をパースして ``availability`` を組み立てる。

    `forms_api_research.md` §4 のパース疑似コードに準拠：
        - 行 = 候補日
        - 列 = 時間枠ラベル（``HH:MM-HH:MM``）を ``"-"`` で分解して start/end
    """
    from app.services import polling

    resp_resource = _FakeResponsesResource(
        [
            {
                "responses": [
                    _make_form_response(
                        response_id="R1",
                        student_number="1",
                        # 行 0（2026-07-15）に 2 つの時間枠選択
                        row0_slots=["16:00-16:20", "16:20-16:40"],
                        # 行 1（2026-07-16）に 1 つの時間枠選択
                        row1_slots=["16:20-16:40"],
                    ),
                ]
            }
        ]
    )

    with TestClient(create_app()) as client:
        project_id = _create_project_and_form_json(client)
        with (
            patch(
                "app.services.polling.google_auth.get_valid_credentials",
                return_value=fake_creds,
            ),
            patch(
                "app.services.polling.build",
                return_value=_make_service_with_responses(resp_resource),
            ),
            patch("app.services.polling.time.sleep"),
        ):
            polling.sync_responses(project_id)

    settings = get_settings()
    sn1_dir = settings.projects_dir / project_id / "responses" / "1"
    saved_files = list(sn1_dir.glob("*.json"))
    assert len(saved_files) == 1
    saved = json.loads(saved_files[0].read_text(encoding="utf-8"))

    assert saved["student_number"] == 1
    assert saved["google_form_response_id"] == "R1"

    availability = saved["availability"]
    # 期待：2026-07-15 から 2 枠、2026-07-16 から 1 枠（合計 3）
    assert len(availability) == 3
    # 順序は内部実装に依存しないように、集合化で比較
    triples = {(a["date"], a["start"], a["end"]) for a in availability}
    assert triples == {
        ("2026-07-15", "16:00:00", "16:20:00"),
        ("2026-07-15", "16:20:00", "16:40:00"),
        ("2026-07-16", "16:20:00", "16:40:00"),
    }


# ---------------------------------------------------------------------------
# 4b. 「終日」列の一括選択：その日のすべての時間枠へ展開される
# ---------------------------------------------------------------------------


def test_sync_responses_expands_select_all_times_column(
    isolated_data_root: Path, fake_creds: object
) -> None:
    """行（候補日）の「終日（すべての時間帯）」列がチェックされた場合、
    その日の個別チェックの有無にかかわらず、その日の全時間枠が
    availability に展開される。
    """
    from app.services import polling
    from app.services.google_forms import SELECT_ALL_TIMES_COLUMN_LABEL

    resp_resource = _FakeResponsesResource(
        [
            {
                "responses": [
                    _make_form_response(
                        response_id="R1",
                        student_number="1",
                        # 2026-07-15: 「終日」のみチェック（個別枠は未チェック）
                        row0_slots=[SELECT_ALL_TIMES_COLUMN_LABEL],
                        # 2026-07-16: 通常どおり 1 枠のみ選択
                        row1_slots=["16:20-16:40"],
                    ),
                ]
            }
        ]
    )

    with TestClient(create_app()) as client:
        project_id = _create_project_and_form_json(client)
        with (
            patch(
                "app.services.polling.google_auth.get_valid_credentials",
                return_value=fake_creds,
            ),
            patch(
                "app.services.polling.build",
                return_value=_make_service_with_responses(resp_resource),
            ),
            patch("app.services.polling.time.sleep"),
        ):
            polling.sync_responses(project_id)

    settings = get_settings()
    sn1_dir = settings.projects_dir / project_id / "responses" / "1"
    saved = json.loads(next(sn1_dir.glob("*.json")).read_text(encoding="utf-8"))

    triples = {(a["date"], a["start"], a["end"]) for a in saved["availability"]}
    assert triples == {
        # 「終日」展開により 2026-07-15 は 2 枠とも選択されたことになる
        ("2026-07-15", "16:00:00", "16:20:00"),
        ("2026-07-15", "16:20:00", "16:40:00"),
        ("2026-07-16", "16:20:00", "16:40:00"),
    }


# ---------------------------------------------------------------------------
# 4c. 「すべての日」行の一括選択：チェックした時間枠が全候補日へ展開される
# ---------------------------------------------------------------------------


def test_sync_responses_expands_select_all_dates_row(
    isolated_data_root: Path, fake_creds: object
) -> None:
    """matrix 末尾の「すべての日」行でチェックした時間枠は、
    各候補日の個別選択と統合（和集合）されて availability に展開される。
    """
    from app.services import polling

    resp_resource = _FakeResponsesResource(
        [
            {
                "responses": [
                    _make_form_response(
                        response_id="R1",
                        student_number="1",
                        # 2026-07-15 は個別に 1 枠だけ選択済み
                        row0_slots=["16:00-16:20"],
                        row1_slots=[],
                        # 「すべての日」行で 16:20-16:40 をチェック
                        # → 2026-07-15 / 2026-07-16 の両方に適用される
                        row_all_slots=["16:20-16:40"],
                    ),
                ]
            }
        ]
    )

    with TestClient(create_app()) as client:
        project_id = _create_project_and_form_json(
            client, with_select_all_row=True
        )
        with (
            patch(
                "app.services.polling.google_auth.get_valid_credentials",
                return_value=fake_creds,
            ),
            patch(
                "app.services.polling.build",
                return_value=_make_service_with_responses(resp_resource),
            ),
            patch("app.services.polling.time.sleep"),
        ):
            polling.sync_responses(project_id)

    settings = get_settings()
    sn1_dir = settings.projects_dir / project_id / "responses" / "1"
    saved = json.loads(next(sn1_dir.glob("*.json")).read_text(encoding="utf-8"))

    triples = {(a["date"], a["start"], a["end"]) for a in saved["availability"]}
    assert triples == {
        # 2026-07-15: 個別選択（16:00-16:20）+「すべての日」展開（16:20-16:40）
        ("2026-07-15", "16:00:00", "16:20:00"),
        ("2026-07-15", "16:20:00", "16:40:00"),
        # 2026-07-16: 「すべての日」展開のみ
        ("2026-07-16", "16:20:00", "16:40:00"),
    }


# ---------------------------------------------------------------------------
# 5. 整数バリデーション失敗時のスキップ（不正な出席番号は保存しない）
# ---------------------------------------------------------------------------


def test_sync_responses_skips_invalid_student_number(
    isolated_data_root: Path, fake_creds: object
) -> None:
    """出席番号が ``int(...)`` でパースできない値（文字列・空白等）の場合、
    その回答は保存せずスキップし、結果サマリの ``skipped_count`` をカウントアップする。

    `forms_api_research.md` §5 採用方針：「失敗時はその回答を保存しない + 警告ログ」
    """
    from app.services import polling

    resp_resource = _FakeResponsesResource(
        [
            {
                "responses": [
                    _make_form_response(
                        response_id="R_BAD",
                        student_number="abc",  # ★整数パース不可
                        row0_slots=["16:00-16:20"],
                    ),
                    _make_form_response(
                        response_id="R_OK",
                        student_number="2",
                        row0_slots=["16:00-16:20"],
                    ),
                ]
            }
        ]
    )

    with TestClient(create_app()) as client:
        project_id = _create_project_and_form_json(client)
        with (
            patch(
                "app.services.polling.google_auth.get_valid_credentials",
                return_value=fake_creds,
            ),
            patch(
                "app.services.polling.build",
                return_value=_make_service_with_responses(resp_resource),
            ),
            patch("app.services.polling.time.sleep"),
        ):
            result = polling.sync_responses(project_id)

    assert result["new_count"] == 1, "正常な R_OK のみ保存"
    assert result["skipped_count"] == 1, "不正な R_BAD はスキップカウントへ"

    settings = get_settings()
    responses_dir = settings.projects_dir / project_id / "responses"
    # 不正回答に対応するディレクトリ（"abc/" など）は作られていない
    assert not (responses_dir / "abc").exists()
    # 正常な sn=2 のディレクトリには 1 ファイル
    assert len(list((responses_dir / "2").glob("*.json"))) == 1


# ---------------------------------------------------------------------------
# 6. 429 でリトライが行われ、最終的に成功する
# ---------------------------------------------------------------------------


def test_sync_responses_retries_on_429_then_succeeds(
    isolated_data_root: Path, fake_creds: object
) -> None:
    """``forms.responses.list().execute()`` が 429 を 2 回投げてから成功した場合、
    リトライにより最終的に成功し、回答が保存される。

    `forms_api_research.md` §6 採用方針：「truncated exponential backoff
    （最低 1 回はリトライ）」
    """
    from app.services import polling

    success_payload = {
        "responses": [
            _make_form_response(
                response_id="R1",
                student_number="1",
                row0_slots=["16:00-16:20"],
            ),
        ]
    }
    resp_resource = _FakeResponsesResource(
        [
            _make_http_error(429),
            _make_http_error(429, retry_after="1"),
            success_payload,
        ]
    )

    with TestClient(create_app()) as client:
        project_id = _create_project_and_form_json(client)
        with (
            patch(
                "app.services.polling.google_auth.get_valid_credentials",
                return_value=fake_creds,
            ),
            patch(
                "app.services.polling.build",
                return_value=_make_service_with_responses(resp_resource),
            ),
            patch("app.services.polling.time.sleep") as sleep_mock,
        ):
            result = polling.sync_responses(project_id)

    assert result["new_count"] == 1
    # list は 3 回呼ばれる（2 回 429 + 1 回成功）
    assert len(resp_resource.list_calls) == 3
    # 少なくとも 2 回 sleep が呼ばれている（429 のたびに）
    assert sleep_mock.call_count >= 2


# ---------------------------------------------------------------------------
# 7. 429 が継続してリトライ全消費した場合に例外を上げる
# ---------------------------------------------------------------------------


def test_sync_responses_raises_after_max_429_retries(
    isolated_data_root: Path, fake_creds: object
) -> None:
    """429 がリトライ回数を超えて続いた場合、例外を上げる（API 層で 503 等に変換）。"""
    from app.services import polling

    # 4 回連続で 429（最大リトライ数 3 を超える）
    resp_resource = _FakeResponsesResource(
        [
            _make_http_error(429),
            _make_http_error(429),
            _make_http_error(429),
            _make_http_error(429),
        ]
    )

    with TestClient(create_app()) as client:
        project_id = _create_project_and_form_json(client)
        with (
            patch(
                "app.services.polling.google_auth.get_valid_credentials",
                return_value=fake_creds,
            ),
            patch(
                "app.services.polling.build",
                return_value=_make_service_with_responses(resp_resource),
            ),
            patch("app.services.polling.time.sleep"),
        ):
            with pytest.raises(Exception):
                polling.sync_responses(project_id)

    # リトライ回数の上限まで（最大 4 回 = 初回 1 + リトライ 3）呼ばれている
    assert len(resp_resource.list_calls) == 4


# ---------------------------------------------------------------------------
# 8. ページング：nextPageToken がある間取得し切る
# ---------------------------------------------------------------------------


def test_sync_responses_handles_pagination(
    isolated_data_root: Path, fake_creds: object
) -> None:
    """``nextPageToken`` が無くなるまで複数ページを取得し、全件を差分処理する。"""
    from app.services import polling

    resp_resource = _FakeResponsesResource(
        [
            {
                "responses": [
                    _make_form_response(
                        response_id="R1",
                        student_number="1",
                        row0_slots=["16:00-16:20"],
                    ),
                ],
                "nextPageToken": "TOKEN_2",
            },
            {
                "responses": [
                    _make_form_response(
                        response_id="R2",
                        student_number="2",
                        row1_slots=["16:20-16:40"],
                    ),
                ]
                # nextPageToken 無し → 終了
            },
        ]
    )

    with TestClient(create_app()) as client:
        project_id = _create_project_and_form_json(client)
        with (
            patch(
                "app.services.polling.google_auth.get_valid_credentials",
                return_value=fake_creds,
            ),
            patch(
                "app.services.polling.build",
                return_value=_make_service_with_responses(resp_resource),
            ),
            patch("app.services.polling.time.sleep"),
        ):
            result = polling.sync_responses(project_id)

    assert result["new_count"] == 2
    # 2 ページ取得した（pageToken=TOKEN_2 で 2 回目を呼んでいる）
    assert len(resp_resource.list_calls) == 2
    assert resp_resource.list_calls[1].get("pageToken") == "TOKEN_2"
