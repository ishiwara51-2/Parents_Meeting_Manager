"""スケジューラ API ルータ（Phase 3.3b）。

requirements.md §6 の ``POST /api/projects/{id}/schedule`` を担当する。

設計上の決定（Phase 3.3b）:

- 入力：プロジェクト ID（URL パス）+ オプションで ``solver_time_limit_seconds``（ボディ）
- 内部処理:
    1. ``ProjectRepository.get(project_id)`` でプロジェクト取得（不在なら 404）
    2. ``FileProjectRepository.get_form_info(project_id)`` で form.json の存在を確認
       （未作成なら 404 — 「先に Form を作成してください」案内）
    3. ``ResponseRepository.list_latest_per_student(project_id)`` で受領済み回答を取得
       （0 件なら 404 — 「回答を取得してから再試行してください」案内）
    4. ``RuleRepository.get_project_rules(project_id)`` でルール取得
    5. ``app.services.scheduler.solve(project, responses, rules)`` で求解
    6. 結果を ``SchedulingResult`` モデル（Phase 3.2 / 3.3a）として返す
- エラー応答:
    - 404: プロジェクト不在 / form.json 未作成 / 受領済み回答が 0 件
    - 503: CP-SAT が想定外の例外を投げた場合
      （実機ではほぼ発生しないが、防御として明示）
- 例外切り分け:
    - HTTPException は handler 自身がそのまま再送出（再度の HTTPException 変換は不要）

レスポンス構造は Phase 3.2 で定義した ``SchedulingResult``（assignments /
unassigned_students / violated_constraints）。Phase 3.4 のドラフト保存・Phase 4.4 の
日程案表示画面でそのまま使えるフィールド名で揃えてある。

ソルバタイムリミット:
    Phase 3.3a の scheduler 既定値は 60.0 秒だが、API ハンドラでは UX 上 15 秒を
    既定とする（フロントエンドのプログレス表示・ユーザの待ち時間許容を踏まえ、
    パフォーマンス目標 10 秒の +50% を確保）。
    リクエストボディで `solver_time_limit_seconds` を渡せば上書き可能。
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.dependencies import (
    get_project_repository,
    get_response_repository,
    get_rule_repository,
)
from app.repositories.base import (
    ProjectRepository,
    ResponseRepository,
    RuleRepository,
)
from app.repositories.file_repository import FileProjectRepository
from app.services.scheduler import SchedulingResult, solve

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["schedule"])


#: API ハンドラ既定のソルバタイムリミット（秒）。
#: scheduler モジュールの `DEFAULT_SOLVER_TIME_LIMIT_SECONDS=60.0` より厳しい値で、
#: フロントエンドのユーザ待ち時間許容（プログレス表示・体感）を考慮して 15 秒に設定。
#: Phase 3.3b 目標「30 名・5 日 × 10 コマで 10 秒以内」に対し 50% の余裕。
DEFAULT_API_SOLVER_TIME_LIMIT_SECONDS = 15.0


class ScheduleRequest(BaseModel):
    """``POST /api/projects/{id}/schedule`` のリクエストボディ。

    すべて任意。ボディ無しでも呼び出し可能（FastAPI の挙動で 422 にならないよう
    型を ``Optional[ScheduleRequest] | None`` で受ける）。
    """

    model_config = ConfigDict(extra="forbid")

    solver_time_limit_seconds: Optional[float] = Field(
        default=None,
        gt=0,
        description=(
            "CP-SAT のタイムリミット（秒）。省略時は "
            f"{DEFAULT_API_SOLVER_TIME_LIMIT_SECONDS} 秒。"
        ),
    )


@router.post(
    "/{project_id}/schedule",
    response_model=SchedulingResult,
    status_code=status.HTTP_200_OK,
)
def post_schedule(
    project_id: str,
    body: Optional[ScheduleRequest] = None,
    project_repo: ProjectRepository = Depends(get_project_repository),
    response_repo: ResponseRepository = Depends(get_response_repository),
    rule_repo: RuleRepository = Depends(get_rule_repository),
) -> SchedulingResult:
    """指定プロジェクトのスケジューリングを実行する。

    requirements.md §4.6 の方針（ハード制約で解なしの場合は緩和しない、
    未配置生徒の出席番号一覧を返す）に従う。

    Args:
        project_id: 対象プロジェクト ID（URL パス）。
        body: リクエストボディ（任意）。

    Returns:
        SchedulingResult: assignments / unassigned_students / violated_constraints。

    Raises:
        HTTPException 404: プロジェクト不在 / form.json 未作成 / 受領済み回答が 0 件
        HTTPException 503: ソルバが想定外の例外を投げた場合
    """
    # 1. プロジェクト存在チェック
    project = project_repo.get(project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"project '{project_id}' not found",
        )

    # 2. form.json 存在チェック（Form が作成済みでないとスケジューリングは意味を成さない）
    # 抽象 ProjectRepository には get_form_info が無いため、ここだけ FileProjectRepository
    # の I/F に依存する。将来 DB 化する際は ProjectRepository に form_info アクセスを
    # 追加するか別 Repository（FormRepository 等）に切り出す。
    if isinstance(project_repo, FileProjectRepository):
        form_info = project_repo.get_form_info(project_id)
        if form_info is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"form.json not found for project '{project_id}'; "
                    "create Form first via POST /api/projects/{id}/form"
                ),
            )

    # 3. 受領済み回答取得（未受領生徒は除外、requirements.md §4.6.1）
    responses = response_repo.list_latest_per_student(project_id)
    if not responses:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"no responses received for project '{project_id}'; "
                "fetch responses first via POST /api/projects/{id}/responses/sync"
            ),
        )

    # 4. ルール取得（プロジェクト作成時に必ず生成されている前提だが、防御）
    try:
        rules = rule_repo.get_project_rules(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"rules for project '{project_id}' not found",
        ) from exc

    # 5. 求解（任意のタイムリミット上書きあり）
    time_limit = (
        body.solver_time_limit_seconds
        if body is not None and body.solver_time_limit_seconds is not None
        else DEFAULT_API_SOLVER_TIME_LIMIT_SECONDS
    )
    try:
        result = solve(
            project, responses, rules, time_limit_seconds=time_limit
        )
    except Exception as exc:  # noqa: BLE001 - CP-SAT 想定外エラー全般を 503 に
        logger.exception(
            "scheduler.solve raised an unexpected exception for project %s",
            project_id,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"scheduler failed: {exc}",
        ) from exc

    return result


__all__ = ["router", "post_schedule", "DEFAULT_API_SOLVER_TIME_LIMIT_SECONDS"]
