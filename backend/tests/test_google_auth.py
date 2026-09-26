"""Phase 1.3: Google OAuth2 認証フローのテスト。

requirements.md §2.1 / implementation_prompts_subdivided.md Phase 1.3 §テスト に従い、
以下7項目を検証する。

1. 認可URL生成が必須スコープと state を含むこと
2. 認可コードからトークンを取得・保存できること（モック）
3. 既存トークンを読み込めること
4. 期限切れトークンが自動リフレッシュされること（モック）
5. 未認証時に /api/auth/status が unauthorized を返すこと
6. state 不一致時にコールバックが 400 を返すこと
7. state がセッションに保存されていない場合にも 400 を返すこと

OAuth フローの「実 Google 通信」はモック（``unittest.mock``）で偽装し、
``%APPDATA%`` を汚さないため ``isolated_data_root`` を継承した
``fake_oauth_client`` フィクスチャで一時 config ディレクトリへダミーの
``oauth_client.json`` を書き出す。
"""

from __future__ import annotations

import base64
import datetime as _dt
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app


REQUIRED_SCOPES = [
    "https://www.googleapis.com/auth/forms.body",
    "https://www.googleapis.com/auth/forms.responses.readonly",
    "https://www.googleapis.com/auth/drive.file",
]


@pytest.fixture
def fake_oauth_client(isolated_data_root: Path) -> Path:
    """テスト用の偽 oauth_client.json を config_dir に配置する。

    実機の GCP クライアント認証情報を読まないようにするため、
    各テストで隔離された ``tmp_path`` 配下に書き出す。
    """
    settings = get_settings()
    settings.ensure_directories()
    client_path = settings.config_dir / "oauth_client.json"
    client_path.write_text(
        json.dumps(
            {
                "web": {
                    "client_id": "fake-client.apps.googleusercontent.com",
                    "client_secret": "fake-secret",
                    "redirect_uris": [
                        "http://localhost:8000/api/auth/google/callback"
                    ],
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "auth_provider_x509_cert_url": (
                        "https://www.googleapis.com/oauth2/v1/certs"
                    ),
                }
            }
        ),
        encoding="utf-8",
    )
    return client_path


def _make_fake_id_token(*, email: str) -> str:
    """署名検証なし（``verify=False``）でデコード可能なダミー ID トークンを作る。

    ``_extract_email`` は id_token をサーバー間通信で直接受け取った信頼済みの
    ものとして署名検証せずデコードするため、テストでも実際の RS256 署名は不要。
    """

    def _b64(obj: dict) -> bytes:
        return base64.urlsafe_b64encode(json.dumps(obj).encode("utf-8")).rstrip(b"=")

    header = _b64({"alg": "RS256", "typ": "JWT"})
    payload = _b64({"email": email, "sub": "123456"})
    return (header + b"." + payload + b"." + b"fake-signature").decode("ascii")


def _make_credentials_json(*, token: str, expired: bool) -> str:
    """テスト用の oauth_token.json 相当の JSON 文字列を組み立てる。

    google-auth の ``Credentials.to_json()`` と互換のキーで書く。
    """
    from google.oauth2.credentials import Credentials

    now = _dt.datetime.utcnow()
    expiry = now - _dt.timedelta(hours=1) if expired else now + _dt.timedelta(hours=1)
    creds = Credentials(
        token=token,
        refresh_token="stored-refresh-token",
        token_uri="https://oauth2.googleapis.com/token",
        client_id="fake-client.apps.googleusercontent.com",
        client_secret="fake-secret",
        scopes=REQUIRED_SCOPES,
        expiry=expiry,
    )
    return creds.to_json()


# ---------- 1. 認可URL生成 ----------

def test_authorization_url_contains_required_scopes_and_state(
    fake_oauth_client: Path,
) -> None:
    """build_authorization_url() は requirements.md §2.1 の必須スコープと state を含む。"""
    from app.services import google_auth

    url, state, _code_verifier = google_auth.build_authorization_url()

    # 必須スコープ（URL エンコードされていても部分文字列で検出可能）
    assert "forms.body" in url
    assert "forms.responses.readonly" in url
    assert "drive.file" in url
    # ログイン状態ヘッダーの email 表示用スコープ
    assert "openid" in url
    assert "userinfo.email" in url
    # state パラメータ（CSRF 対策）
    assert "state=" in url
    # secrets.token_urlsafe(32) 由来で 32 文字以上
    assert isinstance(state, str)
    assert len(state) >= 32


# ---------- 2. 認可コードからトークン取得・保存 ----------

def test_exchange_code_saves_token_via_mocked_flow(fake_oauth_client: Path) -> None:
    """``exchange_code_for_token()`` がモック Flow からトークンを取り出し JSON に保存する。"""
    from app.services import google_auth

    settings = get_settings()
    token_path = settings.config_dir / "oauth_token.json"
    assert not token_path.exists()

    fake_creds = MagicMock()
    fake_creds.to_json.return_value = json.dumps(
        {
            "token": "new-access-token",
            "refresh_token": "new-refresh-token",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "fake-client.apps.googleusercontent.com",
            "client_secret": "fake-secret",
            "scopes": REQUIRED_SCOPES,
        }
    )

    fake_flow = MagicMock()
    fake_flow.credentials = fake_creds

    with patch.object(google_auth, "_build_flow", return_value=fake_flow):
        google_auth.exchange_code_for_token(code="dummy-code", state="dummy-state")

    assert fake_flow.fetch_token.called, "fetch_token must be invoked with the auth code"
    assert token_path.exists(), "oauth_token.json must be written to config_dir"

    saved = json.loads(token_path.read_text(encoding="utf-8"))
    assert saved["token"] == "new-access-token"
    assert saved["refresh_token"] == "new-refresh-token"


def test_exchange_code_extracts_and_persists_email_from_id_token(
    fake_oauth_client: Path,
) -> None:
    """id_token の email クレームを oauth_email.json に保存し、後から読み出せる。"""
    from app.services import google_auth

    fake_creds = MagicMock()
    fake_creds.to_json.return_value = json.dumps({"token": "new-access-token"})
    fake_creds.id_token = _make_fake_id_token(email="teacher@example.com")

    fake_flow = MagicMock()
    fake_flow.credentials = fake_creds

    with patch.object(google_auth, "_build_flow", return_value=fake_flow):
        google_auth.exchange_code_for_token(code="dummy-code", state="dummy-state")

    settings = get_settings()
    email_path = settings.config_dir / "oauth_email.json"
    assert email_path.exists()
    assert json.loads(email_path.read_text(encoding="utf-8")) == {
        "email": "teacher@example.com"
    }
    assert google_auth.get_authenticated_email() == "teacher@example.com"


def test_exchange_code_without_id_token_leaves_email_none(
    fake_oauth_client: Path,
) -> None:
    """id_token が無い（email スコープ未許可等）場合は email=None として扱う。"""
    from app.services import google_auth

    fake_creds = MagicMock()
    fake_creds.to_json.return_value = json.dumps({"token": "new-access-token"})
    fake_creds.id_token = None

    fake_flow = MagicMock()
    fake_flow.credentials = fake_creds

    with patch.object(google_auth, "_build_flow", return_value=fake_flow):
        google_auth.exchange_code_for_token(code="dummy-code", state="dummy-state")

    assert google_auth.get_authenticated_email() is None


# ---------- 3. 既存トークンを読み込める ----------

def test_load_existing_token(fake_oauth_client: Path) -> None:
    """ディスク上の oauth_token.json を読み出し Credentials を構築できる。"""
    from app.services import google_auth

    settings = get_settings()
    token_path = settings.config_dir / "oauth_token.json"
    token_path.write_text(
        _make_credentials_json(token="stored-access-token", expired=False),
        encoding="utf-8",
    )

    creds = google_auth.load_credentials()
    assert creds is not None
    assert creds.token == "stored-access-token"
    assert creds.refresh_token == "stored-refresh-token"


# ---------- 4. 期限切れトークンが自動リフレッシュされる ----------

def test_expired_token_is_refreshed_and_persisted(fake_oauth_client: Path) -> None:
    """期限切れトークン読み込み時に refresh が呼ばれ、新しい値が保存される。"""
    from app.services import google_auth

    settings = get_settings()
    token_path = settings.config_dir / "oauth_token.json"
    token_path.write_text(
        _make_credentials_json(token="stored-access-token", expired=True),
        encoding="utf-8",
    )

    def fake_refresh(self, _request):  # type: ignore[no-untyped-def]
        self.token = "refreshed-access-token"
        self.expiry = _dt.datetime.utcnow() + _dt.timedelta(hours=1)

    with patch(
        "google.oauth2.credentials.Credentials.refresh",
        autospec=True,
        side_effect=fake_refresh,
    ) as mock_refresh:
        creds = google_auth.get_valid_credentials()

    assert mock_refresh.called, "expired token should trigger refresh()"
    assert creds is not None
    assert creds.token == "refreshed-access-token"

    saved = json.loads(token_path.read_text(encoding="utf-8"))
    assert saved["token"] == "refreshed-access-token"


# ---------- 4b. リフレッシュ失敗（invalid_scope 等）時は未認証として扱われる ----------

def test_refresh_failure_clears_stored_token(fake_oauth_client: Path) -> None:
    """スコープ変更後の旧トークン等で refresh が RefreshError を送出した場合、

    get_valid_credentials は None を返し、oauth_token.json / oauth_email.json を
    削除する（以後 /api/auth/status が正しく未認証を返すようにするため）。
    """
    from google.auth.exceptions import RefreshError

    from app.services import google_auth

    settings = get_settings()
    token_path = settings.config_dir / "oauth_token.json"
    email_path = settings.config_dir / "oauth_email.json"
    token_path.write_text(
        _make_credentials_json(token="stored-access-token", expired=True),
        encoding="utf-8",
    )
    email_path.write_text(json.dumps({"email": "teacher@example.com"}), encoding="utf-8")

    def fake_refresh(self, _request):  # type: ignore[no-untyped-def]
        raise RefreshError("invalid_scope: Bad Request")

    with patch(
        "google.oauth2.credentials.Credentials.refresh",
        autospec=True,
        side_effect=fake_refresh,
    ):
        creds = google_auth.get_valid_credentials()

    assert creds is None
    assert not token_path.exists()
    assert not email_path.exists()
    assert google_auth.is_authenticated() is False


# ---------- 5. /api/auth/status は未認証時に unauthorized ----------

def test_auth_status_returns_unauthorized_when_no_token(
    isolated_data_root: Path,
) -> None:
    """oauth_token.json が無ければ authenticated=False, email=None を返す。"""
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/api/auth/status")

    assert response.status_code == 200
    assert response.json() == {"authenticated": False, "email": None}


def test_auth_status_returns_email_when_authenticated(
    isolated_data_root: Path,
) -> None:
    """oauth_token.json と oauth_email.json がある場合は email を含めて返す。"""
    settings = get_settings()
    settings.ensure_directories()
    (settings.config_dir / "oauth_token.json").write_text(
        _make_credentials_json(token="stored-access-token", expired=False),
        encoding="utf-8",
    )
    (settings.config_dir / "oauth_email.json").write_text(
        json.dumps({"email": "teacher@example.com"}), encoding="utf-8"
    )

    app = create_app()
    with TestClient(app) as client:
        response = client.get("/api/auth/status")

    assert response.status_code == 200
    assert response.json() == {
        "authenticated": True,
        "email": "teacher@example.com",
    }


# ---------- 8. ログアウト ----------

def test_logout_deletes_stored_credentials_and_email(
    isolated_data_root: Path,
) -> None:
    """POST /api/auth/logout で oauth_token.json / oauth_email.json が削除される。"""
    settings = get_settings()
    settings.ensure_directories()
    token_path = settings.config_dir / "oauth_token.json"
    email_path = settings.config_dir / "oauth_email.json"
    token_path.write_text(
        _make_credentials_json(token="stored-access-token", expired=False),
        encoding="utf-8",
    )
    email_path.write_text(json.dumps({"email": "teacher@example.com"}), encoding="utf-8")

    app = create_app()
    with TestClient(app) as client:
        response = client.post("/api/auth/logout")

    assert response.status_code == 200
    assert response.json() == {"authenticated": False, "email": None}
    assert not token_path.exists()
    assert not email_path.exists()


def test_logout_is_idempotent_when_not_authenticated(
    isolated_data_root: Path,
) -> None:
    """未認証状態で /api/auth/logout を呼んでもエラーにならない。"""
    app = create_app()
    with TestClient(app) as client:
        response = client.post("/api/auth/logout")

    assert response.status_code == 200
    assert response.json() == {"authenticated": False, "email": None}


def test_auth_status_reflects_logout(isolated_data_root: Path) -> None:
    """ログアウト後に /api/auth/status を叩くと未認証を返す。"""
    from app.services import google_auth

    settings = get_settings()
    settings.ensure_directories()
    (settings.config_dir / "oauth_token.json").write_text(
        _make_credentials_json(token="stored-access-token", expired=False),
        encoding="utf-8",
    )
    (settings.config_dir / "oauth_email.json").write_text(
        json.dumps({"email": "teacher@example.com"}), encoding="utf-8"
    )

    app = create_app()
    with TestClient(app) as client:
        assert client.get("/api/auth/status").json()["authenticated"] is True
        client.post("/api/auth/logout")
        status_response = client.get("/api/auth/status")

    assert status_response.json() == {"authenticated": False, "email": None}
    assert google_auth.is_authenticated() is False


# ---------- 6. state 不一致でコールバックが 400 ----------

def test_callback_returns_400_on_state_mismatch(fake_oauth_client: Path) -> None:
    """セッション保存値と受信 state が一致しない場合は 400 を返す（CSRF対策）。"""
    app = create_app()

    fake_flow = MagicMock()
    # build_authorization_url() 内で flow.authorization_url() が呼ばれるが
    # 戻り値は (url, state) のタプル。state はサービス側で別途生成するため
    # 第2要素はダミーで構わない。
    fake_flow.authorization_url.return_value = (
        "https://accounts.google.com/o/oauth2/v2/auth?fake=1",
        "ignored",
    )
    # MagicMock の属性はデフォルトで MagicMock を返し JSON シリアライズできない
    # ため、build_authorization_url() がセッションに保存する code_verifier に
    # JSON 化可能な値を明示しておく。
    fake_flow.code_verifier = "fake-code-verifier"

    with TestClient(app, follow_redirects=False) as client:
        with patch("app.services.google_auth._build_flow", return_value=fake_flow):
            start_resp = client.get("/api/auth/google")
        # サービスが認可URLにリダイレクトすること
        assert start_resp.status_code in (302, 307)

        # 同じ TestClient (セッションクッキー保持) で異なる state を投げる
        bad_resp = client.get(
            "/api/auth/google/callback",
            params={"state": "WRONG_STATE", "code": "dummy-code"},
        )

    assert bad_resp.status_code == 400


# ---------- 7. state がセッションに無い場合も 400 ----------

def test_callback_returns_400_when_state_not_in_session(
    fake_oauth_client: Path,
) -> None:
    """``/api/auth/google`` を経由せずコールバックだけ叩いた場合も 400 を返す。"""
    app = create_app()
    with TestClient(app) as client:
        response = client.get(
            "/api/auth/google/callback",
            params={"state": "ANY_STATE", "code": "dummy-code"},
        )

    assert response.status_code == 400
