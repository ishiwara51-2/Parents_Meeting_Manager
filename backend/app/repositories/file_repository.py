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
import logging
import shutil
import threading
from pathlib import Path

from app.config import Settings
from app.models.draft import Draft
from app.models.form import FormInfo
from app.models.project import Project
from app.models.response import Response
from app.models.rules import GlobalConstraints, Rules
from app.repositories.base import (
    DraftRepository,
    ProjectRepository,
    ResponseRepository,
    RuleRepository,
)


# Phase 2.3 で polling.py の流儀（``logger = logging.getLogger(__name__)`` 直接利用）に揃える。
# 当初は ``logger_warning(msg)`` という薄いラッパを置いていたが、
# 呼び出し側を ``logger.warning(...)`` に直接置き換えて helper を削除した（idiomatic 化）。
logger = logging.getLogger(__name__)


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
    FORM_FILE_NAME = "form.json"
    GLOBAL_RULES_FILE_NAME = "global_rules.json"
    SUBDIR_NAMES = ("responses", "drafts", "output")

    def get_project_dir(self, project_id: str) -> Path:
        """プロジェクトディレクトリの絶対パス。存在保証はしない。"""
        return self.projects_dir / project_id

    def _project_json_path(self, project_id: str) -> Path:
        return self.get_project_dir(project_id) / self.PROJECT_FILE_NAME

    def _form_json_path(self, project_id: str) -> Path:
        return self.get_project_dir(project_id) / self.FORM_FILE_NAME

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

        # rules.json は API ハンドラから FileRuleRepository.copy_global_to_project()
        # 経由で生成する（Phase 3.1 本実装）。
        # Phase 2.1 の _initialize_project_rules() はここで削除された。

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
    # form.json （Phase 2.2 で追加）
    # ------------------------------------------------------------------

    def has_form(self, project_id: str) -> bool:
        """``<project_dir>/form.json`` が存在するか。

        Phase 2.2 の Form 作成 API で **二重作成防止判定** に使う。
        プロジェクト自体の存在は問わない（呼び出し側で先に判定する想定）。
        """
        return self._form_json_path(project_id).is_file()

    def get_form_info(self, project_id: str) -> FormInfo | None:
        """``form.json`` を読み出して ``FormInfo`` として返す。

        ファイルが無ければ ``None``。Phase 2.3 のポーリング・Form 受領状況 API
        からも参照される想定。
        """
        path = self._form_json_path(project_id)
        if not path.is_file():
            return None
        # populate_by_name=True なので camelCase / snake_case 混在キーをそのまま受け入れる
        return FormInfo.model_validate(_read_json(path))

    def save_form_info(self, project_id: str, form_info: FormInfo) -> Path:
        """``form.json`` を書き出す。

        Phase 2.2 の Form 作成成功直後に呼ばれる。JSON のキー命名は
        ``formId`` / ``responderUri`` / ``editUri``（camelCase）と
        ``student_number_question_id`` / ``row_question_id_by_date`` /
        ``time_slot_labels``（snake_case）の混在で、``by_alias=True`` で
        Forms API 由来キーを再現する。
        """
        path = self._form_json_path(project_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(path, form_info.model_dump(mode="json", by_alias=True))
        return path



class FileRuleRepository(_SettingsBacked, RuleRepository):
    """グローバルルールとプロジェクトルールをファイルで永続化する（Phase 3.1 本実装）。

    ファイル配置（requirements.md §3.1）::

        <config_dir>/global_rules.json          ← グローバルルール
        <projects_dir>/<project_id>/rules.json  ← プロジェクトルール

    グローバルルールはプロジェクト新規作成時に ``copy_global_to_project()`` で
    プロジェクトルールとして複製される（requirements.md §4.5.2）。
    両者は独立したファイルに永続化されるため、一方の更新が他方に波及しない。
    """

    GLOBAL_RULES_FILE_NAME = "global_rules.json"
    RULES_FILE_NAME = "rules.json"

    def get_global_rules(self) -> Rules:
        """グローバルルールを取得する。

        ``<config_dir>/global_rules.json`` が存在しない場合または破損している場合は
        ``_DEFAULT_RULES`` を書き出してから返す（初回アクセス時の初期化）。
        """
        path = self.config_dir / self.GLOBAL_RULES_FILE_NAME
        if path.is_file():
            try:
                return Rules.model_validate(_read_json(path))
            except Exception as exc:
                logger.warning(
                    "global_rules.json の読み込みに失敗しました。既定値で初期化します: %s", exc
                )
        # 初回または破損時：既定値を書き出してから返す
        return self.set_global_rules(_DEFAULT_RULES)

    def set_global_rules(self, rules: Rules) -> Rules:
        """グローバルルールを上書き保存する。

        ``<config_dir>`` が存在しない場合は冪等に作成する。
        """
        self.config_dir.mkdir(parents=True, exist_ok=True)
        path = self.config_dir / self.GLOBAL_RULES_FILE_NAME
        _write_json(path, rules.model_dump(mode="json"))
        return rules

    def get_project_rules(self, project_id: str) -> Rules:
        """プロジェクトルールを取得する。

        ``<projects_dir>/<project_id>/rules.json`` が存在しない場合は
        ``FileNotFoundError`` を送出する。
        API 層でプロジェクト存在確認の後に呼ぶこと（404 変換の責務は API 層）。
        """
        path = self.projects_dir / project_id / self.RULES_FILE_NAME
        if not path.is_file():
            raise FileNotFoundError(
                f"project '{project_id}' の rules.json が存在しません"
            )
        return Rules.model_validate(_read_json(path))

    def set_project_rules(self, project_id: str, rules: Rules) -> Rules:
        """プロジェクトルールを上書き保存する。

        プロジェクトディレクトリが存在しない場合は ``FileNotFoundError``。
        """
        project_dir = self.projects_dir / project_id
        if not project_dir.is_dir():
            raise FileNotFoundError(
                f"project '{project_id}' のディレクトリが存在しません"
            )
        path = project_dir / self.RULES_FILE_NAME
        _write_json(path, rules.model_dump(mode="json"))
        return rules

    def copy_global_to_project(self, project_id: str) -> Rules:
        """グローバルルールをプロジェクトルールとして複製する。

        プロジェクト新規作成時に API 層から呼ばれる（requirements.md §4.5.2）。
        ``get_global_rules()`` 経由で既定値初期化も含めて取得し、
        ``<projects_dir>/<project_id>/rules.json`` に書き出す。

        プロジェクトディレクトリは呼び出し前に作成済みであることが前提
        （``FileProjectRepository.create()`` でディレクトリ作成済み）。
        """
        rules = self.get_global_rules()
        project_dir = self.projects_dir / project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        path = project_dir / self.RULES_FILE_NAME
        _write_json(path, rules.model_dump(mode="json"))
        return rules


class FileResponseRepository(_SettingsBacked, ResponseRepository):
    """Form 回答をプロジェクト配下にファイル保存する（Phase 2.3 本実装）。

    保存先（requirements.md §3.1 / §4.4）::

        <projects_dir>/<project_id>/responses/<出席番号>/<YYYYMMDD_HHMMSS>.json

    同一出席番号からの複数回答はすべて別ファイルとして併存し、
    後続処理（``list_latest_per_student``）では ``submitted_at`` 最新のもののみ返す。
    """

    RESPONSES_DIR_NAME = "responses"
    #: タイムスタンプ衝突時の連番付与回数上限（同一秒・同一生徒で 99 件まで安全に扱う）。
    _MAX_FILENAME_SUFFIX = 99

    # ------------------------------------------------------------------
    # パス計算
    # ------------------------------------------------------------------

    def _responses_dir(self, project_id: str) -> Path:
        return (
            self.projects_dir / project_id / self.RESPONSES_DIR_NAME
        )

    def _student_dir(self, project_id: str, student_number: int) -> Path:
        return self._responses_dir(project_id) / str(student_number)

    # ------------------------------------------------------------------
    # 永続化
    # ------------------------------------------------------------------

    def save_response(self, project_id: str, response: Response) -> Path:
        """回答 1 件をファイルに保存する。

        ファイル名は ``response.submitted_at`` を ``YYYYMMDD_HHMMSS`` に整形して使用する
        （requirements.md §3.1 / §4.4 のサンプル形式）。
        同一秒に複数回答が来た場合は ``_NN`` の連番サフィックスで衝突回避する。
        """
        student_dir = self._student_dir(project_id, response.student_number)
        student_dir.mkdir(parents=True, exist_ok=True)

        base = response.submitted_at.strftime("%Y%m%d_%H%M%S")
        candidate = student_dir / f"{base}.json"
        if candidate.exists():
            # 同一秒・同一生徒で複数回答が来た場合の衝突回避
            for i in range(1, self._MAX_FILENAME_SUFFIX + 1):
                candidate = student_dir / f"{base}_{i:02d}.json"
                if not candidate.exists():
                    break
            else:
                raise RuntimeError(
                    f"ファイル名の連番サフィックスが {self._MAX_FILENAME_SUFFIX} を超過: "
                    f"{base}.json"
                )

        _write_json(candidate, response.model_dump(mode="json"))
        return candidate

    # ------------------------------------------------------------------
    # 読み出し
    # ------------------------------------------------------------------

    def list_all(self, project_id: str) -> list[Response]:
        """全回答ファイルを ``Response`` モデルとして返す（履歴含む）。

        ``responses/`` 以下に存在しない生徒ディレクトリ・壊れた JSON はスキップする。
        順序は保証しない（呼び出し側でソートする）。
        """
        responses_dir = self._responses_dir(project_id)
        if not responses_dir.is_dir():
            return []

        results: list[Response] = []
        for student_dir in responses_dir.iterdir():
            if not student_dir.is_dir():
                continue
            # ディレクトリ名は出席番号（整数）想定。それ以外は壊れたディレクトリとしてスキップ。
            try:
                int(student_dir.name)
            except ValueError:
                logger.warning(
                    "unexpected non-integer student dir: %s", student_dir
                )
                continue
            for path in student_dir.glob("*.json"):
                try:
                    results.append(
                        Response.model_validate(_read_json(path))
                    )
                except Exception as exc:
                    logger.warning(
                        "failed to parse response file %s: %s", path, exc
                    )
                    continue
        return results

    def list_latest_per_student(self, project_id: str) -> list[Response]:
        """各出席番号の最新（``submitted_at`` 最大）の回答のみ返す。

        requirements.md §4.4 「後続処理ではファイル名タイムスタンプ最新のものを使用」
        ※ ファイル名タイムスタンプと ``submitted_at`` は本実装では同一値由来のため、
        ``submitted_at`` で比較すれば等価。
        """
        latest_by_sn: dict[int, Response] = {}
        for r in self.list_all(project_id):
            existing = latest_by_sn.get(r.student_number)
            if existing is None or r.submitted_at > existing.submitted_at:
                latest_by_sn[r.student_number] = r
        # 出席番号昇順で返す（UI 表示・テストの安定性のため）
        return [latest_by_sn[sn] for sn in sorted(latest_by_sn)]

    def get_received_student_numbers(self, project_id: str) -> set[int]:
        """受領済み出席番号の集合を返す。

        ``responses/<sn>/`` ディレクトリの存在＋少なくとも 1 つの ``.json`` ファイルを基準。
        """
        responses_dir = self._responses_dir(project_id)
        if not responses_dir.is_dir():
            return set()
        received: set[int] = set()
        for child in responses_dir.iterdir():
            if not child.is_dir():
                continue
            try:
                sn = int(child.name)
            except ValueError:
                continue
            if any(child.glob("*.json")):
                received.add(sn)
        return received

    def get_pending_student_numbers(self, project_id: str) -> set[int]:
        """未受領出席番号の集合を返す（プロジェクトの全生徒 − 受領済み）。

        生徒名簿は ``project.json`` の ``student_numbers`` フィールド
        （Phase 1.2 で既に定義済み）を直接参照する。
        """
        project_json_path = (
            self.projects_dir / project_id / "project.json"
        )
        if not project_json_path.is_file():
            return set()
        try:
            project = Project.model_validate(_read_json(project_json_path))
        except Exception as exc:
            logger.warning(
                "failed to parse project.json for pending calc: %s", exc
            )
            return set()
        all_sns: set[int] = set(project.student_numbers)
        return all_sns - self.get_received_student_numbers(project_id)

    def get_known_form_response_ids(self, project_id: str) -> set[str]:
        """既知の ``google_form_response_id`` 集合（ポーリング重複検知用）。

        全ファイルの JSON を読み ``google_form_response_id`` フィールドだけ抽出する。
        順序非依存の差分検知（``set`` 演算）に使うため、戻り値も ``set``。
        """
        responses_dir = self._responses_dir(project_id)
        if not responses_dir.is_dir():
            return set()
        ids: set[str] = set()
        for student_dir in responses_dir.iterdir():
            if not student_dir.is_dir():
                continue
            for path in student_dir.glob("*.json"):
                try:
                    data = _read_json(path)
                except Exception:
                    continue
                rid = data.get("google_form_response_id")
                if isinstance(rid, str) and rid:
                    ids.add(rid)
        return ids


class FileDraftRepository(_SettingsBacked, DraftRepository):
    """ドラフトを ``<project_dir>\\drafts\\draft_<timestamp>.json`` として永続化する。

    Phase 3.4 本実装。

    ファイル命名規則（requirements.md §3.1 / §4.9）::

        <projects_dir>/<project_id>/drafts/draft_<YYYYMMDD_HHMMSS>.json

    同一秒に複数保存が来た場合は ``draft_<YYYYMMDD_HHMMSS>_<NN>.json`` で連番回避。
    最新ドラフトは ``saved_at`` の降順で決定する。

    スレッド安全性:
        クラスレベルの ``threading.Lock`` でシリアライズし、並行書き込みによる
        JSON 破損を防ぐ（シングルプロセス・マルチスレッドの uvicorn 運用を想定）。
    """

    DRAFTS_DIR_NAME = "drafts"
    DRAFT_FILE_PREFIX = "draft_"
    #: 同一秒の連番衝突上限
    _MAX_FILENAME_SUFFIX = 99

    # クラスレベルのロック（同一プロセス内で共有される）
    _write_lock: threading.Lock = threading.Lock()

    # ------------------------------------------------------------------
    # パス計算
    # ------------------------------------------------------------------

    def _drafts_dir(self, project_id: str) -> Path:
        return self.projects_dir / project_id / self.DRAFTS_DIR_NAME

    # ------------------------------------------------------------------
    # 内部: ファイル一覧からドラフト読み込み
    # ------------------------------------------------------------------

    def _load_all_with_paths(
        self, project_id: str
    ) -> list[tuple[Draft, Path]]:
        """全ドラフトファイルを (Draft, Path) のリストとして返す。

        読み込み失敗ファイルはログ警告を出してスキップする。
        """
        drafts_dir = self._drafts_dir(project_id)
        if not drafts_dir.is_dir():
            return []

        results: list[tuple[Draft, Path]] = []
        for path in drafts_dir.glob(f"{self.DRAFT_FILE_PREFIX}*.json"):
            try:
                draft = Draft.model_validate(_read_json(path))
                results.append((draft, path))
            except Exception as exc:
                logger.warning("failed to parse draft file %s: %s", path, exc)
        return results

    # ------------------------------------------------------------------
    # 永続化
    # ------------------------------------------------------------------

    def save_draft(self, project_id: str, draft: Draft) -> Path:
        """ドラフトを新規ファイルとして保存し、保存先パスを返す。

        ファイル名は ``draft.saved_at`` を ``YYYYMMDD_HHMMSS`` に整形して使用。
        同一秒の重複は ``_NN`` 連番サフィックスで回避する。

        スレッドセーフ：クラスレベルの Lock でシリアライズ。
        """
        with self._write_lock:
            drafts_dir = self._drafts_dir(project_id)
            drafts_dir.mkdir(parents=True, exist_ok=True)

            base_ts = draft.saved_at.strftime("%Y%m%d_%H%M%S")
            candidate = drafts_dir / f"{self.DRAFT_FILE_PREFIX}{base_ts}.json"

            if candidate.exists():
                # 同一秒・複数保存の衝突回避（連番サフィックス）
                for i in range(1, self._MAX_FILENAME_SUFFIX + 1):
                    candidate = (
                        drafts_dir / f"{self.DRAFT_FILE_PREFIX}{base_ts}_{i:02d}.json"
                    )
                    if not candidate.exists():
                        break
                else:
                    raise RuntimeError(
                        f"ドラフトファイル名の連番が上限 {self._MAX_FILENAME_SUFFIX} を超過: "
                        f"{base_ts}"
                    )

            _write_json(candidate, draft.model_dump(mode="json"))
            return candidate

    # ------------------------------------------------------------------
    # 読み出し
    # ------------------------------------------------------------------

    def get_latest(self, project_id: str) -> Draft | None:
        """最新ドラフトを返す。

        最新の判定は ``saved_at`` 降順の先頭（= 最も新しい保存）。
        ドラフトが 0 件の場合は ``None``。
        """
        entries = self._load_all_with_paths(project_id)
        if not entries:
            return None
        # saved_at 降順でソートし先頭を返す
        entries.sort(key=lambda e: e[0].saved_at, reverse=True)
        return entries[0][0]

    # ------------------------------------------------------------------
    # アンロック
    # ------------------------------------------------------------------

    def unlock_latest(self, project_id: str) -> Draft:
        """最新ドラフトの ``locked`` を ``False`` に更新して返す。

        最新ドラフトが存在しない場合は ``FileNotFoundError``。
        更新は対象ファイルを上書きする（requirements.md §4.9 の「ロック解除」）。

        スレッドセーフ：クラスレベルの Lock でシリアライズ。
        """
        with self._write_lock:
            entries = self._load_all_with_paths(project_id)
            if not entries:
                raise FileNotFoundError(
                    f"project '{project_id}' のドラフトが存在しません"
                )
            entries.sort(key=lambda e: e[0].saved_at, reverse=True)
            latest_draft, latest_path = entries[0]

            unlocked = latest_draft.model_copy(update={"locked": False})
            _write_json(latest_path, unlocked.model_dump(mode="json"))
            return unlocked

    def list_all(self, project_id: str) -> list[Draft]:
        """全ドラフトを ``saved_at`` 降順で返す（履歴含む）。"""
        entries = self._load_all_with_paths(project_id)
        entries.sort(key=lambda e: e[0].saved_at, reverse=True)
        return [e[0] for e in entries]


__all__ = [
    "FileProjectRepository",
    "FileRuleRepository",
    "FileResponseRepository",
    "FileDraftRepository",
]
