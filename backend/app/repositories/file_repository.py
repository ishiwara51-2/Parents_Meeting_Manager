"""ファイルベース Repository 実装。

各クラスは ``app.repositories.base`` の抽象基底を継承し、``%APPDATA%\\meeting-scheduler``
配下のJSONファイル群に対する CRUD を提供する（requirements.md §3.1 / §6）。

実装状況（フェーズ進行に合わせて NotImplementedError を本実装へ置き換え）:

- ``FileProjectRepository``  → **Phase 2.1 で本実装（本フェーズ）**
- ``FileResponseRepository`` → Phase 2.3 で本実装
- ``FileRuleRepository``     → Phase 3.1 で本実装。本フェーズでは ``copy_global_to_project``
  の最小実装のみ（プロジェクト作成時の rules.json 初期化用）
- ``FileDraftRepository``    → Phase 3.4 で本実装

クラス共通の初期化として ``Settings`` を受け取り、``settings.projects_dir`` /
``settings.config_dir`` を基点にファイル操作を行う。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from app.config import Settings
from app.models.draft import Draft
from app.models.project import Project
from app.models.response import Response
from app.models.rules import GlobalConstraints, Rules
from app.repositories.base import (
    DraftRepository,
    ProjectRepository,
    ResponseRepository,
    RuleRepository,
)


# ---------------------------------------------------------------------------
# 既定のグローバルルール（Phase 2.1）
# ---------------------------------------------------------------------------
# Phase 2.1 ではグローバルルール管理 API（Phase 3.1）が未実装のため、
# プロジェクト作成時に既存の global_rules.json があればコピーし、無ければ
# 「ハードコードされた既定値」で rules.json を初期化する。
#
# 既定値は requirements.md §3.2 / §4.5 のサンプル相当：
#   - max_consecutive_slots: 4
#   - forced_break_slots: 1
#   - max_slots_per_day: 20
#   - teacher_unavailable: []
#   - student_constraints: []
#
# Phase 3.1 でグローバルルール API が実装された後は、本既定値は
# ``FileRuleRepository.get_global_rules()`` 側の初期化フォールバックに
# 移管される想定。

_DEFAULT_RULES = Rules(
    global_constraints=GlobalConstraints(
        max_consecutive_slots=4,
        forced_break_slots=1,
        max_slots_per_day=20,
        teacher_unavailable=[],
    ),
    student_constraints=[],
)


def _write_json(path: Path, data: dict) -> None:
    """JSON を UTF-8 (BOM なし) で書き出すヘルパ。

    requirements.md §8.3 に従い、ソースコードと同様 BOM なし UTF-8 で永続化する。
    日本語キー・値を扱うため ``ensure_ascii=False`` で保存。
    """
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict:
    """JSON を UTF-8 として読み出すヘルパ。"""
    return json.loads(path.read_text(encoding="utf-8"))


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

    Phase 2.1 本実装。

    ディレクトリ構造（requirements.md §3.1）::

        <projects_dir>\\<project_id>\\
        ├── project.json
        ├── rules.json
        ├── responses\\
        ├── drafts\\
        └── output\\
    """

    PROJECT_FILE_NAME = "project.json"
    RULES_FILE_NAME = "rules.json"
    GLOBAL_RULES_FILE_NAME = "global_rules.json"
    SUBDIR_NAMES = ("responses", "drafts", "output")

    def get_project_dir(self, project_id: str) -> Path:
        """プロジェクトディレクトリの絶対パス。存在保証はしない。"""
        return self.projects_dir / project_id

    def _project_json_path(self, project_id: str) -> Path:
        return self.get_project_dir(project_id) / self.PROJECT_FILE_NAME

    def list_all(self) -> list[Project]:
        """全プロジェクトを ``created_at`` 降順で返す。"""
        if not self.projects_dir.exists():
            return []

        projects: list[Project] = []
        for child in self.projects_dir.iterdir():
            if not child.is_dir():
                continue
            project_json = child / self.PROJECT_FILE_NAME
            if not project_json.is_file():
                # project.json を持たないディレクトリはスキップ
                continue
            try:
                projects.append(Project.model_validate(_read_json(project_json)))
            except Exception:
                # 壊れた project.json はスキップ（プロトタイプ運用として許容）
                continue

        # 作成日時降順（後に作成したものが先頭）
        projects.sort(key=lambda p: p.created_at, reverse=True)
        return projects

    def get(self, project_id: str) -> Project | None:
        """指定 ID のプロジェクトを取得する。存在しない場合は ``None``。"""
        path = self._project_json_path(project_id)
        if not path.is_file():
            return None
        return Project.model_validate(_read_json(path))

    def create(self, project: Project) -> Project:
        """プロジェクトを新規作成する。

        - ``<projects_dir>/<project_id>/`` を作成（既存なら ``FileExistsError``）
        - サブディレクトリ ``responses/``, ``drafts/``, ``output/`` を作成
        - ``project.json`` を書き出す
        - ``rules.json`` を初期化する（グローバルルールがあれば複製、無ければ既定値）
        """
        project_dir = self.get_project_dir(project.project_id)
        if project_dir.exists():
            raise FileExistsError(
                f"project_id '{project.project_id}' は既に存在します"
            )

        # プロジェクト本体ディレクトリ＋サブディレクトリ
        project_dir.mkdir(parents=True, exist_ok=False)
        for sub in self.SUBDIR_NAMES:
            (project_dir / sub).mkdir(parents=True, exist_ok=False)

        # project.json
        _write_json(
            self._project_json_path(project.project_id),
            project.model_dump(mode="json"),
        )

        # rules.json（グローバルルールがあれば複製、無ければ既定）
        self._initialize_project_rules(project.project_id)

        return project

    def update(self, project: Project) -> Project:
        """既存プロジェクトのメタ情報を更新する。

        ``project_id`` で対象を特定。存在しない場合は ``FileNotFoundError``。
        ``project.json`` を全置換する（部分更新はサービス層で行う）。
        """
        path = self._project_json_path(project.project_id)
        if not path.is_file():
            raise FileNotFoundError(
                f"project_id '{project.project_id}' は存在しません"
            )
        _write_json(path, project.model_dump(mode="json"))
        return project

    def delete(self, project_id: str) -> None:
        """プロジェクトディレクトリを配下も含め再帰削除する。

        存在しない場合は ``FileNotFoundError``。
        """
        project_dir = self.get_project_dir(project_id)
        if not project_dir.exists():
            raise FileNotFoundError(
                f"project_id '{project_id}' は存在しません"
            )
        shutil.rmtree(project_dir)

    # ------------------------------------------------------------------
    # 内部ユーティリティ
    # ------------------------------------------------------------------

    def _initialize_project_rules(self, project_id: str) -> None:
        """プロジェクト作成時の ``rules.json`` 初期化。

        Phase 2.1 暫定実装：

        - グローバルルール (``<config_dir>/global_rules.json``) が存在すれば内容を複製
        - 存在しなければ ``_DEFAULT_RULES`` を書き出す

        Phase 3.1 で ``FileRuleRepository.copy_global_to_project()`` 本実装に
        移管されたら、本処理は API ハンドラ側からその呼び出しに置換される想定
        （依存方向：API → RuleRepository）。
        """
        rules_path = self.get_project_dir(project_id) / self.RULES_FILE_NAME
        global_rules_path = self.config_dir / self.GLOBAL_RULES_FILE_NAME

        if global_rules_path.is_file():
            # 既存グローバルルールを Rules モデル経由で検証してから書き戻す
            try:
                rules = Rules.model_validate(_read_json(global_rules_path))
            except Exception:
                # 壊れていれば既定値で初期化
                rules = _DEFAULT_RULES
        else:
            rules = _DEFAULT_RULES

        _write_json(rules_path, rules.model_dump(mode="json"))


class FileRuleRepository(_SettingsBacked, RuleRepository):
    """グローバルルールとプロジェクトルールをファイルで永続化する。

    本フェーズ（Phase 2.1）では Phase 3.1 で実装するメソッドの骨格を維持する。
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
