"""FastAPI 依存性注入（DI）のプロバイダ。

各 Repository を FastAPI の ``Depends`` で注入できるようにする。
テスト時は ``app.dependency_overrides[...] = lambda: stub`` で差し替え可能。

使用例（後続フェーズのルータ実装）::

    from fastapi import APIRouter, Depends
    from app.dependencies import get_project_repository
    from app.repositories.base import ProjectRepository

    router = APIRouter()

    @router.get("/api/projects")
    def list_projects(repo: ProjectRepository = Depends(get_project_repository)):
        return repo.list_all()

設計方針:
    - プロバイダ関数の戻り値型は抽象基底（``ProjectRepository`` 等）とする。
      ファイル実装からDB実装への差し替えを ``app.dependency_overrides`` で行えるようにする
      （requirements.md §6 末尾「ファイルベース実装を後でDB実装に差し替え可能にする」）。
    - 設定は ``get_settings()`` シングルトン経由で取得する（直に環境変数を読まない、
      Phase 1.1 引き継ぎ事項より）。
"""

from __future__ import annotations

from app.config import Settings, get_settings
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


def get_settings_dependency() -> Settings:
    """``Settings`` を返す DI プロバイダ。

    既存の ``get_settings()`` をラップしてあるのは、FastAPI の依存性を
    プロバイダ関数として明示するため。
    """
    return get_settings()


def get_project_repository() -> ProjectRepository:
    """``ProjectRepository`` の既定実装（ファイルベース）を返す。"""
    return FileProjectRepository(get_settings())


def get_rule_repository() -> RuleRepository:
    """``RuleRepository`` の既定実装（ファイルベース）を返す。"""
    return FileRuleRepository(get_settings())


def get_response_repository() -> ResponseRepository:
    """``ResponseRepository`` の既定実装（ファイルベース）を返す。"""
    return FileResponseRepository(get_settings())


def get_draft_repository() -> DraftRepository:
    """``DraftRepository`` の既定実装（ファイルベース）を返す。"""
    return FileDraftRepository(get_settings())


__all__ = [
    "get_settings_dependency",
    "get_project_repository",
    "get_rule_repository",
    "get_response_repository",
    "get_draft_repository",
]
