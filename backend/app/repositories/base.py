"""Repository 抽象基底クラス。

requirements.md §6 末尾「データアクセスは Repository パターンで抽象化し、ファイルベース
実装を後でDB実装に差し替え可能にすること」に従い、データアクセスを抽象化する。

各 Repository は ABC として宣言し、後続フェーズ（Phase 2.1 / 2.3 / 3.1 / 3.4 等）で
具象実装が ``raise NotImplementedError`` を本実装に置き換える。

メソッドシグネチャは ``requirements.md §3.2``（データスキーマ）と ``§6``（API一覧）から
導出している。本フェーズは骨格のみで、実装本体は持たない。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.models.draft import Draft
from app.models.project import Project
from app.models.response import Response
from app.models.rules import Rules


class ProjectRepository(ABC):
    """プロジェクトのCRUD抽象化。

    Phase 2.1 で ``FileProjectRepository`` が本実装を提供する。
    """

    @abstractmethod
    def list_all(self) -> list[Project]:
        """全プロジェクトを取得する（作成日時降順を想定）。"""

    @abstractmethod
    def get(self, project_id: str) -> Project | None:
        """指定 ID のプロジェクトを取得する。存在しない場合は ``None``。"""

    @abstractmethod
    def create(self, project: Project) -> Project:
        """プロジェクトを新規作成する。

        プロジェクトディレクトリ・サブディレクトリ（``responses/``, ``drafts/``,
        ``output/``）の生成、および ``rules.json`` のグローバルルール複製は
        実装側の責務とする（requirements.md §3.1 / Phase 2.1）。
        """

    @abstractmethod
    def update(self, project: Project) -> Project:
        """既存プロジェクトのメタ情報を更新する。"""

    @abstractmethod
    def delete(self, project_id: str) -> None:
        """プロジェクトとその配下を削除する。"""

    @abstractmethod
    def get_project_dir(self, project_id: str) -> Path:
        """プロジェクトディレクトリの絶対パスを返す（存在保証はしない）。"""


class RuleRepository(ABC):
    """ルール（グローバル/プロジェクト）の永続化抽象化。

    Phase 3.1 で ``FileRuleRepository`` が本実装を提供する。
    グローバルルールは ``%APPDATA%\\meeting-scheduler\\config\\global_rules.json``、
    プロジェクトルールは ``<project_dir>\\rules.json`` に格納される
    （requirements.md §3.1）。
    """

    @abstractmethod
    def get_global_rules(self) -> Rules:
        """グローバルルールを取得する。未作成時は既定値で初期化する想定。"""

    @abstractmethod
    def set_global_rules(self, rules: Rules) -> Rules:
        """グローバルルールを上書き保存する。"""

    @abstractmethod
    def get_project_rules(self, project_id: str) -> Rules:
        """プロジェクトルールを取得する。"""

    @abstractmethod
    def set_project_rules(self, project_id: str, rules: Rules) -> Rules:
        """プロジェクトルールを上書き保存する。"""

    @abstractmethod
    def copy_global_to_project(self, project_id: str) -> Rules:
        """グローバルルールをプロジェクトルールとして複製する。

        プロジェクト新規作成時に呼ばれる（requirements.md §4.5.2）。
        """


class ResponseRepository(ABC):
    """Form 回答の保存・参照抽象化。

    Phase 2.3 で ``FileResponseRepository`` が本実装を提供する。
    保存先は ``<project_dir>\\responses\\<出席番号>\\<YYYYMMDD_HHMMSS>.json``
    （requirements.md §3.1 / §4.4）。
    """

    @abstractmethod
    def save_response(self, project_id: str, response: Response) -> Path:
        """回答1件を保存し、保存先パスを返す。

        同一生徒からの複数回答は別ファイルとして併存し、上書きしない
        （requirements.md §4.4）。
        """

    @abstractmethod
    def list_latest_per_student(self, project_id: str) -> list[Response]:
        """各出席番号の最新回答のみを返す（後続処理用、requirements.md §4.4）。"""

    @abstractmethod
    def list_all(self, project_id: str) -> list[Response]:
        """全回答ファイルを返す（履歴・監査用）。"""

    @abstractmethod
    def get_received_student_numbers(self, project_id: str) -> set[int]:
        """受領済みの出席番号集合を返す。"""

    @abstractmethod
    def get_pending_student_numbers(self, project_id: str) -> set[int]:
        """未受領の出席番号集合を返す（プロジェクトの全生徒 − 受領済み）。"""

    @abstractmethod
    def get_known_form_response_ids(self, project_id: str) -> set[str]:
        """既知の ``google_form_response_id`` 集合（ポーリング重複検知用）。"""


class DraftRepository(ABC):
    """ドラフトの保存・参照・ロック管理抽象化。

    Phase 3.4 で ``FileDraftRepository`` が本実装を提供する。
    保存先は ``<project_dir>\\drafts\\draft_<YYYYMMDD_HHMMSS>.json``
    （requirements.md §3.1 / §4.9）。
    """

    @abstractmethod
    def save_draft(self, project_id: str, draft: Draft) -> Path:
        """ドラフトを保存し、保存先パスを返す（保存時 ``locked=True``）。"""

    @abstractmethod
    def get_latest(self, project_id: str) -> Draft | None:
        """最新ドラフトを返す。存在しない場合は ``None``。"""

    @abstractmethod
    def unlock_latest(self, project_id: str) -> Draft:
        """最新ドラフトのロックを解除する（再編集モード、requirements.md §4.9）。"""

    @abstractmethod
    def list_all(self, project_id: str) -> list[Draft]:
        """全ドラフト（履歴含む）を新しい順で返す。"""


__all__ = [
    "ProjectRepository",
    "RuleRepository",
    "ResponseRepository",
    "DraftRepository",
]
