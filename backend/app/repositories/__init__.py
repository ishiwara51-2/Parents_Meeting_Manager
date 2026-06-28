"""Repository層パッケージ。

抽象基底（``base``）と、ファイルベース実装（``file_repository``）を提供する。
本フェーズ（Phase 1.2）は骨格のみで、具象メソッドは ``NotImplementedError`` を返す。
"""

from __future__ import annotations

from app.repositories.base import (
    DraftRepository,
    ProjectRepository,
    ResponseRepository,
    RuleRepository,
)
from app.repositories.file_repository import (
    FileDraftRepository,
    FileProjectRepository,
    FileResponseRepository,
    FileRuleRepository,
)

__all__ = [
    # base
    "ProjectRepository",
    "RuleRepository",
    "ResponseRepository",
    "DraftRepository",
    # file impl
    "FileProjectRepository",
    "FileRuleRepository",
    "FileResponseRepository",
    "FileDraftRepository",
]
