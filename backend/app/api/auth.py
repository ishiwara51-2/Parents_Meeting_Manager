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

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.services import google_auth


router = APIRouter(prefix="/api/auth", tags=["auth"])

SESSION_STATE_KEY = "oauth_state"


@router.get("/google")
def start_google_auth(request: Request) -> RedirectResponse:
    """Google 認可フローを開始する。

    state を生成しセッションに保存した上で、Google の認可エンドポイントへ
    リダイレクト（HTTP 307）する。
    """
    url, state = google_auth.build_authorization_url()
    request.session[SESSION_STATE_KEY] = state
    return RedirectResponse(url=url)


@router.get("/google/callback")
def google_auth_callback(
    request: Request,
    state: str | None = None,
    code: str | None = None,
    error: str | None = None,
) -> dict[str, str]:
    """Google からのコールバックを処理する。

    1. セッションに保存された state を取り出す（無ければ 400）
    2. クエリの ``state`` と一致するか検証（不一致は 400）
    3. ``code`` を Google に渡してトークン交換
    4. 取得したトークンを ``%APPDATA%\\meeting-scheduler\\config\\oauth_token.json`` に保存
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
        raise HTTPException(
            status_code=400,
            detail="state mismatch (CSRF protection)",
        )

    # state 検証 OK。以降は使い切りなのでセッションから消す
    request.session.pop(SESSION_STATE_KEY, None)

    if error:
        raise HTTPException(status_code=400, detail=f"oauth error: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="missing authorization code")

    google_auth.exchange_code_for_token(code=code, state=state)
    return {"status": "authorized"}


@router.get("/status")
def auth_status() -> dict[str, str]:
    """現在の認証状態を返す（``authorized`` または ``unauthorized``）。"""
    if google_auth.is_authenticated():
        return {"status": "authorized"}
    return {"status": "unauthorized"}


__all__ = ["router"]
