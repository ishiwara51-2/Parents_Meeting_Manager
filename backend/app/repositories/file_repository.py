"""ファイルベース Repository 実装の骨格。

各クラスは ``app.repositories.base`` の抽象基底を継承し、``%APPDATA%\\meeting-scheduler``
配下のJSONファイル群に対する CRUD を提供する（requirements.md §3.1 / §6）。

本フェーズ（Phase 1.2）では各メソッドを ``raise NotImplementedError`` で骨格のみ実装する。
具象実装は後続フェーズで行う：

- ``FileProjectRepository``  → Phase 2.1
- ``FileResponseRepository`` → Phase 2.3
- ``FileRuleRepository``     → Phase 3.1
- ``FileDraftRepository``    → Phase 3.4

クラス共通の初期化として ``Settings`` を受け取り、``settings.projects_dir`` /
``settings.config_dir`` を基点にファイル操作を行う。
"""

from __future__ import annotations

from pathlib import Path

from app.config import Settings
from app.models.draft import Draft
from app.models.project import Project
from app.models.response import Response
from app.models.rules import Rules
from app.repositories.base import (
    DraftRepository,
    ProjectRepository,
    ResponseRepository,
    RuleRepository,
)


class _SettingsBacked:
    """Settings を共有する mixin。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def projects_dir(self) -> Path:
        """``<APP_DATA_ROOT>\\projects`` を返す（requirements.md §3.1）。"""
        return self._settings.projects_dir

    @property
    def config_dir(self) -> Path:
        """``<APP_DATA_ROOT>\\config`` を返す（requirements.md §3.1）。"""
        return self._settings.config_dir


class FileProjectRepository(_SettingsBacked, ProjectRepository):
    """``<APP_DATA_ROOT>\\projects\\<project_id>`` 配下にファイルとしてプロジェクトを永続化する。

    本フェーズは骨格のみ。実装は Phase 2.1。
    """

    def list_all(self) -> list[Project]:
        raise NotImplementedError("Phase 2.1 で実装")

    def get(self, project_id: str) -> Project | None:
        raise NotImplementedError("Phase 2.1 で実装")

    def create(self, project: Project) -> Project:
        raise NotImplementedError("Phase 2.1 で実装")

    def update(self, project: Project) -> Project:
        raise NotImplementedError("Phase 2.1 で実装")

    def delete(self, project_id: str) -> None:
        raise NotImplementedError("Phase 2.1 で実装")

    def get_project_dir(self, project_id: str) -> Path:
        raise NotImplementedError("Phase 2.1 で実装")


class FileRuleRepository(_SettingsBacked, RuleRepository):
    """グローバルルールとプロジェクトルールをファイルで永続化する。

    本フェーズは骨格のみ。実装は Phase 3.1。
    """

    def get_global_rules(self) -> Rules:
        raise NotImplementedError("Phase 3.1 で実装")

    def set_global_rules(self, rules: Rules) -> Rules:
        raise NotImplementedError("Phase 3.1 で実装")

    def get_project_rules(self, project_id: str) -> Rules:
        raise NotImplementedError("Phase 3.1 で実装")

    def set_project_rules(self, project_id: str, rules: Rules) -> Rules:
        raise NotImplementedError("Phase 3.1 で実装")

    def copy_global_to_project(self, project_id: str) -> Rules:
        raise NotImplementedError("Phase 3.1 で実装")


class FileResponseRepository(_SettingsBacked, ResponseRepository):
    """Form 回答をプロジェクト配下にファイル保存する。

    本フェーズは骨格のみ。実装は Phase 2.3。
    """

    def save_response(self, project_id: str, response: Response) -> Path:
        raise NotImplementedError("Phase 2.3 で実装")

    def list_latest_per_student(self, project_id: str) -> list[Response]:
        raise NotImplementedError("Phase 2.3 で実装")

    def list_all(self, project_id: str) -> list[Response]:
        raise NotImplementedError("Phase 2.3 で実装")

    def get_received_student_numbers(self, project_id: str) -> set[int]:
        raise NotImplementedError("Phase 2.3 で実装")

    def get_pending_student_numbers(self, project_id: str) -> set[int]:
        raise NotImplementedError("Phase 2.3 で実装")

    def get_known_form_response_ids(self, project_id: str) -> set[str]:
        raise NotImplementedError("Phase 2.3 で実装")


class FileDraftRepository(_SettingsBacked, DraftRepository):
    """ドラフトを ``<project_dir>\\drafts\\draft_<timestamp>.json`` として永続化する。

    本フェーズは骨格のみ。実装は Phase 3.4。
    """

    def save_draft(self, project_id: str, draft: Draft) -> Path:
        raise NotImplementedError("Phase 3.4 で実装")

    def get_latest(self, project_id: str) -> Draft | None:
        raise NotImplementedError("Phase 3.4 で実装")

    def unlock_latest(self, project_id: str) -> Draft:
        raise NotImplementedError("Phase 3.4 で実装")

    def list_all(self, project_id: str) -> list[Draft]:
        raise NotImplementedError("Phase 3.4 で実装")


__all__ = [
    "FileProjectRepository",
    "FileRuleRepository",
    "FileResponseRepository",
    "FileDraftRepository",
]
