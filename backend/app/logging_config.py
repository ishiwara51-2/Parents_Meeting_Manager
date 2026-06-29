"""ロギング設定モジュール。

requirements.md §3.1 の %APPDATA% ディレクトリに従い、
アプリケーションログを ``%APPDATA%\\meeting-scheduler\\logs\\app.log`` に
``RotatingFileHandler`` でローテーションしながら出力する。

利用方法::

    from app.logging_config import configure_logging
    configure_logging()
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging() -> None:
    """アプリケーションのロギングを設定する。

    設定内容:
    - ログファイル: ``%APPDATA%\\meeting-scheduler\\logs\\app.log``
    - RotatingFileHandler: maxBytes=10MB, backupCount=5
    - ログレベル: INFO (環境変数 ``LOG_LEVEL`` があれば優先)
    - フォーマット: 時刻・レベル・ロガー名・メッセージ
    - ログディレクトリ不在時は自動作成

    本関数は複数回呼び出しても安全（RotatingFileHandler 重複追加を防ぐ）。
    """
    root_logger = logging.getLogger()

    # RotatingFileHandler が既に登録済みの場合はスキップ（重複防止）
    if any(isinstance(h, RotatingFileHandler) for h in root_logger.handlers):
        return

    # ログレベル解決（環境変数 LOG_LEVEL → INFO）
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    # ログディレクトリを解決・作成
    appdata = os.getenv("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    log_dir = Path(appdata) / "meeting-scheduler" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "app.log"

    # フォーマッタ
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)-8s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    # RotatingFileHandler (10 MB × 5 世代)
    file_handler = RotatingFileHandler(
        filename=str(log_file),
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    # StreamHandler（コンソール出力）
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root_logger.setLevel(log_level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
