"""Phase 3.3b: スケジューラ パフォーマンステスト。

implementation_prompts_subdivided.md の Phase 3.3b パフォーマンス目標:
    30 名 × 5 日 × 10 コマ で 10 秒以内に解けること。

本ファイルは `@pytest.mark.slow` を付与しており、通常 pytest 実行で除外したい
場合は ``pytest -m "not slow"`` でスキップできる（マーカーは pyproject.toml の
`tool.pytest.ini_options.markers` に登録済み）。

Check-PhaseDone.ps1 の pytest 実行はマーカーフィルタを付けないため、本テストも
実行される。求解時間 10 秒以内が達成されている前提なので、CI 上でも 10 秒以内に
完了する（環境差を踏まえ assert は 10 秒で固定）。

乱数フィクスチャは `random.Random(seed)` で seed=20260629 を固定し再現性を確保する。
各生徒の availability は 50 スロット中ランダムに 25 個（半数）を「可」とする。
"""

from __future__ import annotations

import random
import time as _time_module
from datetime import date, datetime, time, timedelta, timezone

import pytest

from app.models import (
    Availability,
    GlobalConstraints,
    Project,
    Response,
    Rules,
    TimeSlot,
)
from app.services.scheduler import solve


PERF_SEED = 20260629
PERF_NUM_STUDENTS = 30
PERF_NUM_DAYS = 5
PERF_SLOTS_PER_DAY = 10
PERF_AVAIL_RATIO = 0.5  # 各生徒が半数のスロットを「可」とする
#: 求解の上限時間（秒）。Phase 3.3b 目標。
PERF_TIME_BUDGET_SECONDS = 10.0
#: ソルバ自身に渡すタイムリミット。budget 以下に抑えて、wall-clock が暴走するのを防ぐ。
PERF_SOLVER_TIME_LIMIT_SECONDS = 10.0


def _build_perf_fixture(seed: int) -> tuple[Project, list[Response], Rules]:
    """30 名 × 5 日 × 10 コマ のパフォーマンス検証用フィクスチャを生成する。

    - 候補日：2026-07-15 から 5 日連続
    - 各日のスロット：16:00-16:20 から 20 分刻みで 10 スロット（16:00〜19:20）
    - 生徒数 30 名（出席番号 1〜30）
    - 各生徒の availability：50 スロットから 25 個をランダム抽出（seed 固定）
    - rules：ハード制約（教師不可・所要時間倍率）は無し、ソフト制約も最小
      （`max_consecutive_slots=4, forced_break_slots=1, max_slots_per_day=10`）
    """
    rng = random.Random(seed)

    base_date = date(2026, 7, 15)
    dates = [base_date + timedelta(days=i) for i in range(PERF_NUM_DAYS)]

    # 16:00 から 20 分刻みで 10 スロット
    slots: list[TimeSlot] = []
    for i in range(PERF_SLOTS_PER_DAY):
        start_minutes = 16 * 60 + i * 20  # 16:00 = 960
        end_minutes = start_minutes + 20
        slots.append(
            TimeSlot(
                start=time(start_minutes // 60, start_minutes % 60),
                end=time(end_minutes // 60, end_minutes % 60),
            )
        )

    student_numbers = list(range(1, PERF_NUM_STUDENTS + 1))

    project = Project(
        project_id="perf-30x50",
        display_name="パフォーマンス検証 30名×50枠",
        created_at=datetime(2026, 6, 28, tzinfo=timezone.utc),
        status="in_progress",
        slot_minutes=20,
        candidate_dates=dates,
        candidate_time_slots=slots,
        student_numbers=student_numbers,
    )

    # 各生徒の availability：50 スロット中 25 個ランダム
    all_slot_keys: list[tuple[date, time, time]] = [
        (d, ts.start, ts.end) for d in dates for ts in slots
    ]
    n_pick = int(len(all_slot_keys) * PERF_AVAIL_RATIO)
    responses: list[Response] = []
    for sn in student_numbers:
        picked = rng.sample(all_slot_keys, n_pick)
        responses.append(
            Response(
                project_id=project.project_id,
                student_number=sn,
                submitted_at=datetime(2026, 6, 28, 12, 0, 0, tzinfo=timezone.utc),
                google_form_response_id=f"R_{sn}",
                availability=[
                    Availability(date=d, start=s, end=e) for d, s, e in picked
                ],
            )
        )

    rules = Rules(
        global_constraints=GlobalConstraints(
            max_consecutive_slots=4,
            forced_break_slots=1,
            max_slots_per_day=10,
            teacher_unavailable=[],
        ),
        student_constraints=[],
    )

    return project, responses, rules


@pytest.mark.slow
def test_solve_30_students_5_days_10_slots_within_budget() -> None:
    """30 名 × 5 日 × 10 コマ のスケジューリングが 10 秒以内に完了することを検証。

    実測値（経過時間・配置数・未配置数）は標準出力にログする。
    Phase 3.3b の handoff_phase3_3b.md にこの数値を転記する想定。
    """
    project, responses, rules = _build_perf_fixture(PERF_SEED)

    start = _time_module.perf_counter()
    result = solve(
        project,
        responses,
        rules,
        time_limit_seconds=PERF_SOLVER_TIME_LIMIT_SECONDS,
    )
    elapsed = _time_module.perf_counter() - start

    # 計測ログ（pytest -s 等で観察可能）
    print(
        f"\n[perf] 30 students x 5 days x 10 slots: elapsed={elapsed:.3f}s, "
        f"placed={len(result.assignments)}, "
        f"unassigned={len(result.unassigned_students)}, "
        f"seed={PERF_SEED}"
    )

    assert elapsed < PERF_TIME_BUDGET_SECONDS, (
        f"performance budget exceeded: elapsed={elapsed:.3f}s, "
        f"budget={PERF_TIME_BUDGET_SECONDS}s"
    )
    # 念のため：何らかの配置は得られていること（フィクスチャは充分余裕がある）
    assert len(result.assignments) > 0
