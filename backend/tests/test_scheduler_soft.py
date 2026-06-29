"""Phase 3.3a: スケジューラ（ソフト制約モデル）のテスト。

requirements.md §4.5.2 / §4.6 および implementation_prompts_subdivided.md の
Phase 3.3a 指示に基づくソフト制約 5 種類の振る舞いを検証する。

ソフト制約（requirements.md §4.6.2）:
    1. 連続コマ数上限・強制空きコマ（global）
    2. 1 日あたりコマ数上限（global）
    3. ペアリング（per-student）
    4. 時間帯回避（per-student）
    5. 時間帯優先（per-student）

検証観点:
    - 各ソフト制約の挙動（weight > 0 のとき該当制約が効く）
    - 重みが大きい制約が優先される
    - weight=0 のソフト制約は無視される（= 制約なしと等価）
    - ハード/ソフト混在ケースで妥当な解
    - 配置数最大化はソフト制約より優先される（辞書式優先）

TDD 順序:
    1. 本ファイルを RED コミット
    2. 実装で全 PASS（GREEN）にする
    3. 同時に test_scheduler_hard.py の 14 件は引き続き全 PASS であること

実装は Phase 3.2 の `solve_hard` と並ぶ `solve` 関数として
`app.services.scheduler` にエクスポートされる。`solve_hard` は
`solve` のエイリアスとして互換維持される。
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timezone

import pytest

from app.models import (
    Assignment,
    Availability,
    AvoidTimeConstraint,
    DurationMultiplierConstraint,
    GlobalConstraints,
    PairingConstraint,
    PreferTimeConstraint,
    Project,
    Response,
    Rules,
    TeacherUnavailable,
    TimeSlot,
)
from app.services.scheduler import SchedulingResult, solve


# ===== ヘルパ =====


def _project(
    *,
    dates: list[str],
    slots: list[tuple[str, str]],
    students: list[int],
    slot_minutes: int = 20,
) -> Project:
    """テスト用 Project を生成する簡易ヘルパ。"""
    return Project(
        project_id="test-proj",
        display_name="テスト面談",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        status="in_progress",
        slot_minutes=slot_minutes,
        candidate_dates=[date.fromisoformat(d) for d in dates],
        candidate_time_slots=[
            TimeSlot(start=time.fromisoformat(s), end=time.fromisoformat(e))
            for s, e in slots
        ],
        student_numbers=list(students),
    )


def _response(
    student_number: int,
    availability: list[tuple[str, str, str]],
    project_id: str = "test-proj",
) -> Response:
    """テスト用 Response を生成する簡易ヘルパ。"""
    return Response(
        project_id=project_id,
        student_number=student_number,
        submitted_at=datetime(2026, 6, 24, 12, 0, 0, tzinfo=timezone.utc),
        google_form_response_id=f"r_{student_number}",
        availability=[
            Availability(
                date=date.fromisoformat(d),
                start=time.fromisoformat(s),
                end=time.fromisoformat(e),
            )
            for d, s, e in availability
        ],
    )


def _loose_global() -> GlobalConstraints:
    """ハード/per-student ソフトのテストでグローバル制約による
    意図しないペナルティを避けるための「緩い」グローバル制約。"""
    return GlobalConstraints(
        max_consecutive_slots=100,
        forced_break_slots=0,
        max_slots_per_day=100,
        teacher_unavailable=[],
    )


def _full_day_avail(
    student_number: int, date_str: str, slots: list[tuple[str, str]]
) -> Response:
    """ある日の全候補スロットを「可」とする Response を作る。"""
    return _response(
        student_number, [(date_str, s, e) for s, e in slots]
    )


# ===== 1. avoid_time（時間帯回避） =====


def test_avoid_time_after_avoids_late_slots():
    """avoid_after が効いて閾値以降への配置を回避する。"""
    project = _project(
        dates=["2026-07-15"],
        slots=[("16:00", "16:20"), ("17:00", "17:20"), ("18:00", "18:20")],
        students=[1],
    )
    responses = [
        _response(
            1,
            [
                ("2026-07-15", "16:00", "16:20"),
                ("2026-07-15", "17:00", "17:20"),
                ("2026-07-15", "18:00", "18:20"),
            ],
        )
    ]
    rules = Rules(
        global_constraints=_loose_global(),
        student_constraints=[
            AvoidTimeConstraint(
                student_number=1, avoid_after=time(17, 0), weight=10
            )
        ],
    )
    result = solve(project, responses, rules)
    assert len(result.assignments) == 1
    a = result.assignments[0]
    # 17:00 以降 (17:00, 18:00) を避けて 16:00 に置かれるはず
    assert a.start == time(16, 0)


def test_avoid_time_before_avoids_early_slots():
    """avoid_before が効いて閾値以前への配置を回避する。"""
    project = _project(
        dates=["2026-07-15"],
        slots=[("16:00", "16:20"), ("17:00", "17:20"), ("18:00", "18:20")],
        students=[1],
    )
    responses = [
        _response(
            1,
            [
                ("2026-07-15", "16:00", "16:20"),
                ("2026-07-15", "17:00", "17:20"),
                ("2026-07-15", "18:00", "18:20"),
            ],
        )
    ]
    rules = Rules(
        global_constraints=_loose_global(),
        student_constraints=[
            AvoidTimeConstraint(
                student_number=1, avoid_before=time(17, 0), weight=10
            )
        ],
    )
    result = solve(project, responses, rules)
    assert len(result.assignments) == 1
    a = result.assignments[0]
    # 17:00 未満（16:00）を避けて 17:00 or 18:00 に置かれるはず
    assert a.start >= time(17, 0)


# ===== 2. prefer_time（時間帯優先） =====


def test_prefer_time_before_prefers_early_slots():
    """prefer_before が効いて閾値以前への配置を優先する。"""
    project = _project(
        dates=["2026-07-15"],
        slots=[("16:00", "16:20"), ("17:00", "17:20"), ("18:00", "18:20")],
        students=[1],
    )
    responses = [
        _response(
            1,
            [
                ("2026-07-15", "16:00", "16:20"),
                ("2026-07-15", "17:00", "17:20"),
                ("2026-07-15", "18:00", "18:20"),
            ],
        )
    ]
    rules = Rules(
        global_constraints=_loose_global(),
        student_constraints=[
            PreferTimeConstraint(
                student_number=1, prefer_before=time(17, 0), weight=10
            )
        ],
    )
    result = solve(project, responses, rules)
    assert len(result.assignments) == 1
    a = result.assignments[0]
    # 17:00 未満を優先 → 16:00
    assert a.start < time(17, 0)


def test_prefer_time_after_prefers_late_slots():
    """prefer_after が効いて閾値以降への配置を優先する。"""
    project = _project(
        dates=["2026-07-15"],
        slots=[("16:00", "16:20"), ("17:00", "17:20"), ("18:00", "18:20")],
        students=[1],
    )
    responses = [
        _response(
            1,
            [
                ("2026-07-15", "16:00", "16:20"),
                ("2026-07-15", "17:00", "17:20"),
                ("2026-07-15", "18:00", "18:20"),
            ],
        )
    ]
    rules = Rules(
        global_constraints=_loose_global(),
        student_constraints=[
            PreferTimeConstraint(
                student_number=1, prefer_after=time(17, 0), weight=10
            )
        ],
    )
    result = solve(project, responses, rules)
    assert len(result.assignments) == 1
    a = result.assignments[0]
    # 17:00 以上を優先 → 17:00 or 18:00
    assert a.start >= time(17, 0)


# ===== 3. pairing（ペアリング） =====


def test_pairing_places_students_in_adjacent_slots():
    """pairing 制約で指定生徒同士が隣接スロットに配置される（距離=1 が最小）。"""
    project = _project(
        dates=["2026-07-15"],
        slots=[
            ("15:00", "15:20"),
            ("15:20", "15:40"),
            ("15:40", "16:00"),
            ("16:00", "16:20"),
            ("16:20", "16:40"),
        ],
        students=[1, 2],
    )
    # 両生徒とも全スロット可
    responses = [
        _full_day_avail(
            sn,
            "2026-07-15",
            [
                ("15:00", "15:20"),
                ("15:20", "15:40"),
                ("15:40", "16:00"),
                ("16:00", "16:20"),
                ("16:20", "16:40"),
            ],
        )
        for sn in [1, 2]
    ]
    rules = Rules(
        global_constraints=_loose_global(),
        student_constraints=[
            PairingConstraint(student_numbers=[1, 2], weight=10)
        ],
    )
    result = solve(project, responses, rules)
    assert len(result.assignments) == 2
    # 開始分単位で隣接（差 20 分 = 1 スロット）であること
    s1 = next(a for a in result.assignments if a.student_number == 1)
    s2 = next(a for a in result.assignments if a.student_number == 2)
    s1_min = s1.start.hour * 60 + s1.start.minute
    s2_min = s2.start.hour * 60 + s2.start.minute
    assert abs(s1_min - s2_min) == 20, (
        f"pairing should place students adjacent (20 min apart), "
        f"got s1={s1.start} s2={s2.start}"
    )


# ===== 4. max_consecutive_slots / forced_break_slots（連続コマ数上限） =====


def test_max_consecutive_slots_avoids_long_runs():
    """max_consecutive_slots を超える連続配置はペナルティされ回避される。"""
    project = _project(
        dates=["2026-07-15"],
        slots=[
            ("15:00", "15:20"),
            ("15:20", "15:40"),
            ("15:40", "16:00"),
            ("16:00", "16:20"),
            ("16:20", "16:40"),
        ],
        students=[1, 2, 3],
    )
    responses = [
        _full_day_avail(
            sn,
            "2026-07-15",
            [
                ("15:00", "15:20"),
                ("15:20", "15:40"),
                ("15:40", "16:00"),
                ("16:00", "16:20"),
                ("16:20", "16:40"),
            ],
        )
        for sn in [1, 2, 3]
    ]
    rules = Rules(
        global_constraints=GlobalConstraints(
            max_consecutive_slots=2,
            forced_break_slots=0,
            max_slots_per_day=100,
        ),
        student_constraints=[],
    )
    result = solve(project, responses, rules)
    # 3 名全員配置されるはず（W_PLACE > soft penalty で辞書式優先）
    assert len(result.assignments) == 3
    # 連続 3 コマ（= max_consecutive_slots を超える）が無いこと
    positions = sorted(
        _slot_position(a.start, "2026-07-15") for a in result.assignments
    )
    for i in range(len(positions) - 2):
        assert not (
            positions[i + 1] == positions[i] + 1
            and positions[i + 2] == positions[i] + 2
        ), f"3 consecutive placements found at positions {positions}"


def test_forced_break_slot_inserts_gap_after_consecutive_run():
    """forced_break_slots=1 で 2 連続後に 1 スロットの空きが入る。"""
    project = _project(
        dates=["2026-07-15"],
        slots=[
            ("15:00", "15:20"),
            ("15:20", "15:40"),
            ("15:40", "16:00"),
            ("16:00", "16:20"),
            ("16:20", "16:40"),
        ],
        students=[1, 2, 3],
    )
    responses = [
        _full_day_avail(
            sn,
            "2026-07-15",
            [
                ("15:00", "15:20"),
                ("15:20", "15:40"),
                ("15:40", "16:00"),
                ("16:00", "16:20"),
                ("16:20", "16:40"),
            ],
        )
        for sn in [1, 2, 3]
    ]
    # max_consecutive=2, forced_break=1 → window_size=3, 3 連続中に最大 2 コマ
    rules = Rules(
        global_constraints=GlobalConstraints(
            max_consecutive_slots=2,
            forced_break_slots=1,
            max_slots_per_day=100,
        ),
        student_constraints=[],
    )
    result = solve(project, responses, rules)
    assert len(result.assignments) == 3
    # 3 名 / 5 スロット中、ウィンドウ size 3 で max 2 占有が守られること
    positions = sorted(
        _slot_position(a.start, "2026-07-15") for a in result.assignments
    )
    for win_start in range(5 - 3 + 1):
        win = set(range(win_start, win_start + 3))
        count = sum(1 for p in positions if p in win)
        assert count <= 2, (
            f"window [{win_start}, {win_start + 2}] has {count} placements "
            f"(max 2 allowed); positions={positions}"
        )


# ===== 5. max_slots_per_day（1日あたりコマ数上限） =====


def test_max_slots_per_day_distributes_across_days():
    """1日あたりコマ数上限が効き、複数日に分散して配置される。"""
    project = _project(
        dates=["2026-07-15", "2026-07-16"],
        slots=[
            ("16:00", "16:20"),
            ("16:20", "16:40"),
            ("16:40", "17:00"),
        ],
        students=[1, 2, 3, 4],
    )
    # 4 名とも 2 日両方の全枠が可
    responses = []
    for sn in [1, 2, 3, 4]:
        avail = []
        for d in ["2026-07-15", "2026-07-16"]:
            for s, e in [("16:00", "16:20"), ("16:20", "16:40"), ("16:40", "17:00")]:
                avail.append((d, s, e))
        responses.append(_response(sn, avail))
    rules = Rules(
        global_constraints=GlobalConstraints(
            max_consecutive_slots=100,
            forced_break_slots=0,
            max_slots_per_day=2,  # 1日 2 コマまでに制限
        ),
        student_constraints=[],
    )
    result = solve(project, responses, rules)
    assert len(result.assignments) == 4
    # 各日のコマ数が 2 以下であること
    counts = Counter(a.date for a in result.assignments)
    for d, c in counts.items():
        assert c <= 2, f"day {d} has {c} placements (max 2)"


# ===== 6. weight=0 の挙動 =====


def test_zero_weight_pairing_ignored():
    """pairing で weight=0 のときは近接配置が強制されない（制約無しと等価）。"""
    project = _project(
        dates=["2026-07-15"],
        slots=[
            ("15:00", "15:20"),
            ("15:20", "15:40"),
            ("15:40", "16:00"),
            ("16:00", "16:20"),
            ("16:20", "16:40"),
        ],
        students=[1, 2],
    )
    responses = [
        _full_day_avail(
            sn,
            "2026-07-15",
            [
                ("15:00", "15:20"),
                ("15:20", "15:40"),
                ("15:40", "16:00"),
                ("16:00", "16:20"),
                ("16:20", "16:40"),
            ],
        )
        for sn in [1, 2]
    ]
    rules_zero = Rules(
        global_constraints=_loose_global(),
        student_constraints=[
            PairingConstraint(student_numbers=[1, 2], weight=0)
        ],
    )
    rules_none = Rules(
        global_constraints=_loose_global(),
        student_constraints=[],
    )
    result_zero = solve(project, responses, rules_zero)
    result_none = solve(project, responses, rules_none)
    # weight=0 は制約無しと完全に等価
    assert result_zero.assignments == result_none.assignments
    assert result_zero.unassigned_students == result_none.unassigned_students


def test_zero_weight_avoid_time_ignored():
    """avoid_time で weight=0 のときは制約が無視される。"""
    project = _project(
        dates=["2026-07-15"],
        slots=[("16:00", "16:20"), ("18:00", "18:20")],
        students=[1],
    )
    responses = [
        _response(
            1,
            [
                ("2026-07-15", "16:00", "16:20"),
                ("2026-07-15", "18:00", "18:20"),
            ],
        )
    ]
    rules_zero = Rules(
        global_constraints=_loose_global(),
        student_constraints=[
            AvoidTimeConstraint(
                student_number=1, avoid_after=time(17, 0), weight=0
            )
        ],
    )
    rules_none = Rules(
        global_constraints=_loose_global(),
        student_constraints=[],
    )
    result_zero = solve(project, responses, rules_zero)
    result_none = solve(project, responses, rules_none)
    assert result_zero.assignments == result_none.assignments


def test_zero_weight_prefer_time_ignored():
    """prefer_time で weight=0 のときは制約が無視される。"""
    project = _project(
        dates=["2026-07-15"],
        slots=[("16:00", "16:20"), ("18:00", "18:20")],
        students=[1],
    )
    responses = [
        _response(
            1,
            [
                ("2026-07-15", "16:00", "16:20"),
                ("2026-07-15", "18:00", "18:20"),
            ],
        )
    ]
    rules_zero = Rules(
        global_constraints=_loose_global(),
        student_constraints=[
            PreferTimeConstraint(
                student_number=1, prefer_before=time(17, 0), weight=0
            )
        ],
    )
    rules_none = Rules(
        global_constraints=_loose_global(),
        student_constraints=[],
    )
    result_zero = solve(project, responses, rules_zero)
    result_none = solve(project, responses, rules_none)
    assert result_zero.assignments == result_none.assignments


# ===== 7. 重みの相対大小（重みが大きい制約が優先される） =====


def test_higher_weight_dominates_competing_soft_constraints():
    """2 つの背反するソフト制約のうち重みが大きい方が支配する。"""
    project = _project(
        dates=["2026-07-15"],
        slots=[("16:00", "16:20"), ("18:00", "18:20")],
        students=[1],
    )
    responses = [
        _response(
            1,
            [
                ("2026-07-15", "16:00", "16:20"),
                ("2026-07-15", "18:00", "18:20"),
            ],
        )
    ]
    # 16:00 を避けたい（avoid_before=17:00, weight=10）
    # 18:00 を避けたい（avoid_after=17:00, weight=1）
    # 重みが大きい方（avoid_before）が支配 → 18:00 に配置
    rules = Rules(
        global_constraints=_loose_global(),
        student_constraints=[
            AvoidTimeConstraint(
                student_number=1, avoid_before=time(17, 0), weight=10
            ),
            AvoidTimeConstraint(
                student_number=1, avoid_after=time(17, 0), weight=1
            ),
        ],
    )
    result = solve(project, responses, rules)
    assert len(result.assignments) == 1
    a = result.assignments[0]
    assert a.start == time(18, 0), (
        f"higher weight (avoid_before, weight=10) should dominate; "
        f"got start={a.start}"
    )


# ===== 8. ハード制約と組み合わせ =====


def test_hard_and_soft_mixed():
    """ハード制約（教師不可、所要時間倍率）とソフト制約（時間帯回避）の混在。"""
    project = _project(
        dates=["2026-07-15"],
        slots=[
            ("15:00", "15:20"),
            ("15:20", "15:40"),
            ("15:40", "16:00"),
            ("16:00", "16:20"),
            ("16:20", "16:40"),
        ],
        students=[1, 9],
    )
    responses = [
        _full_day_avail(
            9,
            "2026-07-15",
            [
                ("15:00", "15:20"),
                ("15:20", "15:40"),
                ("15:40", "16:00"),
                ("16:00", "16:20"),
                ("16:20", "16:40"),
            ],
        ),
        _full_day_avail(
            1,
            "2026-07-15",
            [
                ("15:00", "15:20"),
                ("15:20", "15:40"),
                ("15:40", "16:00"),
                ("16:00", "16:20"),
                ("16:20", "16:40"),
            ],
        ),
    ]
    # ハード: 教師不可 15:00-15:20, 生徒 9 は 2 倍枠
    # ソフト: 生徒 1 は 16:00 以降を回避
    rules = Rules(
        global_constraints=GlobalConstraints(
            max_consecutive_slots=100,
            forced_break_slots=0,
            max_slots_per_day=100,
            teacher_unavailable=[
                TeacherUnavailable(
                    date=date(2026, 7, 15),
                    start=time(15, 0),
                    end=time(15, 20),
                )
            ],
        ),
        student_constraints=[
            DurationMultiplierConstraint(student_number=9, multiplier=2),
            AvoidTimeConstraint(
                student_number=1, avoid_after=time(16, 0), weight=10
            ),
        ],
    )
    result = solve(project, responses, rules)
    # 2 名とも配置されるはず
    assert {a.student_number for a in result.assignments} == {1, 9}
    s9 = next(a for a in result.assignments if a.student_number == 9)
    # 生徒 9 は 2 枠連続（40 分）かつ教師不可 15:00 を含まない
    assert s9.start >= time(15, 20)
    s9_minutes = (s9.end.hour * 60 + s9.end.minute) - (
        s9.start.hour * 60 + s9.start.minute
    )
    assert s9_minutes == 40
    s1 = next(a for a in result.assignments if a.student_number == 1)
    # 生徒 1 は 16:00 以降を回避 → 16:00 より前
    assert s1.start < time(16, 0)


# ===== 9. 辞書式優先：配置数 > ソフト制約 =====


def test_placement_count_takes_priority_over_soft_penalty():
    """配置数最大化はソフト制約より優先される（辞書式優先）。

    具体的: 「ソフト制約に違反して配置する」 vs 「配置せずに違反を回避する」
    の選択肢で、必ず前者が選ばれる（W_PLACE が max soft penalty を超える設計）。
    """
    project = _project(
        dates=["2026-07-15"],
        slots=[("18:00", "18:20")],  # 1 枠のみ、18:00 開始
        students=[1],
    )
    responses = [_response(1, [("2026-07-15", "18:00", "18:20")])]
    # 18:00 を強く回避（weight=10）したいが、唯一の枠が 18:00
    # → 配置数 1 を優先し、ペナルティを受け入れる
    rules = Rules(
        global_constraints=_loose_global(),
        student_constraints=[
            AvoidTimeConstraint(
                student_number=1, avoid_after=time(17, 0), weight=10
            )
        ],
    )
    result = solve(project, responses, rules)
    assert len(result.assignments) == 1
    assert result.assignments[0].student_number == 1
    assert result.unassigned_students == []


# ===== 10. ソフト制約が無くてもハード制約のみで正しく解ける =====


def test_solve_with_no_soft_constraints_matches_hard_behavior():
    """ソフト制約が一切ない（空 student_constraints + 緩いグローバル）場合、
    `solve` は Phase 3.2 の `solve_hard` と同等に動作する。"""
    project = _project(
        dates=["2026-07-15"],
        slots=[("16:00", "16:20"), ("16:20", "16:40")],
        students=[1, 2],
    )
    responses = [
        _response(
            sn,
            [
                ("2026-07-15", "16:00", "16:20"),
                ("2026-07-15", "16:20", "16:40"),
            ],
        )
        for sn in [1, 2]
    ]
    rules = Rules(
        global_constraints=_loose_global(),
        student_constraints=[],
    )
    result = solve(project, responses, rules)
    assert isinstance(result, SchedulingResult)
    assert len(result.assignments) == 2
    assert result.unassigned_students == []


# ===== 11. solve_hard エイリアスの後方互換 =====


def test_solve_hard_is_alias_of_solve():
    """`solve_hard` は `solve` のエイリアスとして Phase 3.2 互換を維持する。"""
    from app.services.scheduler import solve as solve_fn
    from app.services.scheduler import solve_hard as solve_hard_fn

    assert solve_fn is solve_hard_fn


# ===== ヘルパ関数 =====


def _slot_position(start_time: time, date_str: str) -> int:
    """テスト固有のスロット位置計算（同一日 5 スロット 20 分刻み 15:00 始まり）。"""
    base = time(15, 0)
    minutes = (start_time.hour - base.hour) * 60 + (
        start_time.minute - base.minute
    )
    return minutes // 20
