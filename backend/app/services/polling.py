"""Form 回答ポーリング・パースサービス（Phase 2.3）。

requirements.md §4.4 / §5.2、`docs/forms_api_research.md` §4 / §5 / §6 / §8、
`docs/handoff_phase2_0.md` / `docs/handoff_phase2_2.md` で確定した方針：

- 採用方式: matrix（``QuestionGroupItem`` + ``Grid(columns.type=CHECKBOX)``）
- API シーケンス: ``forms.responses.list(formId=..., pageToken=...)`` を
  ``nextPageToken`` が無くなるまで反復し**全件取得**してからクライアント側で差分判定
- 差分検知: ``FileResponseRepository.get_known_form_response_ids()`` で得た既知集合との
  ``set`` 差分（**順序非依存**で動作）
- 整数バリデーション: API レベルでは未対応 → サーバ側で ``int(value.strip())``。
  失敗時は不正回答として **保存せずスキップ + 警告ログ**
- 429 / 503 リトライ: truncated exponential backoff（初回 1 秒・倍々、最大 3 回まで）。
  ``Retry-After`` ヘッダがあれば優先採用

認証は ``app.services.google_auth.get_valid_credentials()`` 経由（期限切れ自動リフレッシュ）。
未認証時は ``GoogleAuthRequiredError`` を投げ、API 層で 401 に変換する。

リトライ全消費時は ``PollingRetryExhaustedError`` を投げ、API 層で 503 に変換する想定。
"""

from __future__ import annotations

import email.utils
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.config import get_settings
from app.models.form import FormInfo
from app.models.response import Availability, Response
from app.repositories.file_repository import (
    FileProjectRepository,
    FileResponseRepository,
)
from app.services import google_auth
from app.services.google_forms import GoogleAuthRequiredError


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 例外
# ---------------------------------------------------------------------------


class PollingRetryExhaustedError(RuntimeError):
    """429 / 503 のリトライ上限を超えた場合に投げる。

    API 層で 503 Service Unavailable に変換し、フロントへ「一時的にクォータ超過」を伝える。
    """


class FormNotConfiguredError(RuntimeError):
    """対象プロジェクトに ``form.json`` が存在せず、ポーリング対象が無い場合に投げる。

    API 層で 409 Conflict（先に Form を作成してください）に変換する想定。
    """


# ---------------------------------------------------------------------------
# 内部パラメータ（リトライ設定）
# ---------------------------------------------------------------------------

#: リトライ対象 HTTP ステータス。Google Forms API 公式の「Expensive read」分類は
#: クォータ超過時に 429、サーバ側一時障害は 503 を返す（`forms_api_research.md` §6）。
RETRYABLE_STATUSES = frozenset({429, 503})

#: 最大リトライ回数（初回呼び出しに加えて、最大この回数だけ追加で呼び直す）。
DEFAULT_MAX_RETRIES = 3

#: 初回バックオフ秒（指数で 2 倍ずつ増やす）。``Retry-After`` ヘッダがあればそちらを優先。
INITIAL_BACKOFF_SECONDS = 1.0


# ---------------------------------------------------------------------------
# ヘルパ
# ---------------------------------------------------------------------------


def _parse_retry_after_header(value: str | None) -> float | None:
    """``Retry-After`` ヘッダをパースして秒数を返す。

    RFC 7231 §7.1.3 に従い、整数秒（例: ``"30"``) または HTTP-date 形式
    （例: ``"Fri, 31 Dec 2026 23:59:59 GMT"``) を受け付ける。
    解釈不能なら ``None`` を返す（呼び出し側の指数バックオフにフォールバック）。
    """
    if not value:
        return None
    # 整数秒
    try:
        seconds = float(value)
        if seconds < 0:
            return None
        return seconds
    except ValueError:
        pass
    # HTTP-date
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    delta = (when - datetime.now(timezone.utc)).total_seconds()
    return max(delta, 0.0)


def _http_error_status(exc: HttpError) -> int | None:
    """``HttpError.resp.status`` を int で安全に取り出す。"""
    resp = getattr(exc, "resp", None)
    if resp is None:
        return None
    status = getattr(resp, "status", None)
    if status is None:
        return None
    try:
        return int(status)
    except (TypeError, ValueError):
        return None


def _http_error_retry_after(exc: HttpError) -> str | None:
    """``Retry-After`` ヘッダを取り出す（``httplib2.Response`` は ``dict`` 風）。"""
    resp = getattr(exc, "resp", None)
    if resp is None:
        return None
    # httplib2.Response は dict サブクラス
    try:
        return resp.get("retry-after")  # type: ignore[no-any-return]
    except AttributeError:
        return None


# ---------------------------------------------------------------------------
# 全件取得（ページング + リトライ）
# ---------------------------------------------------------------------------


def _list_all_responses(
    forms_api: Any,
    *,
    form_id: str,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> list[dict[str, Any]]:
    """``forms.responses.list`` を ``nextPageToken`` が尽きるまで反復し全件返す。

    各ページ呼び出しで 429 / 503 を受けた場合は ``max_retries`` 回まで
    truncated exponential backoff（初期 ``INITIAL_BACKOFF_SECONDS`` 秒、倍々）で
    リトライする。``Retry-After`` ヘッダがあればその秒数を優先採用。
    リトライ全消費時は ``PollingRetryExhaustedError`` を投げる。

    呼び出し側責務:
        - ``forms_api`` は ``service.forms()`` の戻り値（``ResponsesResource`` 系を持つ）
        - 認証/サービスビルドは呼び出し側で済ませる（テスト容易性のため）
    """
    all_responses: list[dict[str, Any]] = []
    page_token: str | None = None

    while True:
        attempt = 0
        backoff = INITIAL_BACKOFF_SECONDS
        last_error: HttpError | None = None

        # 1 ページ取得（リトライループ）
        while True:
            kwargs: dict[str, Any] = {"formId": form_id}
            if page_token:
                kwargs["pageToken"] = page_token

            try:
                page = (
                    forms_api.responses().list(**kwargs).execute()
                )
            except HttpError as exc:
                status = _http_error_status(exc)
                if status in RETRYABLE_STATUSES and attempt < max_retries:
                    retry_after = _parse_retry_after_header(
                        _http_error_retry_after(exc)
                    )
                    sleep_for = retry_after if retry_after is not None else backoff
                    logger.warning(
                        "forms.responses.list returned %s; retrying in %.1fs "
                        "(attempt %d/%d)",
                        status,
                        sleep_for,
                        attempt + 1,
                        max_retries,
                    )
                    time.sleep(sleep_for)
                    attempt += 1
                    backoff *= 2
                    last_error = exc
                    continue
                # リトライ非対象 or リトライ上限超過
                if status in RETRYABLE_STATUSES:
                    raise PollingRetryExhaustedError(
                        f"forms.responses.list が {status} を返し続け、"
                        f"リトライ上限 {max_retries} 回を超過しました"
                    ) from exc
                # その他 HTTP エラー（401/403/404/400 等）はそのまま伝播
                raise
            else:
                # 成功
                all_responses.extend(page.get("responses") or [])
                page_token = page.get("nextPageToken")
                break

        if not page_token:
            break

    return all_responses


# ---------------------------------------------------------------------------
# パース（matrix 回答 → Response モデル）
# ---------------------------------------------------------------------------


def _extract_text_value(answer: dict[str, Any] | None) -> str | None:
    """``Answer.textAnswers.answers[0].value`` を取り出す。

    `forms_api_research.md` §4 のサンプル構造に準拠。
    """
    if not answer:
        return None
    text_answers = (answer.get("textAnswers") or {}).get("answers") or []
    if not text_answers:
        return None
    return text_answers[0].get("value")


def _extract_selected_labels(answer: dict[str, Any] | None) -> list[str]:
    """matrix 1 行に対する CHECKBOX 回答ラベル配列を取り出す。

    順序はチェック順（保護者の操作順）になる可能性があるため、呼び出し側で
    順序非依存に扱う前提。
    """
    if not answer:
        return []
    text_answers = (answer.get("textAnswers") or {}).get("answers") or []
    return [
        a.get("value")
        for a in text_answers
        if isinstance(a.get("value"), str)
    ]


def _parse_availability(
    answers: dict[str, dict[str, Any]],
    *,
    row_question_id_by_date: dict[str, str],
) -> list[Availability]:
    """matrix 回答を ``Availability`` のリストに変換する。

    `forms_api_research.md` §4 のパース疑似コードに準拠：
        - 行 questionId に対応する CHECKBOX 値（``HH:MM-HH:MM``）を分解し
          ``date / start / end`` に格納
    """
    availability: list[Availability] = []
    for date_str, row_qid in row_question_id_by_date.items():
        labels = _extract_selected_labels(answers.get(row_qid))
        for label in labels:
            if "-" not in label:
                logger.warning(
                    "matrix label '%s' has no '-' separator; skipping",
                    label,
                )
                continue
            start_str, end_str = label.split("-", 1)
            try:
                availability.append(
                    Availability(
                        date=date_str,
                        start=start_str.strip(),
                        end=end_str.strip(),
                    )
                )
            except Exception as exc:  # pydantic ValidationError 含む
                logger.warning(
                    "availability validation failed for label '%s' on %s: %s",
                    label,
                    date_str,
                    exc,
                )
    return availability


def _parse_response(
    *,
    project_id: str,
    form_response: dict[str, Any],
    form_info: FormInfo,
) -> Response | None:
    """1 件の Forms API レスポンスを ``Response`` モデルに変換する。

    返り値が ``None`` の場合は「不正回答 → スキップ」の意味。理由は警告ログに残す。
    """
    response_id = form_response.get("responseId")
    if not response_id:
        logger.warning("response without responseId is skipped: %s", form_response)
        return None

    answers = form_response.get("answers") or {}

    # 1. 出席番号（整数バリデーション）
    raw_sn = _extract_text_value(answers.get(form_info.student_number_question_id))
    if raw_sn is None:
        logger.warning(
            "responseId=%s: student_number answer is missing; skipping",
            response_id,
        )
        return None
    try:
        student_number = int(str(raw_sn).strip())
    except ValueError:
        logger.warning(
            "responseId=%s: student_number '%s' is not an integer; skipping",
            response_id,
            raw_sn,
        )
        return None

    # 2. 提出時刻（lastSubmittedTime を優先、なければ createTime）
    submitted_at_str = (
        form_response.get("lastSubmittedTime")
        or form_response.get("createTime")
    )
    if not submitted_at_str:
        logger.warning(
            "responseId=%s: lastSubmittedTime/createTime missing; skipping",
            response_id,
        )
        return None

    try:
        # Pydantic v2 が ISO8601 文字列を datetime に変換できる
        submitted_at = datetime.fromisoformat(
            submitted_at_str.replace("Z", "+00:00")
        )
    except ValueError:
        logger.warning(
            "responseId=%s: submitted_at '%s' is not a valid ISO 8601 datetime",
            response_id,
            submitted_at_str,
        )
        return None

    # 3. availability（matrix 各行 → 時間枠）
    availability = _parse_availability(
        answers,
        row_question_id_by_date=form_info.row_question_id_by_date,
    )

    try:
        return Response(
            project_id=project_id,
            student_number=student_number,
            submitted_at=submitted_at,
            google_form_response_id=response_id,
            availability=availability,
        )
    except Exception as exc:
        logger.warning(
            "responseId=%s: Response model validation failed: %s",
            response_id,
            exc,
        )
        return None


# ---------------------------------------------------------------------------
# サービスビルド（モック可能な seam）
# ---------------------------------------------------------------------------


def _build_forms_service() -> Any:
    """Forms API クライアントを認証込みで組み立てる。

    Phase 1.3 の ``google_auth.get_valid_credentials()`` を呼ぶため、期限切れトークンは
    自動でリフレッシュ・ディスク再保存される。
    """
    creds = google_auth.get_valid_credentials()
    if creds is None:
        raise GoogleAuthRequiredError(
            "Google OAuth トークンが未保存です。/api/auth/google から認証してください"
        )
    return build("forms", "v1", credentials=creds, cache_discovery=False)


# ---------------------------------------------------------------------------
# 公開関数
# ---------------------------------------------------------------------------


def sync_responses(project_id: str) -> dict[str, Any]:
    """指定プロジェクトの Form 回答を同期取得し、未取得分を保存する。

    処理フロー:
        1. ``form.json`` を読み出して ``FormInfo`` を取得
        2. 認証込みで Forms サービスを構築
        3. ``forms.responses.list`` を全ページ取得（429/503 リトライ込み）
        4. 既知 ``responseId`` 集合と差分を取り、新規分を抽出
        5. 新規分をパース（整数バリデーション失敗はスキップ）
        6. 各 Response を ``responses/<sn>/<YYYYMMDD_HHMMSS>.json`` に保存

    Returns:
        サマリ辞書::

            {
                "new_count": <保存した件数>,
                "skipped_count": <不正回答などでスキップした件数>,
                "errors": [<エラーメッセージ>, ...],
            }

    Raises:
        FormNotConfiguredError: ``form.json`` 未作成（先に Form を作るべき）。
        GoogleAuthRequiredError: OAuth トークン未保存・リフレッシュ失敗。
        PollingRetryExhaustedError: 429/503 リトライ上限超過。
    """
    settings = get_settings()
    project_repo = FileProjectRepository(settings)
    response_repo = FileResponseRepository(settings)

    project = project_repo.get(project_id)
    if project is None:
        raise FileNotFoundError(
            f"project '{project_id}' not found"
        )

    form_info = project_repo.get_form_info(project_id)
    if form_info is None:
        raise FormNotConfiguredError(
            f"project '{project_id}' に form.json がありません。先に Form を作成してください"
        )

    service = _build_forms_service()
    forms_api = service.forms()

    all_form_responses = _list_all_responses(
        forms_api, form_id=form_info.form_id
    )

    # 集合差分による新規抽出（順序非依存）
    known_ids: set[str] = response_repo.get_known_form_response_ids(project_id)
    new_count = 0
    skipped_count = 0
    errors: list[str] = []

    for fr in all_form_responses:
        rid = fr.get("responseId")
        if not rid:
            skipped_count += 1
            errors.append("responseId missing in form response")
            continue
        if rid in known_ids:
            continue

        parsed = _parse_response(
            project_id=project_id,
            form_response=fr,
            form_info=form_info,
        )
        if parsed is None:
            skipped_count += 1
            errors.append(f"responseId={rid}: parse skipped (see logs)")
            continue

        try:
            response_repo.save_response(project_id, parsed)
            known_ids.add(rid)  # 同一バッチ内重複への保険
            new_count += 1
        except Exception as exc:
            logger.exception(
                "responseId=%s: save_response failed", rid
            )
            errors.append(f"responseId={rid}: save failed ({exc})")
            skipped_count += 1

    return {
        "new_count": new_count,
        "skipped_count": skipped_count,
        "errors": errors,
    }


__all__ = [
    "sync_responses",
    "PollingRetryExhaustedError",
    "FormNotConfiguredError",
    # 再エクスポート（API 層から扱いやすくするため）
    "GoogleAuthRequiredError",
]
