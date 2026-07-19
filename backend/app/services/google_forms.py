"""Google Form 作成サービス（Phase 2.2）。

requirements.md §4.3 / §5.1、`docs/forms_api_research.md` §2 / §4 / §5 / §8、
`docs/handoff_phase2_0.md` で確定した **matrix 方式**
（``QuestionGroupItem`` + ``Grid(columns.type=CHECKBOX)``）で Form を生成する。

API 呼び出しシーケンス（公式の標準パターン）::

    1. forms.create(body={"info": {"title": ...}})
       → タイトルだけ確定。タイトル以外のフィールドはコピーされない仕様
    2. forms.batchUpdate(formId, body={"requests": [createItem×3]})
       → 出席番号 TextQuestion、候補日×時間枠 matrix、自由記述コメント
         TextQuestion を追加
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


# matrix に追加する「一括選択」用の特殊な列・行。
# Google Forms のグリッド質問はネイティブに「行/列の一括選択」を持たないため、
# 追加の列（＝各日の行に対する「終日OK」）と追加の行（＝各時間枠に対する
# 「すべての日でOK」）をデータとして matrix に組み込み、回答パース側
# （app.services.polling._resolve_time_pairs）で実際の候補日×時間枠へ展開する。
SELECT_ALL_TIMES_COLUMN_LABEL = "終日（すべての時間帯）"
SELECT_ALL_DATES_ROW_TITLE = "すべての日（共通で使える時間帯があれば）"

# 自由記述コメント欄。Forms API の TextQuestion には文字数バリデーションが
# 無いため（`forms_api_research.md` §5）、100 文字超の入力に対する防御は
# ``app.services.polling._sanitize_comment`` でサーバ側のみ行う。
COMMENT_QUESTION_TITLE = "面談についてのご要望・コメント（任意）"
COMMENT_MAX_LENGTH = 100


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
        - 各 row に ``required=False``（0 枠の日を許容するため。
          全日不可は ``_parse_availability`` が空リストを返すことで自然に扱える）
        - ``shuffleQuestions=False``（日付順を維持）

    Google Forms のグリッドには行/列を一括選択する機能が無いため、
    ``SELECT_ALL_TIMES_COLUMN_LABEL``（各日の行に追加する「終日」列）と
    ``SELECT_ALL_DATES_ROW_TITLE``（末尾に追加する「すべての日」行）を
    通常の列・行として組み込む。回答パース側でこれらのチェックを
    実際の候補日×時間枠へ展開する。
    """
    return {
        "createItem": {
            "location": {"index": 1},
            "item": {
                "title": (
                    "参加可能な日時にチェックを入れてください"
                    "（複数選択可、参加不可の日は空欄で可）。"
                    f"「{SELECT_ALL_TIMES_COLUMN_LABEL}」にチェックするとその日は"
                    "すべての時間帯を選択したことになります。"
                    f"「{SELECT_ALL_DATES_ROW_TITLE}」の行でチェックした時間帯は"
                    "すべての候補日で選択されます。"
                ),
                "questionGroupItem": {
                    "grid": {
                        "columns": {
                            "type": "CHECKBOX",
                            "options": [
                                {"value": label}
                                for label in [
                                    *time_slot_labels,
                                    SELECT_ALL_TIMES_COLUMN_LABEL,
                                ]
                            ],
                        },
                        "shuffleQuestions": False,
                    },
                    "questions": [
                        {
                            "required": False,
                            "rowQuestion": {"title": date_str},
                        }
                        for date_str in candidate_dates
                    ]
                    + [
                        {
                            "required": False,
                            "rowQuestion": {"title": SELECT_ALL_DATES_ROW_TITLE},
                        }
                    ],
                },
            },
        }
    }


def _build_comment_item() -> dict[str, Any]:
    """自由記述コメント質問の ``createItem`` リクエストを組み立てる。

    matrix（インデックス 1）より後ろのインデックス 2 に配置する。
    ``_extract_row_qids_from_batch`` が matrix を ``replies[1]`` 固定で参照する
    ため、matrix より前に別の質問を挿し込むとそちらが壊れる。
    """
    return {
        "createItem": {
            "location": {"index": 2},
            "item": {
                "title": COMMENT_QUESTION_TITLE,
                "description": (
                    "面談の日程調整について伝えたいことがあればご記入ください"
                    f"（任意、{COMMENT_MAX_LENGTH}文字以内。"
                    "超過分は保存時に切り詰められます）"
                ),
                "questionItem": {
                    "question": {
                        "required": False,
                        "textQuestion": {"paragraph": False},
                    }
                },
            },
        }
    }


def _build_batch_update_body(
    *, candidate_dates: list[str], time_slot_labels: list[str]
) -> dict[str, Any]:
    """``forms.batchUpdate`` リクエスト本体を組み立てる。

    インデックス 0 = 出席番号 TextQuestion、インデックス 1 = matrix、
    インデックス 2 = 自由記述コメント TextQuestion。
    順序は ``form.json`` 保存時の ``row_question_id_by_date`` 復元にも依存する
    （matrix は常にインデックス 1 に固定する）。
    """
    return {
        "requests": [
            _build_student_number_item(),
            _build_matrix_item(
                candidate_dates=candidate_dates,
                time_slot_labels=time_slot_labels,
            ),
            _build_comment_item(),
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


def _extract_comment_qid(batch_response: dict[str, Any]) -> str | None:
    """``batchUpdate`` 応答からコメント質問の questionId を取り出す。

    コメント質問は補助的な項目であり、取得に失敗しても Form 自体の生成は
    継続する（``comment_question_id=None`` として扱い、回答パース時は
    コメント欄なしとして無視される）。
    """
    try:
        qid_list = batch_response["replies"][2]["createItem"]["questionId"]
    except (KeyError, IndexError, TypeError):
        logger.warning(
            "forms.batchUpdate 応答からコメント questionId が取得できません。"
            "コメント欄なしの Form として扱います"
        )
        return None
    if not qid_list:
        logger.warning(
            "forms.batchUpdate 応答のコメント questionId が空配列です。"
            "コメント欄なしの Form として扱います"
        )
        return None
    return qid_list[0]


def _extract_row_qids_from_batch(
    batch_response: dict[str, Any], *, candidate_dates: list[str]
) -> tuple[dict[str, str], str | None]:
    """``batchUpdate`` 応答から matrix 行 questionId を取り出す。

    行は ``[*candidate_dates, SELECT_ALL_DATES_ROW_TITLE]`` の順で作成しているため
    （``_build_matrix_item``）、応答の questionId 配列も同じ順序・件数
    （候補日数 + 1）である想定で分解する。件数が合わない・空要素を含む場合は
    ``({}, None)`` を返し、呼び出し元が ``forms.get`` フォールバックへ回す。
    """
    try:
        qid_list = (
            batch_response["replies"][1]["createItem"]["questionId"]
        )
    except (KeyError, IndexError, TypeError):
        return {}, None
    qid_list = list(qid_list) if qid_list else []
    if len(qid_list) != len(candidate_dates) + 1 or not all(qid_list):
        return {}, None
    row_question_id_by_date = dict(
        zip(candidate_dates, qid_list[:-1], strict=True)
    )
    return row_question_id_by_date, qid_list[-1]


def _extract_row_qids_from_form(
    form_get_response: dict[str, Any], *, candidate_dates: list[str]
) -> tuple[dict[str, str], str | None]:
    """``forms.get`` 応答から「候補日 → 行 questionId」マップを構築する。

    レスポンス構造（`forms_api_research.md` §2 / Forms API リファレンス）::

        items: [
            { questionItem: {...} },           # 出席番号
            { questionGroupItem: {
                grid: {...},
                questions: [
                    { questionId: ..., rowQuestion: { title: "YYYY-MM-DD" } },
                    ...
                    { questionId: ..., rowQuestion: { title: SELECT_ALL_DATES_ROW_TITLE } },
                ]
            }}
        ]

    「すべての日」行は ``rowQuestion.title`` で識別し、別枠の戻り値
    （2 要素目）として返す。
    """
    items = form_get_response.get("items") or []
    for item in items:
        qgi = item.get("questionGroupItem")
        if not qgi:
            continue
        questions = qgi.get("questions") or []
        by_title: dict[str, str] = {}
        for q in questions:
            row = q.get("rowQuestion") or {}
            title = row.get("title")
            qid = q.get("questionId")
            if title and qid:
                by_title[title] = qid
        if by_title:
            # 候補日順に揃え直して返す（候補日に該当しないキーは除外）
            row_question_id_by_date = {
                d: by_title[d] for d in candidate_dates if d in by_title
            }
            select_all_dates_qid = by_title.get(SELECT_ALL_DATES_ROW_TITLE)
            return row_question_id_by_date, select_all_dates_qid

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

    # コメント questionId（任意項目のため、取得失敗は None のまま継続）
    comment_qid = _extract_comment_qid(batch_response)

    # 3. matrix 行 questionId（候補日 + 「すべての日」行）は batchUpdate 応答に
    #    含まれることもあるが、公式リファレンスに明記が無いため、
    #    取得できなければフォールバックで forms.get
    row_question_id_by_date, select_all_dates_qid = _extract_row_qids_from_batch(
        batch_response, candidate_dates=candidate_dates
    )
    if row_question_id_by_date:
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
        row_question_id_by_date, select_all_dates_qid = _extract_row_qids_from_form(
            form_get_response, candidate_dates=candidate_dates
        )

    return FormInfo(
        form_id=form_id,
        responder_uri=responder_uri,
        edit_uri=_build_edit_uri(form_id),
        student_number_question_id=student_number_qid,
        comment_question_id=comment_qid,
        row_question_id_by_date=row_question_id_by_date,
        time_slot_labels=time_slot_labels,
        select_all_dates_row_question_id=select_all_dates_qid,
    )


__all__ = [
    "create_form",
    "GoogleAuthRequiredError",
    "SELECT_ALL_TIMES_COLUMN_LABEL",
    "SELECT_ALL_DATES_ROW_TITLE",
    "COMMENT_MAX_LENGTH",
]
