"""Repository 骨格のスモークテスト（Phase 1.2）。

本フェーズは骨格のみのため、TDD の対象外（implementation_prompts_subdivided.md
Phase 1.2 §テスト駆動「本サブステップは対象外（骨格のみ）」）。

検証する観点:
    1. 抽象基底クラスが ABC として正しく定義されており、直接インスタンス化できないこと
    2. ファイル実装クラスが抽象基底を継承していること
    3. ファイル実装クラスがインスタンス化できること
    4. 骨格メソッドが ``NotImplementedError`` を送出すること
    5. DI プロバイダがファイル実装を返すこと
"""

from __future__ import annotations

import pytest

from app.dependencies import (
    get_draft_repository,
    get_project_repository,
    get_response_repository,
    get_rule_repository,
    get_settings_dependency,
)
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


# ---------------------------------------------------------------------------
# 1. ABC として直接インスタンス化できないこと
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "abstract_cls",
    [ProjectRepository, RuleRepository, ResponseRepository, DraftRepository],
)
def test_abstract_repository_cannot_be_instantiated(abstract_cls) -> None:
    """抽象基底クラスは直接 ``__init__`` できない。"""
    with pytest.raises(TypeError):
        abstract_cls()  # type: ignore[abstract,call-arg]


# ---------------------------------------------------------------------------
# 2. ファイル実装が抽象基底を継承していること
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "file_cls, abstract_cls",
    [
        (FileProjectRepository, ProjectRepository),
        (FileRuleRepository, RuleRepository),
        (FileResponseRepository, ResponseRepository),
        (FileDraftRepository, DraftRepository),
    ],
)
def test_file_repository_subclasses_abstract(file_cls, abstract_cls) -> None:
    """ファイル実装は対応する抽象基底のサブクラス。"""
    assert issubclass(file_cls, abstract_cls)


# ---------------------------------------------------------------------------
# 3. ファイル実装がインスタンス化できること
# ---------------------------------------------------------------------------


def test_file_project_repository_can_instantiate() -> None:
    repo = get_project_repository()
    assert isinstance(repo, ProjectRepository)
    assert isinstance(repo, FileProjectRepository)


def test_file_rule_repository_can_instantiate() -> None:
    repo = get_rule_repository()
    assert isinstance(repo, RuleRepository)
    assert isinstance(repo, FileRuleRepository)


def test_file_response_repository_can_instantiate() -> None:
    repo = get_response_repository()
    assert isinstance(repo, ResponseRepository)
    assert isinstance(repo, FileResponseRepository)


def test_file_draft_repository_can_instantiate() -> None:
    repo = get_draft_repository()
    assert isinstance(repo, DraftRepository)
    assert isinstance(repo, FileDraftRepository)


# ---------------------------------------------------------------------------
# 4. 骨格メソッドが NotImplementedError を送出すること
# ---------------------------------------------------------------------------
#
# Phase 2.1 で FileProjectRepository は本実装に置き換えられたため、骨格テストは
# 削除し、本格テストは tests/test_project_api.py が担う。
# Phase 2.3 で FileResponseRepository も本実装に置き換えられたため、骨格テストは
# 削除し、本格テストは tests/test_responses_api.py / tests/test_polling.py が担う。
# FileRuleRepository / FileDraftRepository は引き続き
# 骨格のままなので、NotImplementedError チェックを残す。


def test_rule_repository_methods_raise_not_implemented() -> None:
    repo = get_rule_repository()
    with pytest.raises(NotImplementedError):
        repo.get_global_rules()
    with pytest.raises(NotImplementedError):
        repo.get_project_rules("dummy")
    with pytest.raises(NotImplementedError):
        repo.copy_global_to_project("dummy")


def test_draft_repository_methods_raise_not_implemented() -> None:
    repo = get_draft_repository()
    with pytest.raises(NotImplementedError):
        repo.get_latest("dummy")
    with pytest.raises(NotImplementedError):
        repo.unlock_latest("dummy")
    with pytest.raises(NotImplementedError):
        repo.list_all("dummy")


# ---------------------------------------------------------------------------
# 5. 設定 DI プロバイダ
# ---------------------------------------------------------------------------


def test_get_settings_dependency_returns_singleton() -> None:
    """``get_settings_dependency`` は ``get_settings()`` と同一インスタンスを返す。"""
    from app.config import get_settings

    assert get_settings_dependency() is get_settings()


# ---------------------------------------------------------------------------
# 6. ファイル実装が settings に基づくパスを保持していること
# ---------------------------------------------------------------------------


def test_file_repository_uses_settings_paths(isolated_data_root) -> None:
    """ファイル実装が ``settings.projects_dir`` / ``config_dir`` を参照する。"""
    repo = get_project_repository()
    assert isinstance(repo, FileProjectRepository)
    # _SettingsBacked 経由で projects_dir / config_dir を取得できる
    assert repo.projects_dir == isolated_data_root / "projects"
    assert repo.config_dir == isolated_data_root / "config"
