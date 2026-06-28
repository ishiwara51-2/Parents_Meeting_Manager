"""Google Form 作成サービス（Phase 2.2）。

requirements.md §4.3 / §5.1、`docs/forms_api_research.md` §2 / §4 / §5 / §8、
`docs/handoff_phase2_0.md` で確定した **matrix 方式**
（``QuestionGroupItem`` + ``Grid(columns.type=CHECKBOX)``）で Form を生成する。

API 呼び出しシーケンス（公式の標準パターン）::

    1. forms.create(body={"info": {"title": ...}})
       → タイトルだけ確定。タイトル以外のフィールドはコピーされない仕様
    2. forms.batchUpdate(formId, body={"requests": [createItem×2]})
       → 出席番号 TextQuestion と 候補日×時間枠 matrix を追加
    3. （フォールバック）forms.get(formId)
       → batchUpdate の応答に matrix の行 questionId が含まれない場合のみ
         実機 API での挙動が公式リファレンスに明記されていないリスクへの保険
         （`forms_api_research.md` §8 リスク表）

保存先：``<project_dir>/form.json``（FormInfo モデル）。Phase 2.3 で
回答パース時にこのファイルから ``row_question_id_by_date`` を引き、
「行 questionId → 候補日」のマッピングを用いて availability を組み立てる。

認証：``app.services.google_auth.get_valid_credentials()`` を使う
（期限切れ自動リフレッシュ込み）。未認証時は ``GoogleAuthRequiredError``
を投げ、API 層で 401 に変換する。
"""

from __future__ import annotations

import logging
from typing import Any

from googleapiclient.discovery import build

from app.models.form import FormInfo
from app.models.project import Project, TimeSlot
from app.services import google_auth


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 例外
# ---------------------------------------------------------------------------


class GoogleAuthRequiredError(RuntimeError):
    """OAuth 認証が完了していない、もしくはリフレッシュに失敗した場合に投げる。

    API 層で 401 Unauthorized に変換し、フロントへ認証導線を示す。
    """


# ---------------------------------------------------------------------------
# Form 構造ビルダ（純粋関数 = テスタブル）
# ---------------------------------------------------------------------------


def _format_time_slot_label(slot: TimeSlot) -> str:
    """時間枠を ``HH:MM-HH:MM`` ラベルに整形する。

    forms_api_research.md §2 のサンプル JSON ``"16:00-16:20"`` 形式に揃える。
    Phase 2.3 のパースで ``label.split("-")`` で分解されるため、ハイフンを境界に使う。
    """
    start = slot.start.strftime("%H:%M")
    end = slot.end.strftime("%H:%M")
    return f"{start}-{end}"


def _build_student_number_item() -> dict[str, Any]:
    """出席番号質問の ``createItem`` リクエストを組み立てる。

    `forms_api_research.md` §5 採用方針：
        - ``TextQuestion(paragraph=False)``
        - ``required=True``
        - 整数バリデーションは API では未対応のため、Phase 2.3 のサーバ側で実装
    """
    return {
        "createItem": {
            "location": {"index": 0},
            "item": {
                "title": "出席番号（半角数字）",
                "description": "あなたの出席番号を入力してください",
                "questionItem": {
                    "question": {
                        "required": True,
                        "textQuestion": {"paragraph": False},
                    }
                },
            },
        }
    }


def _build_matrix_item(
    *, candidate_dates: list[str], time_slot_labels: list[str]
) -> dict[str, Any]:
    """候補日×時間枠の matrix ``createItem`` リクエストを組み立てる。

    `forms_api_research.md` §2 採用方針（matrix）：
        - ``QuestionGroupItem`` + ``Grid``
        - ``columns.type=CHECKBOX``（複数選択可）
        - 各行 = 候補日（``rowQuestion.title`` に ISO 文字列を入れる）
        - 各 row に ``required=True``（行単位の必須化が API 仕様）
        - ``shuffleQuestions=False``（日付順を維持）
    """
    return {
        "createItem": {
            "location": {"index": 1},
            "item": {
                "title": "参加可能な日時にチェックを入れてください（複数選択可）",
                "questionGroupItem": {
                    "grid": {
                        "columns": {
                            "type": "CHECKBOX",
                            "options": [
                                {"value": label}
                                for label in time_slot_labels
                            ],
                        },
                        "shuffleQuestions": False,
                    },
                    "questions": [
                        {
                            "required": True,
                            "rowQuestion": {"title": date_str},
                        }
                        for date_str in candidate_dates
                    ],
                },
            },
        }
    }


def _build_batch_update_body(
    *, candidate_dates: list[str], time_slot_labels: list[str]
) -> dict[str, Any]:
    """``forms.batchUpdate`` リクエスト本体を組み立てる。

    インデックス 0 = 出席番号 TextQuestion、インデックス 1 = matrix。
    順序は ``form.json`` 保存時の ``row_question_id_by_date`` 復元にも依存する。
    """
    return {
        "requests": [
            _build_student_number_item(),
            _build_matrix_item(
                candidate_dates=candidate_dates,
                time_slot_labels=time_slot_labels,
            ),
        ]
    }


# ---------------------------------------------------------------------------
# レスポンスパース
# ---------------------------------------------------------------------------


def _extract_student_number_qid(batch_response: dict[str, Any]) -> str:
    """``batchUpdate`` 応答から出席番号 questionId を取り出す。

    ``replies[0].createItem.questionId`` は ``string[]`` で 1 要素のはず。
    取得できない場合は ``RuntimeError``（実機で観測されたら要調査）。
    """
    try:
        qid_list = (
            batch_response["replies"][0]["createItem"]["questionId"]
        )
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(
            "forms.batchUpdate 応答から出席番号 questionId が取得できません"
        ) from exc

    if not qid_list:
        raise RuntimeError(
            "forms.batchUpdate 応答の出席番号 questionId が空配列です"
        )
    return qid_list[0]


def _extract_row_qids_from_batch(
    batch_response: dict[str, Any],
) -> list[str]:
    """``batchUpdate`` 応答から matrix 行 questionId を取り出す。

    取得できれば候補日順の文字列配列を返す。``forms.get`` フォールバックが
    必要かどうかの判定にも使う（空配列なら呼び出し元が ``forms.get`` する）。
    """
    try:
        qid_list = (
            batch_response["replies"][1]["createItem"]["questionId"]
        )
    except (KeyError, IndexError, TypeError):
        return []
    return list(qid_list) if qid_list else []


def _extract_row_qids_from_form(
    form_get_response: dict[str, Any], *, candidate_dates: list[str]
) -> dict[str, str]:
    """``forms.get`` 応答から「候補日 → 行 questionId」マップを構築する。

    レスポンス構造（`forms_api_research.md` §2 / Forms API リファレンス）::

        items: [
            { questionItem: {...} },           # 出席番号
            { questionGroupItem: {
                grid: {...},
                questions: [
                    { questionId: ..., rowQuestion: { title: "YYYY-MM-DD" } },
                    ...
                ]
            }}
        ]
    """
    items = form_get_response.get("items") or []
    for item in items:
        qgi = item.get("questionGroupItem")
        if not qgi:
            continue
        questions = qgi.get("questions") or []
        result: dict[str, str] = {}
        for q in questions:
            row = q.get("rowQuestion") or {}
            date_str = row.get("title")
            qid = q.get("questionId")
            if date_str and qid:
                result[date_str] = qid
        if result:
            # 候補日順に揃え直して返す（候補日に該当しないキーは除外）
            return {d: result[d] for d in candidate_dates if d in result}

    raise RuntimeError(
        "forms.get 応答から matrix 行 questionId が抽出できません。"
        "Form の構造が想定と異なる可能性があります"
    )


# ---------------------------------------------------------------------------
# URL 構築
# ---------------------------------------------------------------------------


def _build_edit_uri(form_id: str) -> str:
    """編集 URL を formId から構築する。

    Google Forms API は edit URI を直接返さないため、慣例的な URL パターン
    （``https://docs.google.com/forms/d/<formId>/edit``）で組み立てる。
    """
    return f"https://docs.google.com/forms/d/{form_id}/edit"


# ---------------------------------------------------------------------------
# サービス公開関数
# ---------------------------------------------------------------------------


def _build_forms_service():
    """Forms API クライアントを組み立てる（認証込み）。

    Phase 1.3 の ``google_auth.get_valid_credentials`` を呼び出すことで、
    トークン期限切れ時は自動でリフレッシュ・ディスク再保存される。

    Raises:
        GoogleAuthRequiredError: トークン未保存 or リフレッシュ失敗。
    """
    creds = google_auth.get_valid_credentials()
    if creds is None:
        raise GoogleAuthRequiredError(
            "Google OAuth トークンが未保存です。/api/auth/google から認証してください"
        )
    # discovery cache を無効化（ファイルシステム書込みエラー回避）
    return build("forms", "v1", credentials=creds, cache_discovery=False)


def create_form(project: Project) -> FormInfo:
    """``Project`` から Google Form を生成し、``FormInfo`` を返す。

    本関数は ``form.json`` の保存までは行わない（呼び出し側の責務）。
    Repository への永続化は API ハンドラ層で実施する。

    Args:
        project: Phase 2.1 で作成済みのプロジェクトメタ。
            ``candidate_dates`` / ``candidate_time_slots`` を Form の rows / columns に展開する。

    Returns:
        FormInfo: 生成済み Form の保存用メタデータ。
    """
    service = _build_forms_service()
    forms_api = service.forms()

    candidate_dates: list[str] = [d.isoformat() for d in project.candidate_dates]
    time_slot_labels: list[str] = [
        _format_time_slot_label(s) for s in project.candidate_time_slots
    ]

    # 1. forms.create でタイトルだけ確定（公式仕様：タイトル以外は無視される）
    create_response: dict[str, Any] = forms_api.create(
        body={"info": {"title": project.display_name}}
    ).execute()
    form_id: str = create_response["formId"]
    responder_uri: str = create_response.get("responderUri") or ""

    # 2. batchUpdate で質問 2 件を一括追加
    batch_response: dict[str, Any] = forms_api.batchUpdate(
        formId=form_id,
        body=_build_batch_update_body(
            candidate_dates=candidate_dates,
            time_slot_labels=time_slot_labels,
        ),
    ).execute()

    # 出席番号 questionId は batchUpdate 応答から必ず取れる想定
    student_number_qid = _extract_student_number_qid(batch_response)

    # 3. matrix 行 questionId は batchUpdate 応答に含まれることもあるが、
    #    公式リファレンスに明記が無いため、空配列ならフォールバックで forms.get
    row_qids = _extract_row_qids_from_batch(batch_response)
    if len(row_qids) == len(candidate_dates) and all(q for q in row_qids):
        # 候補日順とインデックス対応していると想定（API は createItem の
        # 順序で questionId 配列を返す）
        row_question_id_by_date = {
            date_str: qid
            for date_str, qid in zip(candidate_dates, row_qids, strict=True)
        }
        logger.debug(
            "matrix row questionIds resolved from batchUpdate response "
            "(forms.get skipped)"
        )
    else:
        logger.debug(
            "matrix row questionIds missing from batchUpdate response; "
            "falling back to forms.get(%s)",
            form_id,
        )
        form_get_response: dict[str, Any] = forms_api.get(
            formId=form_id
        ).execute()
        row_question_id_by_date = _extract_row_qids_from_form(
            form_get_response, candidate_dates=candidate_dates
        )

    return FormInfo(
        form_id=form_id,
        responder_uri=responder_uri,
        edit_uri=_build_edit_uri(form_id),
        student_number_question_id=student_number_qid,
        row_question_id_by_date=row_question_id_by_date,
        time_slot_labels=time_slot_labels,
    )


__all__ = [
    "create_form",
    "GoogleAuthRequiredError",
]
