"""アプリケーション設定モジュール。

requirements.md §3.1 / §8.1 / §8.4 に従い、以下を管理する。

- アプリ用データルート（`%APPDATA%\\meeting-scheduler\\` 既定。
  環境変数 `MEETING_SCHEDULER_DATA_ROOT` でオーバーライド可能（テスト用））
- 起動ポート（環境変数 `MEETING_SCHEDULER_PORT`、既定 8000）
- 起動時のデータディレクトリ自動作成（`config/`、`projects/`）

パス操作はすべて ``pathlib.Path`` を使用し、文字列リテラルでパス区切りを
直書きしない（requirements.md §3.3 / §8.1）。
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


DEFAULT_PORT = 8000
ENV_DATA_ROOT = "MEETING_SCHEDULER_DATA_ROOT"
ENV_PORT = "MEETING_SCHEDULER_PORT"
APP_DIR_NAME = "meeting-scheduler"


def _resolve_app_data_root() -> Path:
    """アプリ用データルートの絶対パスを返す。

    優先順位:
        1. 環境変数 ``MEETING_SCHEDULER_DATA_ROOT`` が指定されていればそれを使用
        2. それ以外は ``%APPDATA%\\meeting-scheduler``
        3. ``%APPDATA%`` が未定義の場合は ``~/.meeting-scheduler`` をフォールバック

    Returns:
        Path: アプリ用データルートの ``Path``。
    """
    override = os.getenv(ENV_DATA_ROOT)
    if override:
        return Path(override)

    appdata = os.getenv("APPDATA")
    if appdata:
        return Path(appdata) / APP_DIR_NAME

    # 非Windows環境やAPPDATA未定義時のフォールバック
    return Path.home() / f".{APP_DIR_NAME}"


def _resolve_port() -> int:
    """起動ポートを環境変数から取得する。

    Returns:
        int: ポート番号。``MEETING_SCHEDULER_PORT`` が無効な値の場合は既定値。
    """
    raw = os.getenv(ENV_PORT)
    if not raw:
        return DEFAULT_PORT
    try:
        return int(raw)
    except ValueError:
        return DEFAULT_PORT


class Settings:
    """アプリ設定。起動時に1度だけ生成される想定。"""

    def __init__(self) -> None:
        self.app_data_root: Path = _resolve_app_data_root()
        self.config_dir: Path = self.app_data_root / "config"
        self.projects_dir: Path = self.app_data_root / "projects"
        self.port: int = _resolve_port()

    def ensure_directories(self) -> None:
        """データディレクトリを存在しない場合は作成する。

        ``config/`` および ``projects/`` を冪等に作成する。
        """
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.projects_dir.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """シングルトンとして Settings を取得する。

    ``lru_cache`` により同一プロセス内ではキャッシュされる。
    テストで設定をリセットしたい場合は ``get_settings.cache_clear()`` を呼ぶ。
    """
    return Settings()
