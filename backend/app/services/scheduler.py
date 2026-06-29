"""ハード制約のみを満たすスケジューラ（Phase 3.2）。

requirements.md §4.6 および implementation_prompts_subdivided.md の Phase 3.2 に従い、
OR-Tools CP-SAT モデルでハード制約のみを考慮したスケジューリングを行う純粋関数を提供する。

ハード制約（requirements.md §4.6.2）:
    1. 候補日時範囲内であること（Project.candidate_dates × candidate_time_slots に限る）
    2. 教師不可時間帯の除外（Rules.global_constraints.teacher_unavailable）
    3. 1 コマ 1 生徒（同一スロットに複数生徒不可）
    4. 所要時間倍率（DurationMultiplierConstraint：連続コマ確保）

ソフト制約（連続コマ数・1日上限・ペアリング・時間帯回避/優先）は Phase 3.3a で同モデルに追加する。
本モジュールは「副作用なし、ファイル I/O / DB アクセスなし」の純粋関数として実装する。

決定変数の設計（"開始位置基準" モデル）::

    x[i, s] = 1  ⇔  生徒 i の面談が候補スロット s から「始まる」
                    （生徒 i のスロット占有範囲は [s, s + mult_i - 1]）

「開始位置基準」を採用した理由:
    - 所要時間倍率を自然に表現できる（mult スロット連続占有を「1 つの開始」で表せる）。
    - スロット競合チェックは「t を占有する全変数の和 <= 1」で書ける。
    - Phase 3.3a で「連続コマ数の上限」を載せる際にも同モデルを再利用できる
      （上限 = max_consecutive_slots を超える連続範囲をペナルティ化するだけ）。

目的関数:
    maximize sum(x[i, s])
    （= 配置できた生徒数の最大化。ハード制約のみなので、配置できないケースは
       「真に配置不可」であり、これを unassigned_students で報告する。
       Phase 3.3a でソフト制約を追加する際は、
       目的関数を「(配置生徒数 × 大きな重み) - (ソフト制約違反ペナルティ)」に拡張する想定。
       「大きな重み」は max_soft_penalty * (生徒数 + 1) 程度を設定し、
       配置生徒数優先・同点ならソフト制約遵守、という辞書式順序を実現する。）

ソルバ設定:
    - `cp_model.CpSolver().parameters.max_time_in_seconds = DEFAULT_SOLVER_TIME_LIMIT_SECONDS`
      （既定 60 秒）。
    - 30 名・5 日 × 10 コマで 10 秒以内（Phase 3.3b のパフォーマンス目標）を満たすため、
      Phase 3.3b 着手時に再評価する。プロトタイプの規模では問題化しにくい。

解なし時の挙動（requirements.md §4.6.4）:
    全員配置が無理な場合、CP-SAT は「全員配置」を要求していないので UNSAT にはならず、
    部分配置を返す。配置できなかった生徒を `unassigned_students` に列挙し、
    その原因の概要を `violated_constraints` に文字列で添える。
    具体的な違反個別判定（例：候補ゼロ vs スロット競合）は valid_starts の有無で識別する。
"""

from __future__ import annotations

import logging
from datetime import date, time
from typing import Iterable

from ortools.sat.python import cp_model
from pydantic import BaseModel, ConfigDict, Field

from app.models import (
    Assignment,
    Availability,
    DurationMultiplierConstraint,
    Project,
    Response,
    Rules,
    TeacherUnavailable,
)

logger = logging.getLogger(__name__)


#: ソルバの既定タイムリミット（秒）。Phase 3.3b で実測しつつ調整可能。
DEFAULT_SOLVER_TIME_LIMIT_SECONDS = 60.0


class SchedulingResult(BaseModel):
    """`solve_hard` の戻り値。

    requirements.md §3.2 の Draft スキーマと同じフィールド名を使い、Phase 3.3b の
    API レスポンスや Phase 3.4 のドラフト保存にそのまま流せるようにする。

    Phase 3.2 では `violated_constraints` を `list[str]`（説明文の配列）で表現する。
    Phase 3.3a 以降で構造化が必要になれば、`list[dict]` に拡張する想定
    （Draft モデルの `violated_constraints: list[dict[str, Any]]` と整合）。
    """

    model_config = ConfigDict(extra="forbid")

    assignments: list[Assignment] = Field(default_factory=list)
    unassigned_students: list[int] = Field(default_factory=list)
    violated_constraints: list[str] = Field(default_factory=list)


# ===== 内部ヘルパ =====


def _time_to_minutes(t: time) -> int:
    """time を「その日の 0:00 から数えた分」に変換。

    候補スロットの順序付け・重なり判定は分単位の整数で扱うのが安定で高速。
    """
    return t.hour * 60 + t.minute


def _slots_overlap(a_start: time, a_end: time, b_start: time, b_end: time) -> bool:
    """同一日における 2 つの時間帯 [a_start, a_end) と [b_start, b_end) が重なるか。

    端点共有（a_end == b_start など）は重ならない扱い（半開区間）。
    """
    return _time_to_minutes(a_start) < _time_to_minutes(b_end) and _time_to_minutes(
        a_end
    ) > _time_to_minutes(b_start)


def _build_all_slots(project: Project) -> list[tuple[date, time, time]]:
    """プロジェクト設定から「全候補スロット」を生成する。

    返り値は (日付昇順, 開始時刻昇順) でソート済み。隣接 2 要素 i, i+1 が
    「同日かつ slots[i].end == slots[i+1].start」を満たす場合に
    「連続スロット」と見做せるようにする（所要時間倍率の必要条件）。
    """
    dates_sorted = sorted(project.candidate_dates)
    slots_sorted = sorted(
        project.candidate_time_slots, key=lambda ts: _time_to_minutes(ts.start)
    )
    out: list[tuple[date, time, time]] = []
    for d in dates_sorted:
        for ts in slots_sorted:
            out.append((d, ts.start, ts.end))
    return out


def _slot_blocked_by_teacher_unavailable(
    slot_date: date,
    slot_start: time,
    slot_end: time,
    teacher_unavailable: Iterable[TeacherUnavailable],
) -> bool:
    """当該スロットが教師不可時間帯と重なるか。"""
    for tu in teacher_unavailable:
        if tu.date != slot_date:
            continue
        if _slots_overlap(slot_start, slot_end, tu.start, tu.end):
            return True
    return False


def _availability_to_slot_indices(
    availability: list[Availability],
    all_slots: list[tuple[date, time, time]],
) -> set[int]:
    """生徒が「可」と申告した Availability を、候補スロットの index 集合に変換する。

    候補範囲外の申告（候補日外・候補時間帯外）は黙って捨てられる
    （ハード制約 1「候補日時範囲内」を保証）。
    マッチ判定は (date, start, end) の完全一致。Availability の (start, end) が
    候補スロットの一部にしか重ならない場合は対象外（プロトタイプではFormが
    candidate_time_slots 単位でチェックボックスを出すため、一致のみで十分）。
    """
    out: set[int] = set()
    for av in availability:
        for idx, (d, s, e) in enumerate(all_slots):
            if av.date == d and av.start == s and av.end == e:
                out.add(idx)
                break
    return out


def _get_multiplier_map(rules: Rules) -> dict[int, int]:
    """生徒番号 → 所要時間倍率 のマップを構築する。

    DurationMultiplierConstraint がない生徒は multiplier=1（既定）扱い。
    同一生徒に複数の duration_multiplier が定義されていれば最後勝ち
    （Pydantic レベルでは重複を禁止していないため、防御的に処理）。
    """
    out: dict[int, int] = {}
    for c in rules.student_constraints:
        if isinstance(c, DurationMultiplierConstraint):
            out[c.student_number] = c.multiplier
    return out


def _compute_valid_starts(
    student_avail: set[int],
    multiplier: int,
    all_slots: list[tuple[date, time, time]],
    teacher_unavailable: list[TeacherUnavailable],
) -> list[int]:
    """生徒の「開始可能スロット位置」のリストを返す。

    開始位置 s が有効な条件:
        - s + multiplier <= len(all_slots)
        - all_slots[s..s+multiplier-1] が:
            * すべて同一日付（所要時間倍率は別日にまたがらない）
            * すべて隣接（slots[k].end == slots[k+1].start、空白なし）
            * すべて student_avail に含まれる
            * すべて教師不可と重ならない

    multiplier=1 の場合は隣接条件は自動満足（範囲が 1 つだけ）。
    """
    valid: list[int] = []
    n = len(all_slots)
    for s in range(n - multiplier + 1):
        ok = True
        for k in range(multiplier):
            idx = s + k
            if idx not in student_avail:
                ok = False
                break
            if _slot_blocked_by_teacher_unavailable(
                all_slots[idx][0],
                all_slots[idx][1],
                all_slots[idx][2],
                teacher_unavailable,
            ):
                ok = False
                break
            if k > 0:
                # 同日かつ前スロットの末尾 == このスロットの先頭
                prev_d, _prev_start, prev_end = all_slots[idx - 1]
                cur_d, cur_start, _cur_end = all_slots[idx]
                if prev_d != cur_d or prev_end != cur_start:
                    ok = False
                    break
        if ok:
            valid.append(s)
    return valid


# ===== 公開 API =====


def solve_hard(
    project: Project,
    responses: list[Response],
    rules: Rules,
    *,
    time_limit_seconds: float = DEFAULT_SOLVER_TIME_LIMIT_SECONDS,
) -> SchedulingResult:
    """ハード制約のみを考慮してスケジューリングを実施する純粋関数。

    Args:
        project: プロジェクトメタ情報。`candidate_dates` × `candidate_time_slots` で
            候補スロット集合が決まる。
        responses: スケジューリング対象生徒の Response 一覧。
            未受領生徒の除外は呼び出し側（Phase 3.3b 想定）の責務。
            同一 `student_number` が複数あった場合は最初に出現したものを採用する。
        rules: グローバル制約と生徒別制約。Phase 3.2 では
            `global_constraints.teacher_unavailable` と
            `DurationMultiplierConstraint` のみ使用する。
        time_limit_seconds: CP-SAT のタイムリミット（秒）。

    Returns:
        SchedulingResult: 採用された割当一覧と未配置生徒、違反説明。

    副作用:
        無し（純粋関数）。`project` / `responses` / `rules` を変更しない。
    """
    all_slots = _build_all_slots(project)
    multiplier_map = _get_multiplier_map(rules)
    teacher_unavailable = list(rules.global_constraints.teacher_unavailable)

    # 同一生徒番号が複数あった場合の重複排除（最初に出現したものを採用）
    seen: set[int] = set()
    unique_responses: list[Response] = []
    for r in responses:
        if r.student_number in seen:
            logger.warning(
                "Duplicate response for student_number=%d; using the first occurrence",
                r.student_number,
            )
            continue
        seen.add(r.student_number)
        unique_responses.append(r)

    # 生徒インデックス i ↔ (student_number, multiplier, availability)
    student_numbers: list[int] = [r.student_number for r in unique_responses]
    multipliers: list[int] = [
        multiplier_map.get(sn, 1) for sn in student_numbers
    ]

    # 各生徒の申告可スロット index 集合（候補範囲外は除外済み）
    student_avail_indices: list[set[int]] = [
        _availability_to_slot_indices(r.availability, all_slots)
        for r in unique_responses
    ]

    # 各生徒の「開始可能スロット位置」
    # （ハード制約 1/2/4 を満たす配置候補の列挙、ここで枝刈りすることで
    #  CP-SAT の探索空間を最小化できる）
    valid_starts: list[list[int]] = [
        _compute_valid_starts(
            student_avail_indices[i], multipliers[i], all_slots, teacher_unavailable
        )
        for i in range(len(student_numbers))
    ]

    # ===== CP-SAT モデル構築 =====
    model = cp_model.CpModel()

    # 決定変数 x[(i, s)]：生徒 i が位置 s から開始するか（Bool）
    x: dict[tuple[int, int], cp_model.IntVar] = {}
    for i, sn in enumerate(student_numbers):
        for s in valid_starts[i]:
            x[(i, s)] = model.NewBoolVar(f"x_s{sn}_pos{s}")

    # 制約 A: 各生徒は最大 1 回しか配置されない
    #     sum_s x[i, s] <= 1
    # （= 0 なら未配置、= 1 なら配置）
    for i in range(len(student_numbers)):
        starts_i = [x[(i, s)] for s in valid_starts[i]]
        if starts_i:
            model.Add(sum(starts_i) <= 1)

    # 制約 B: 各スロット t は最大 1 名の生徒に占有される（ハード制約 3）
    #     sum_{(i, s) : s <= t < s + mult_i} x[(i, s)] <= 1
    # 所要時間倍率（ハード制約 4）はここで自然に統合される：
    # 「mult=2 の生徒が位置 s から開始 → スロット s と s+1 を占有」とみなされ、
    # スロット s+1 における他生徒の占有変数と排他的になる。
    for t in range(len(all_slots)):
        occupants: list[cp_model.IntVar] = []
        for i in range(len(student_numbers)):
            mult = multipliers[i]
            for s in valid_starts[i]:
                if s <= t < s + mult:
                    occupants.append(x[(i, s)])
        if len(occupants) >= 2:
            # 1 名以下なら制約不要（trivially satisfied）。最適化のため枝刈り。
            model.Add(sum(occupants) <= 1)

    # 目的関数: 配置できた生徒数の最大化
    # Phase 3.3a でソフト制約を追加する際は、配置数を大重みで保持しつつ
    # ソフト制約ペナルティを減算する形に拡張する。
    if x:
        model.Maximize(sum(x.values()))
    # x が空のケース（valid_starts が全員ゼロ）はそのまま解く（自明な解：何もしない）

    # ===== ソルバ実行 =====
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit_seconds)
    status = solver.Solve(model)

    # OPTIMAL / FEASIBLE 以外は理論上ここで現れないはず（ハード制約のみのため、
    # 「何も配置しない」が常に実行可能解）。INFEASIBLE になった場合は
    # 何らかの実装バグなので警告ログを出して全員未配置扱いにフォールバック。
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        logger.warning(
            "CP-SAT solver returned unexpected status %s; falling back to all-unassigned",
            solver.StatusName(status),
        )
        return SchedulingResult(
            assignments=[],
            unassigned_students=sorted(student_numbers),
            violated_constraints=[
                f"CP-SAT ソルバが解を返しませんでした（status={solver.StatusName(status)}）"
            ],
        )

    # ===== 結果抽出 =====
    assignments: list[Assignment] = []
    unassigned: list[int] = []
    for i, sn in enumerate(student_numbers):
        placed = False
        for s in valid_starts[i]:
            if solver.Value(x[(i, s)]) == 1:
                mult = multipliers[i]
                start_slot = all_slots[s]
                end_slot = all_slots[s + mult - 1]
                assignments.append(
                    Assignment(
                        student_number=sn,
                        date=start_slot[0],
                        start=start_slot[1],
                        end=end_slot[2],
                    )
                )
                placed = True
                break
        if not placed:
            unassigned.append(sn)

    # 配置順を安定させるため (date, start, student_number) でソート
    assignments.sort(key=lambda a: (a.date, a.start, a.student_number))
    unassigned.sort()

    # ===== 違反制約メッセージ =====
    # Phase 3.2 では「全員配置不可」のみがハード制約違反のシグナル。
    # 具体的な原因区分は valid_starts の状態で判定する：
    #   - valid_starts が空 → 候補日時 / 教師不可 / 所要時間倍率の組合せで開始位置自体がない
    #   - valid_starts が非空 → スロット競合（他生徒との 1 コマ 1 生徒制約）で押し出された
    violated_constraints: list[str] = []
    if unassigned:
        no_candidate_students: list[int] = []
        collision_students: list[int] = []
        unassigned_set = set(unassigned)
        for i, sn in enumerate(student_numbers):
            if sn not in unassigned_set:
                continue
            if not valid_starts[i]:
                no_candidate_students.append(sn)
            else:
                collision_students.append(sn)

        if no_candidate_students:
            violated_constraints.append(
                "候補日時 / 教師不可時間帯 / 所要時間倍率の制約により開始可能スロットが"
                f"無い生徒があります: {sorted(no_candidate_students)}"
            )
        if collision_students:
            violated_constraints.append(
                "他生徒とのスロット競合により配置できない生徒があります: "
                f"{sorted(collision_students)}"
            )

    return SchedulingResult(
        assignments=assignments,
        unassigned_students=unassigned,
        violated_constraints=violated_constraints,
    )
