"""Google OAuth2 認証フロー（サービス層）。

requirements.md §2.1 / §3.1 / §8.5 に従い、教師個人の Google アカウントを使った
OAuth2 認証を行う。役割は以下。

- ``oauth_client.json`` の読み込み（GCP コンソールでダウンロードした
  Web タイプのクライアント認証情報）
- 認可URLの生成（**CSRF 対策の ``state`` を ``secrets.token_urlsafe(32)`` で生成**）
- 認可コードからのトークン交換とディスクへの永続化
- 既存トークンの読み込み
- 期限切れトークンの自動リフレッシュ

すべての保存先・読み込み元は ``app.config.Settings`` 経由で解決する
（直接 ``%APPDATA%`` を参照しない）。

リダイレクトURIは requirements.md §8.5 に従い
``http://localhost:8000/api/auth/google/callback`` 固定。
``http://`` のため google-auth-oauthlib の "insecure transport" チェックを
モジュール初期化時に解除する（プロトタイプ・ローカルホスト前提）。
"""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from app.config import Settings, get_settings


# requirements.md §2.1 必須スコープ
SCOPES: list[str] = [
    "https://www.googleapis.com/auth/forms.body",
    "https://www.googleapis.com/auth/forms.responses.readonly",
    "https://www.googleapis.com/auth/drive.file",
]

# requirements.md §8.5 固定 URI（GCP コンソール側にも同じ URI を登録すること）
REDIRECT_URI: str = "http://localhost:8000/api/auth/google/callback"

# state パラメータの推奨長（バイト数）。``secrets.token_urlsafe(32)`` で
# 43 文字程度の base64url 文字列を得る
STATE_BYTES: int = 32

CLIENT_CONFIG_FILENAME = "oauth_client.json"
TOKEN_FILENAME = "oauth_token.json"

# ``http://localhost`` での OAuth2 を許可（プロトタイプのみ）。
# requirements.md §8.5 に準拠したローカル開発向けの暫定設定。
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

# Google は ``include_granted_scopes=true`` 利用時や同意済みアカウントに対し、
# 要求した SCOPES に加えて ``openid`` / ``email`` / ``profile`` 等を勝手に返す
# ことがある。oauthlib は既定でこのスコープ差分を例外化するため、
# プロトタイプではトークンスコープを緩める。
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")


# ---------------------------------------------------------------------------
# パス解決
# ---------------------------------------------------------------------------

def _client_config_path(settings: Optional[Settings] = None) -> Path:
    """``oauth_client.json`` の絶対パスを返す。"""
    s = settings or get_settings()
    return s.config_dir / CLIENT_CONFIG_FILENAME


def _token_path(settings: Optional[Settings] = None) -> Path:
    """``oauth_token.json`` の絶対パスを返す。"""
    s = settings or get_settings()
    return s.config_dir / TOKEN_FILENAME


# ---------------------------------------------------------------------------
# Flow / Credentials の組み立て
# ---------------------------------------------------------------------------

def _load_client_config() -> dict:
    """``oauth_client.json`` を辞書として読み込む。

    ``Flow.from_client_config`` に渡せる形のまま返す（``web`` または
    ``installed`` キーを持つ辞書）。

    Raises:
        FileNotFoundError: ファイルが存在しない場合。GCP セットアップ未済。
    """
    path = _client_config_path()
    if not path.exists():
        raise FileNotFoundError(
            f"oauth_client.json not found at {path}. "
            "README の『GCP セットアップ』を参照しダウンロード＆配置してください。"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _build_flow(state: Optional[str] = None) -> Flow:
    """``google_auth_oauthlib.flow.Flow`` を組み立てる。

    Args:
        state: 認可リクエスト/コールバック検証で使用する state。コールバック
            処理時には認可開始時に保存した値を渡す（同一 Flow を再構築する形）。
    """
    client_config = _load_client_config()
    return Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
        state=state,
    )


def _save_credentials(creds: Credentials) -> Path:
    """``Credentials`` を ``oauth_token.json`` に永続化する。

    google-auth の ``to_json()`` は ``token``/``refresh_token``/``expiry`` を
    含む JSON 文字列を返す。``from_authorized_user_*`` でラウンドトリップ可能。
    """
    settings = get_settings()
    settings.ensure_directories()
    path = _token_path(settings)
    path.write_text(creds.to_json(), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# 公開 API
# ---------------------------------------------------------------------------

def build_authorization_url() -> tuple[str, str, str | None]:
    """認可URLとセッションに保存すべき state / code_verifier を返す。

    CSRF 対策のため state は ``secrets.token_urlsafe`` で生成し、本サービス
    側で明示的に渡す（``Flow.authorization_url`` の自動生成値には依存しない）。

    ``google-auth-oauthlib`` の Flow は PKCE の ``code_verifier`` を自動生成し、
    対応する ``code_challenge`` を認可URLに含める。トークン交換時に Google が
    verifier を要求するため、生成された verifier も呼び出し側で保管する必要がある。

    Returns:
        ``(url, state, code_verifier)``。呼び出し側は ``state`` と
        ``code_verifier`` をサーバ側セッションに保存し、コールバック時に
        ``exchange_code_for_token`` へ渡す責務を負う。
        PKCE が無効な場合 ``code_verifier`` は ``None``。
    """
    flow = _build_flow()
    state = secrets.token_urlsafe(STATE_BYTES)
    url, _returned_state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    # Flow が自動生成した verifier を取り出す（属性が無い場合は None）
    code_verifier = getattr(flow, "code_verifier", None)
    return url, state, code_verifier


def exchange_code_for_token(
    *,
    code: str,
    state: str,
    code_verifier: Optional[str] = None,
) -> Credentials:
    """認可コードをトークンに交換し ``oauth_token.json`` に保存する。

    Args:
        code: Google から付与された認可コード（クエリパラメータ ``code``）。
        state: 認可開始時に生成した state。``Flow`` の再構築に使用する。
        code_verifier: 認可開始時に生成した PKCE verifier。``None`` 可
            （PKCE 無効時）。Google が要求するため、認可URLに ``code_challenge``
            が含まれていた場合は必須。

    Returns:
        取得した ``Credentials``。
    """
    flow = _build_flow(state=state)
    if code_verifier is not None:
        # 認可開始時の verifier を復元してから fetch_token を呼ぶ。
        # Flow は自分の ``code_verifier`` 属性を見て送信する。
        flow.code_verifier = code_verifier
    flow.fetch_token(code=code)
    creds = flow.credentials
    _save_credentials(creds)
    return creds


def load_credentials() -> Optional[Credentials]:
    """ディスクから ``Credentials`` を読み出す。

    Returns:
        ``Credentials`` インスタンス。``oauth_token.json`` が無い場合は ``None``。
    """
    path = _token_path()
    if not path.exists():
        return None
    info = json.loads(path.read_text(encoding="utf-8"))
    # ``from_authorized_user_info`` は token, refresh_token, token_uri,
    # client_id, client_secret, scopes, expiry を解釈する。
    return Credentials.from_authorized_user_info(info, scopes=SCOPES)


def get_valid_credentials() -> Optional[Credentials]:
    """有効な ``Credentials`` を返す。期限切れなら自動リフレッシュ＋保存。

    リフレッシュトークンが無い・期限切れの場合は呼び出し側で再認可を促す。
    """
    creds = load_credentials()
    if creds is None:
        return None
    if creds.expired and creds.refresh_token:
        creds.refresh(GoogleAuthRequest())
        _save_credentials(creds)
    return creds


def is_authenticated() -> bool:
    """有効な Credentials が存在するか（リフレッシュ可能性含む）を返す。"""
    creds = load_credentials()
    if creds is None:
        return False
    # 期限内、もしくはリフレッシュトークンがあれば実質的に認証済みとみなす
    if not creds.expired:
        return True
    return bool(creds.refresh_token)


__all__ = [
    "SCOPES",
    "REDIRECT_URI",
    "build_authorization_url",
    "exchange_code_for_token",
    "load_credentials",
    "get_valid_credentials",
    "is_authenticated",
]
