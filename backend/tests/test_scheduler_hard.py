"""Phase 3.2: スケジューラ（ハード制約のみ）のテスト。

requirements.md §4.6 (面談日程案作成) および implementation_prompts_subdivided.md の
Phase 3.2 指示に基づく純粋関数 ``solve_hard`` の振る舞いを検証する。

ハード制約（requirements.md §4.6.2）:
    1. 候補日時の範囲内であること
    2. 教師不可時間帯の除外
    3. 1 コマ 1 生徒
    4. 所要時間倍率（連続コマ確保）

TDD 順序:
    1. このファイルを作成（テストケース追加）
    2. pytest が失敗することを確認（RED）
    3. test(phase3.2): add scheduler hard constraints test cases (RED) でコミット
    4. 実装してテストを通す（GREEN）
    5. feat(phase3.2): implement scheduler hard constraints (GREEN) でコミット

テストケース（実装指示書の「最低限」7 件）:
    1. 正常系（候補が十分余裕あり → 全員配置）
    2. 正常系（候補がぴったり → 全員配置、余りなし）
    3. 教師不可時間帯（不可スロットには配置されない）
    4. 1 コマ 1 生徒（衝突しない）
    5. 所要時間倍率（2 倍枠の生徒が連続 2 スロットを占有）
    6. 範囲外配置の禁止（候補範囲外には絶対配置されない）
    7. 解なし系（候補が足りない → unassigned_students が空でない）
追加:
    8. 解なし系（教師不可時間帯で詰む）
    9. 申告可スロットゼロの生徒は unassigned
    10. 純粋関数性（入力オブジェクトを変更しない）
    11. 所要時間倍率は他生徒の重なりを排除する
"""

from __future__ import annotations

import copy
from datetime import date, datetime, time, timezone

import pytest

from app.models import (
    Assignment,
    Availability,
    DurationMultiplierConstraint,
    GlobalConstraints,
    Project,
    Response,
    Rules,
    TeacherUnavailable,
    TimeSlot,
)
from app.services.scheduler import SchedulingResult, solve_hard


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


def _default_rules(
    *,
    teacher_unavailable: list[TeacherUnavailable] | None = None,
    student_constraints: list | None = None,
) -> Rules:
    """ハード制約テスト用の最小ルール。

    ソフト制約のフィールドは大きめの上限を入れ、テストでハード制約に集中できるようにする。
    """
    return Rules(
        global_constraints=GlobalConstraints(
            max_consecutive_slots=10,
            forced_break_slots=0,
            max_slots_per_day=20,
            teacher_unavailable=teacher_unavailable or [],
        ),
        student_constraints=student_constraints or [],
    )


# ===== テスト本体 =====


def test_solve_hard_returns_scheduling_result_type():
    """solve_hard の戻り値は SchedulingResult（assignments/unassigned/violated）。"""
    project = _project(
        dates=["2026-07-15"],
        slots=[("16:00", "16:20")],
        students=[1],
    )
    responses = [_response(1, [("2026-07-15", "16:00", "16:20")])]
    result = solve_hard(project, responses, _default_rules())
    assert isinstance(result, SchedulingResult)
    assert isinstance(result.assignments, list)
    assert isinstance(result.unassigned_students, list)
    assert isinstance(result.violated_constraints, list)


def test_all_students_placed_with_ample_candidates():
    """候補が十分余裕ある場合は全員配置される（正常系1）。"""
    project = _project(
        dates=["2026-07-15"],
        slots=[
            ("16:00", "16:20"),
            ("16:20", "16:40"),
            ("16:40", "17:00"),
            ("17:00", "17:20"),
            ("17:20", "17:40"),
        ],
        students=[1, 2, 3],
    )
    # 全員が全スロット可。候補 5 枠 vs 生徒 3 名なので余裕あり。
    responses = [
        _response(
            sn,
            [
                ("2026-07-15", "16:00", "16:20"),
                ("2026-07-15", "16:20", "16:40"),
                ("2026-07-15", "16:40", "17:00"),
                ("2026-07-15", "17:00", "17:20"),
                ("2026-07-15", "17:20", "17:40"),
            ],
        )
        for sn in [1, 2, 3]
    ]
    result = solve_hard(project, responses, _default_rules())
    assert result.unassigned_students == []
    assert result.violated_constraints == []
    assert len(result.assignments) == 3
    assert {a.student_number for a in result.assignments} == {1, 2, 3}
    # 同一スロットへの二重配置がないこと（ハード制約: 1 コマ 1 生徒）
    used = [(a.date, a.start) for a in result.assignments]
    assert len(set(used)) == len(used)


def test_all_students_placed_with_exact_fit():
    """候補がぴったりでも全員配置できる（正常系2）。"""
    project = _project(
        dates=["2026-07-15"],
        slots=[
            ("16:00", "16:20"),
            ("16:20", "16:40"),
            ("16:40", "17:00"),
        ],
        students=[1, 2, 3],
    )
    # 全員が全スロット可、生徒 3 名 = 候補 3 枠でちょうど。
    responses = [
        _response(
            sn,
            [
                ("2026-07-15", "16:00", "16:20"),
                ("2026-07-15", "16:20", "16:40"),
                ("2026-07-15", "16:40", "17:00"),
            ],
        )
        for sn in [1, 2, 3]
    ]
    result = solve_hard(project, responses, _default_rules())
    assert result.unassigned_students == []
    assert result.violated_constraints == []
    assert len(result.assignments) == 3
    # 3 枠が全て使われ、余りなし
    used = {(a.date, a.start) for a in result.assignments}
    assert len(used) == 3


def test_teacher_unavailable_blocks_slot():
    """教師不可時間帯と重なるスロットには絶対に配置されない（ハード制約2）。"""
    project = _project(
        dates=["2026-07-15"],
        slots=[
            ("16:00", "16:20"),
            ("16:20", "16:40"),
            ("16:40", "17:00"),
        ],
        students=[1],
    )
    responses = [
        _response(
            1,
            [
                ("2026-07-15", "16:00", "16:20"),
                ("2026-07-15", "16:20", "16:40"),
                ("2026-07-15", "16:40", "17:00"),
            ],
        )
    ]
    # 16:20-17:00 を教師不可に → スロット2 (16:20-16:40) と スロット3 (16:40-17:00) が使えない
    rules = _default_rules(
        teacher_unavailable=[
            TeacherUnavailable(
                date=date(2026, 7, 15),
                start=time(16, 20),
                end=time(17, 0),
            )
        ]
    )
    result = solve_hard(project, responses, rules)
    assert len(result.assignments) == 1
    a = result.assignments[0]
    assert a.start == time(16, 0)
    assert a.end == time(16, 20)
    assert result.unassigned_students == []


def test_no_two_students_in_same_slot():
    """同一スロットに 2 生徒は配置されない（ハード制約3）。"""
    project = _project(
        dates=["2026-07-15"],
        slots=[
            ("16:00", "16:20"),
            ("16:20", "16:40"),
        ],
        students=[1, 2],
    )
    # 双方が両方の枠を可と申告
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
    result = solve_hard(project, responses, _default_rules())
    assert len(result.assignments) == 2
    # 2 名が別スロットに配置されること
    used = {(a.date, a.start) for a in result.assignments}
    assert len(used) == 2
    assert result.unassigned_students == []


def test_duration_multiplier_consumes_consecutive_slots():
    """multiplier=2 の生徒は連続 2 スロットを占有する（ハード制約4）。"""
    project = _project(
        dates=["2026-07-15"],
        slots=[
            ("16:00", "16:20"),
            ("16:20", "16:40"),
            ("16:40", "17:00"),
            ("17:00", "17:20"),
        ],
        students=[1, 9],
    )
    # 生徒 9 を multiplier=2 に
    rules = _default_rules(
        student_constraints=[
            DurationMultiplierConstraint(student_number=9, multiplier=2)
        ]
    )
    responses = [
        _response(
            9,
            [
                ("2026-07-15", "16:00", "16:20"),
                ("2026-07-15", "16:20", "16:40"),
                ("2026-07-15", "16:40", "17:00"),
            ],
        ),
        _response(
            1,
            [
                ("2026-07-15", "16:40", "17:00"),
                ("2026-07-15", "17:00", "17:20"),
            ],
        ),
    ]
    result = solve_hard(project, responses, rules)
    assert result.unassigned_students == []
    assert len(result.assignments) == 2
    s9 = next(a for a in result.assignments if a.student_number == 9)
    # 生徒 9 は 40 分（2 スロット）連続を占有
    s9_minutes = (s9.end.hour * 60 + s9.end.minute) - (
        s9.start.hour * 60 + s9.start.minute
    )
    assert s9_minutes == 40, f"expected 40 minutes (2 slots), got {s9_minutes}"
    # 生徒 9 が占有するスロット範囲を計算
    s9_start_min = s9.start.hour * 60 + s9.start.minute
    s9_end_min = s9.end.hour * 60 + s9.end.minute
    s1 = next(a for a in result.assignments if a.student_number == 1)
    s1_start_min = s1.start.hour * 60 + s1.start.minute
    s1_end_min = s1.end.hour * 60 + s1.end.minute
    # 占有時間帯が重ならない（1 コマ 1 生徒の延長）
    assert s1_end_min <= s9_start_min or s1_start_min >= s9_end_min


def test_duration_multiplier_blocks_others_on_overlapping_slots():
    """multiplier=2 が占有する 2 スロットには他生徒は入れない。"""
    project = _project(
        dates=["2026-07-15"],
        slots=[
            ("16:00", "16:20"),
            ("16:20", "16:40"),
        ],
        students=[1, 9],
    )
    rules = _default_rules(
        student_constraints=[
            DurationMultiplierConstraint(student_number=9, multiplier=2)
        ]
    )
    responses = [
        _response(
            9,
            [
                ("2026-07-15", "16:00", "16:20"),
                ("2026-07-15", "16:20", "16:40"),
            ],
        ),
        _response(
            1,
            [
                ("2026-07-15", "16:00", "16:20"),
                ("2026-07-15", "16:20", "16:40"),
            ],
        ),
    ]
    result = solve_hard(project, responses, rules)
    # 生徒 9 が 2 枠取ると、生徒 1 は入れない
    assigned_sns = {a.student_number for a in result.assignments}
    assert 9 in assigned_sns
    assert 1 in result.unassigned_students
    # 違反制約として 1 件以上の説明を返す
    assert len(result.violated_constraints) > 0


def test_out_of_range_slot_is_never_assigned():
    """生徒が申告したスロットが候補範囲外なら絶対に配置されない（ハード制約1）。"""
    project = _project(
        dates=["2026-07-15"],
        slots=[("16:00", "16:20")],
        students=[1],
    )
    # 生徒は候補外の日付・候補外の時刻も含めて申告するが、配置は候補内のみ
    responses = [
        _response(
            1,
            [
                ("2026-07-15", "16:00", "16:20"),  # 候補内
                ("2026-07-16", "16:00", "16:20"),  # 候補外（日付外）
                ("2026-07-15", "17:00", "17:20"),  # 候補外（時間帯外）
            ],
        )
    ]
    result = solve_hard(project, responses, _default_rules())
    assert len(result.assignments) == 1
    a = result.assignments[0]
    assert a.date == date(2026, 7, 15)
    assert a.start == time(16, 0)
    assert a.end == time(16, 20)


def test_out_of_range_only_availability_yields_unassigned():
    """候補外の申告しかない生徒は配置されない。"""
    project = _project(
        dates=["2026-07-15"],
        slots=[("16:00", "16:20")],
        students=[1],
    )
    responses = [
        _response(
            1,
            [
                ("2026-07-16", "16:00", "16:20"),  # 候補日外
                ("2026-07-15", "17:00", "17:20"),  # 候補時間帯外
            ],
        )
    ]
    result = solve_hard(project, responses, _default_rules())
    assert result.assignments == []
    assert result.unassigned_students == [1]
    assert len(result.violated_constraints) > 0


def test_unassigned_when_candidates_run_out():
    """候補が足りない場合、超過分は unassigned_students に入る（解なし系1）。"""
    project = _project(
        dates=["2026-07-15"],
        slots=[("16:00", "16:20")],
        students=[1, 2, 3],
    )
    # 3 名が 1 枠だけ可 → 1 名のみ配置可能
    responses = [
        _response(sn, [("2026-07-15", "16:00", "16:20")]) for sn in [1, 2, 3]
    ]
    result = solve_hard(project, responses, _default_rules())
    assert len(result.assignments) == 1
    assert len(result.unassigned_students) == 2
    assert set(result.unassigned_students) == {1, 2, 3} - {
        result.assignments[0].student_number
    }
    assert len(result.violated_constraints) > 0


def test_unassigned_when_teacher_unavailable_blocks_all_slots():
    """教師不可時間帯で全枠が潰れる場合は全員 unassigned（解なし系2）。"""
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
    # 教師が全候補時間帯を不可に
    rules = _default_rules(
        teacher_unavailable=[
            TeacherUnavailable(
                date=date(2026, 7, 15),
                start=time(16, 0),
                end=time(16, 40),
            )
        ]
    )
    result = solve_hard(project, responses, rules)
    assert result.assignments == []
    assert sorted(result.unassigned_students) == [1, 2]
    assert len(result.violated_constraints) > 0


def test_student_with_empty_availability_is_unassigned():
    """申告可スロットゼロの生徒は配置されない。"""
    project = _project(
        dates=["2026-07-15"],
        slots=[("16:00", "16:20")],
        students=[1, 2],
    )
    responses = [
        _response(1, []),  # 空の申告
        _response(2, [("2026-07-15", "16:00", "16:20")]),
    ]
    result = solve_hard(project, responses, _default_rules())
    assert {a.student_number for a in result.assignments} == {2}
    assert result.unassigned_students == [1]
    assert len(result.violated_constraints) > 0


def test_solve_hard_is_pure_function():
    """solve_hard は入力オブジェクトを変更しない（純粋関数性、Phase 3.2 仕様）。"""
    project = _project(
        dates=["2026-07-15"],
        slots=[("16:00", "16:20"), ("16:20", "16:40")],
        students=[1, 2],
    )
    responses = [
        _response(sn, [("2026-07-15", "16:00", "16:20"), ("2026-07-15", "16:20", "16:40")])
        for sn in [1, 2]
    ]
    rules = _default_rules()

    project_before = copy.deepcopy(project)
    responses_before = copy.deepcopy(responses)
    rules_before = copy.deepcopy(rules)

    solve_hard(project, responses, rules)

    assert project == project_before
    assert responses == responses_before
    assert rules == rules_before


def test_duration_multiplier_does_not_cross_day_boundary():
    """multiplier=2 でも別日にまたがって連続扱いされない。"""
    project = _project(
        dates=["2026-07-15", "2026-07-16"],
        # 同じ時間帯の枠を 2 日分用意（各日 1 枠ずつ）
        slots=[("16:00", "16:20")],
        students=[9],
    )
    rules = _default_rules(
        student_constraints=[
            DurationMultiplierConstraint(student_number=9, multiplier=2)
        ]
    )
    # 生徒 9 は両日とも可、ただし各日 1 枠しかないので 2 連続スロットは取れない
    responses = [
        _response(
            9,
            [
                ("2026-07-15", "16:00", "16:20"),
                ("2026-07-16", "16:00", "16:20"),
            ],
        )
    ]
    result = solve_hard(project, responses, rules)
    assert result.assignments == []
    assert result.unassigned_students == [9]
