"""pytest 共通フィクスチャ。

テスト中は ``MEETING_SCHEDULER_DATA_ROOT`` を一時ディレクトリに向け、
実環境の ``%APPDATA%\\meeting-scheduler`` に副作用を残さないようにする。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

import pytest

from app import config as app_config


@pytest.fixture(autouse=True)
def isolated_data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """各テスト毎にデータルートを一時ディレクトリへ切り替える。

    Yields:
        Path: 当該テストで使用するデータルートディレクトリ。
    """
    monkeypatch.setenv(app_config.ENV_DATA_ROOT, str(tmp_path))
    # 設定キャッシュをクリアして環境変数を反映させる
    app_config.get_settings.cache_clear()
    try:
        yield tmp_path
    finally:
        app_config.get_settings.cache_clear()
        # 念のため環境変数の残骸を消す
        os.environ.pop(app_config.ENV_DATA_ROOT, None)
