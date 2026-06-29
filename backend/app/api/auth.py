"""OAuth 認証 API ルータ。

requirements.md §2.1 / §6 に対応する以下3エンドポイントを提供する。

- ``GET /api/auth/google`` 認証開始（``state`` 生成 → セッション保存 → リダイレクト）
- ``GET /api/auth/google/callback`` コールバック処理（``state`` 検証 → トークン取得）
- ``GET /api/auth/status`` 認証状態確認

**CSRF 対策（requirements.md §2.1）**：state パラメータをサーバ側セッション
（``starlette.middleware.sessions.SessionMiddleware``）に保存し、コールバック
時の受信値と一致するか検証する。不一致／セッション未保存はいずれも HTTP 400。
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.services import google_auth


logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/auth", tags=["auth"])

SESSION_STATE_KEY = "oauth_state"
SESSION_NEXT_KEY = "oauth_next"
SESSION_VERIFIER_KEY = "oauth_code_verifier"


def _safe_next(next_url: str | None) -> str:
    """Open redirect 防止のため、相対パスか localhost 系絶対URLのみを許可する。

    - ``/`` 始まりの相対パス：そのまま許可（``//`` で始まるプロトコル相対は拒否）
    - 絶対URL：``http(s)://localhost`` または ``http(s)://127.0.0.1`` のみ許可
      （dev モードで backend(8000)→frontend(5173) へ戻すため必要）
    - それ以外は ``/`` にフォールバック
    """
    if not next_url:
        return "/"
    if next_url.startswith("/") and not next_url.startswith("//"):
        return next_url
    try:
        u = urlparse(next_url)
    except ValueError:
        return "/"
    if u.scheme in ("http", "https") and u.hostname in ("localhost", "127.0.0.1"):
        return next_url
    return "/"


@router.get("/google")
def start_google_auth(
    request: Request,
    next: str | None = None,
) -> RedirectResponse:
    """Google 認可フローを開始する。

    state / PKCE verifier を生成しセッションに保存した上で、Google の
    認可エンドポイントへリダイレクト（HTTP 307）する。
    ``next`` は認証完了後の戻り先（相対パスまたは localhost 系絶対URL）。
    """
    url, state, code_verifier = google_auth.build_authorization_url()
    request.session[SESSION_STATE_KEY] = state
    request.session[SESSION_NEXT_KEY] = _safe_next(next)
    # PKCE verifier はトークン交換時に必須。未生成なら保存しない。
    if code_verifier is not None:
        request.session[SESSION_VERIFIER_KEY] = code_verifier
    return RedirectResponse(url=url)


@router.get("/google/callback")
def google_auth_callback(
    request: Request,
    state: str | None = None,
    code: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Google からのコールバックを処理する。

    1. セッションに保存された state を取り出す（無ければ 400）
    2. クエリの ``state`` と一致するか検証（不一致は 400）
    3. ``code`` を Google に渡してトークン交換
    4. 取得したトークンを ``%APPDATA%\\meeting-scheduler\\config\\oauth_token.json`` に保存
    5. セッションに保存しておいた ``next`` URL へリダイレクト（既定 ``/``）
    """
    saved_state = request.session.get(SESSION_STATE_KEY)
    # state がセッションに無い、もしくはクエリ state が空 → 400
    if not saved_state:
        raise HTTPException(
            status_code=400,
            detail="state not found in session (CSRF protection)",
        )
    if not state or saved_state != state:
        # CSRF 攻撃の可能性。セッションに残った state を破棄してから 400 を返す
        request.session.pop(SESSION_STATE_KEY, None)
        request.session.pop(SESSION_NEXT_KEY, None)
        request.session.pop(SESSION_VERIFIER_KEY, None)
        raise HTTPException(
            status_code=400,
            detail="state mismatch (CSRF protection)",
        )

    # state 検証 OK。以降は使い切りなのでセッションから消す
    request.session.pop(SESSION_STATE_KEY, None)
    next_url = _safe_next(request.session.pop(SESSION_NEXT_KEY, None))
    code_verifier = request.session.pop(SESSION_VERIFIER_KEY, None)

    if error:
        raise HTTPException(status_code=400, detail=f"oauth error: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="missing authorization code")

    try:
        google_auth.exchange_code_for_token(
            code=code,
            state=state,
            code_verifier=code_verifier,
        )
    except Exception as exc:
        # Google からの code 交換失敗（ネットワーク・スコープ不一致・無効 code 等）。
        # raw 500 はブラウザでもログでも原因が分からないため、明示的に記録し
        # 詳細を含む 500 を返す。
        logger.exception("OAuth code exchange failed")
        raise HTTPException(
            status_code=500,
            detail=f"OAuth code exchange failed: {exc!r}",
        ) from exc
    # 303 See Other: POST 後のリダイレクトと同じセマンティクスで GET に正規化
    return RedirectResponse(url=next_url, status_code=303)


@router.get("/status")
def auth_status() -> dict[str, str]:
    """現在の認証状態を返す（``authorized`` または ``unauthorized``）。"""
    if google_auth.is_authenticated():
        return {"status": "authorized"}
    return {"status": "unauthorized"}


__all__ = ["router"]
