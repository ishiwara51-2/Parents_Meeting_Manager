"""ハード制約 + ソフト制約を考慮するスケジューラ（Phase 3.2 → 3.3a）。

requirements.md §4.6 および implementation_prompts_subdivided.md の Phase 3.2 / 3.3a に従い、
OR-Tools CP-SAT モデルでハード制約 + ソフト制約を考慮したスケジューリングを行う純粋関数を提供する。

Phase 3.2 でハード制約のみ実装し、Phase 3.3a で以下の 5 種のソフト制約を追加した:

ハード制約（requirements.md §4.6.2）:
    1. 候補日時範囲内であること（Project.candidate_dates × candidate_time_slots に限る）
    2. 教師不可時間帯の除外（Rules.global_constraints.teacher_unavailable）
    3. 1 コマ 1 生徒（同一スロットに複数生徒不可）
    4. 所要時間倍率（DurationMultiplierConstraint：連続コマ確保）

ソフト制約（requirements.md §4.6.2、Phase 3.3a で追加）:
    5. 連続コマ数上限・強制空きコマ（Rules.global_constraints.max_consecutive_slots /
       forced_break_slots）
    6. 1 日あたりコマ数上限（Rules.global_constraints.max_slots_per_day）
    7. ペアリング（PairingConstraint）：指定生徒同士を近接配置
    8. 時間帯回避（AvoidTimeConstraint）：avoid_after / avoid_before 指定時刻を避ける
    9. 時間帯優先（PreferTimeConstraint）：prefer_after / prefer_before 指定時刻を優先

本モジュールは「副作用なし、ファイル I/O / DB アクセスなし」の純粋関数として実装する。

決定変数の設計（"開始位置基準" モデル）::

    x[i, s] = 1  ⇔  生徒 i の面談が候補スロット s から「始まる」
                    （生徒 i のスロット占有範囲は [s, s + mult_i - 1]）

「開始位置基準」を採用した理由:
    - 所要時間倍率を自然に表現できる（mult スロット連続占有を「1 つの開始」で表せる）。
    - スロット競合チェックは「t を占有する全変数の和 <= 1」で書ける。
    - 連続コマ数上限・1 日上限・時間帯制約も同じ x[i, s] を再利用して書ける。

目的関数（Phase 3.3a で拡張）:

    maximize  W_PLACE × Σ x[i, s]   -   Σ soft_penalty_terms

「辞書式優先」を採用:
    - W_PLACE を「ソフト制約ペナルティの理論最大値 + 1」に設定する。
    - これにより 1 名でも多く配置する解は、どんなソフトペナルティの削減よりも優先される。
    - 同じ配置数の中ではソフトペナルティが小さい解が選ばれる。

「重み付き総和」ではなく「辞書式優先」を採用した理由:
    - requirements.md §4.6.4「ハード制約で解なしの場合は緩和しない」が示すように、
      配置数最大化はソフト制約より明確に優先されるべき。
    - 「重みが大きいから配置を諦める」という解釈は要件と矛盾する。
    - Phase 3.2 の handoff (5d4dfb5) で示唆された方式と一致する。

各ソフト制約の定式化:

ソフト制約 5: 連続コマ数上限・強制空きコマ
    - グローバル制約 max_consecutive_slots = M, forced_break_slots = B。
    - 同一日内の連続 (M + B) スロットウィンドウについて、占有合計が M を超えた分をペナルティ化。
    - B=0 の場合もウィンドウサイズは M+1 とし「M を超えた連続」を検出する。
    - 重みは DEFAULT_GLOBAL_SOFT_WEIGHT（後述）。

ソフト制約 6: 1 日あたりコマ数上限
    - max_slots_per_day = D。
    - 各日の占有合計が D を超えた分をペナルティ化。
    - 重みは DEFAULT_GLOBAL_SOFT_WEIGHT。

ソフト制約 7: ペアリング
    - 指定生徒 [a, b, ...] について、全ペアの「位置インデックス差」の絶対値をペナルティ化。
    - 両生徒が配置されている場合のみ加算（片方未配置 / 両方未配置はペナルティなし）。
    - 重み w。位置インデックスは all_slots での順序（同日内は時刻昇順、別日は日付昇順）。

ソフト制約 8: 時間帯回避
    - avoid_after T: slot.start >= T のスロットへの配置にペナルティ。
    - avoid_before T: slot.start < T のスロットへの配置にペナルティ。
    - 両方指定時は両条件を満たすスロットそれぞれにペナルティ加算。

ソフト制約 9: 時間帯優先
    - prefer_after T: slot.start < T のスロット（= 優先帯の外）への配置にペナルティ。
    - prefer_before T: slot.start >= T のスロット（= 優先帯の外）への配置にペナルティ。
    - 「優先帯への配置にボーナス」ではなく「優先帯外にペナルティ」として実装。
      これにより「未配置（x=0）はペナルティ無し」となり、配置インセンティブを歪めない。

グローバルソフト制約の重み:
    `Rules` モデルの GlobalConstraints は連続コマ・1日上限に明示的な weight フィールドを
    持たない（Phase 1.2 で確定）。Phase 3.3a では DEFAULT_GLOBAL_SOFT_WEIGHT = 5 を採用。
    将来モデルに weight を追加する場合は、本定数を取り去り Rules から取り出すよう変更する。

ソルバ設定:
    - `cp_model.CpSolver().parameters.max_time_in_seconds = DEFAULT_SOLVER_TIME_LIMIT_SECONDS`
      （既定 60 秒）。
    - Phase 3.3b のパフォーマンス目標（30 名・5 日 × 10 コマで 10 秒以内）を満たすため、
      Phase 3.3b 着手時に再評価する。

解なし時の挙動（requirements.md §4.6.4）:
    全員配置が無理な場合、CP-SAT は「全員配置」を要求していないので UNSAT にはならず、
    部分配置を返す。配置できなかった生徒を `unassigned_students` に列挙し、
    その原因の概要を `violated_constraints` に文字列で添える。
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
    AvoidTimeConstraint,
    DurationMultiplierConstraint,
    PairingConstraint,
    PreferTimeConstraint,
    Project,
    Response,
    Rules,
    TeacherUnavailable,
)

logger = logging.getLogger(__name__)


#: ソルバの既定タイムリミット（秒）。Phase 3.3b で実測しつつ調整可能。
DEFAULT_SOLVER_TIME_LIMIT_SECONDS = 60.0

#: グローバルソフト制約（連続コマ上限・1日上限）の暗黙重み。
#: Rules.GlobalConstraints が weight フィールドを持たないため、scheduler 側で固定値を使う。
#: 値 5 は per-student ソフト制約の中央値で、ソフト制約間で極端な優劣を付けない設計意図。
DEFAULT_GLOBAL_SOFT_WEIGHT = 5


class SchedulingResult(BaseModel):
    """`solve` の戻り値。

    requirements.md §3.2 の Draft スキーマと同じフィールド名を使い、Phase 3.3b の
    API レスポンスや Phase 3.4 のドラフト保存にそのまま流せるようにする。

    Phase 3.2 では `violated_constraints` を `list[str]`（説明文の配列）で表現する。
    Phase 3.3a でもこれを維持。Phase 3.4 で Draft モデルとの整合を取る際に
    `list[dict]` へ拡張する想定。
    """

    model_config = ConfigDict(extra="forbid")

    assignments: list[Assignment] = Field(default_factory=list)
    unassigned_students: list[int] = Field(default_factory=list)
    violated_constraints: list[str] = Field(default_factory=list)


# ===== 内部ヘルパ：時刻 / スロット計算 =====


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
    マッチ判定は (date, start, end) の完全一致。
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


# ===== 内部ヘルパ：CP-SAT モデル組み立て =====


def _build_occupancy_expr(
    x: dict[tuple[int, int], cp_model.IntVar],
    valid_starts: list[list[int]],
    multipliers: list[int],
    n_slots: int,
) -> list[object]:
    """各スロット t の「占有有無」を線形式として返す。

    occ[t] = Σ_{(i, s) : s <= t < s + mult_i} x[(i, s)]

    ハード制約 3（1 コマ 1 生徒）により実装上 occ[t] ∈ {0, 1} だが、CP-SAT 上では
    sum-of-bools の線形式として扱う。`0` で初期化することで「対象変数なし」スロットも
    安全に扱える。
    """
    occ: list[list[cp_model.IntVar]] = [[] for _ in range(n_slots)]
    for i, mult in enumerate(multipliers):
        for s in valid_starts[i]:
            for k in range(mult):
                if s + k < n_slots:
                    occ[s + k].append(x[(i, s)])
    return [sum(terms) if terms else 0 for terms in occ]


def _add_consecutive_slot_penalty(
    model: cp_model.CpModel,
    occ_per_slot: list[object],
    all_slots: list[tuple[date, time, time]],
    max_consecutive: int,
    forced_break: int,
    weight: int,
) -> list[object]:
    """連続コマ数上限・強制空きコマのペナルティ項を返す（ソフト制約 5）。

    定式化:
        window_size = max_consecutive + max(1, forced_break)
        同一日内で window_size 連続スロットの占有合計が max_consecutive を超えた分を
        excess（スラック変数）で表し、weight × excess をペナルティ化。

    forced_break=0 でも window_size を max_consecutive+1 として
    「max_consecutive を超えた連続」を検出する（プロトタイプとして自然な挙動）。
    forced_break>=1 の場合は window_size = max_consecutive + forced_break として
    「max_consecutive 連続の後 forced_break コマの空き」を満たす配置を促す。

    返り値は線形ペナルティ項（係数×変数）のリスト。weight=0 のときは空リスト。
    """
    if weight == 0:
        return []
    n_slots = len(occ_per_slot)
    window_size = max_consecutive + max(forced_break, 1)
    if window_size > n_slots:
        # ウィンドウがスロット総数より大きい → 連続制約は trivially 緩い
        return []
    penalty_terms: list[object] = []
    for start_t in range(n_slots - window_size + 1):
        window = list(range(start_t, start_t + window_size))
        # ウィンドウが同一日内であることを要求（別日にまたがるウィンドウは無意味）
        first_date = all_slots[start_t][0]
        if not all(all_slots[t][0] == first_date for t in window):
            continue
        # ウィンドウ内のスロットが「物理的に連続」しているか（時間が地続きか）を要求。
        # 同日でも非連続（例：18:00-18:20 と 19:00-19:20 で空白 40 分）の場合は
        # 「連続コマ」概念が成立しないため、ウィンドウとして扱わない。
        physically_contiguous = True
        for k in range(len(window) - 1):
            _d1, _s1, e1 = all_slots[window[k]]
            _d2, s2, _e2 = all_slots[window[k + 1]]
            if e1 != s2:
                physically_contiguous = False
                break
        if not physically_contiguous:
            continue
        total = sum(occ_per_slot[t] for t in window)
        excess = model.NewIntVar(0, window_size, f"cons_excess_{start_t}")
        # excess >= total - max_consecutive かつ excess >= 0
        # （max_consecutive 以下なら excess=0、超過分のみペナルティ）
        model.Add(excess >= total - max_consecutive)
        penalty_terms.append(weight * excess)
    return penalty_terms


def _add_daily_slot_penalty(
    model: cp_model.CpModel,
    occ_per_slot: list[object],
    all_slots: list[tuple[date, time, time]],
    max_per_day: int,
    weight: int,
) -> list[object]:
    """1 日あたりコマ数上限のペナルティ項を返す（ソフト制約 6）。

    定式化:
        各日 d について excess_d = max(0, Σ_{t in day d} occ[t] - max_per_day)
        ペナルティ = weight × Σ_d excess_d

    weight=0 のときは空リスト。
    """
    if weight == 0:
        return []
    # 日付ごとにスロット index をグループ化
    slots_by_date: dict[date, list[int]] = {}
    for t, (d, _s, _e) in enumerate(all_slots):
        slots_by_date.setdefault(d, []).append(t)
    penalty_terms: list[object] = []
    for d, indices in slots_by_date.items():
        total = sum(occ_per_slot[t] for t in indices)
        excess = model.NewIntVar(0, len(indices), f"day_excess_{d.isoformat()}")
        model.Add(excess >= total - max_per_day)
        penalty_terms.append(weight * excess)
    return penalty_terms


def _add_pairing_penalty(
    model: cp_model.CpModel,
    x: dict[tuple[int, int], cp_model.IntVar],
    valid_starts: list[list[int]],
    student_index_map: dict[int, int],
    constraint: PairingConstraint,
    n_slots: int,
) -> list[object]:
    """ペアリング制約のペナルティ項を返す（ソフト制約 7）。

    定式化:
        対象生徒 [a, b, ...] の全ペア (a, b) について
            placed_a = Σ_s x[a, s], placed_b = Σ_s x[b, s]   （いずれも 0 or 1）
            start_a = Σ_s s × x[a, s]                         （未配置時 = 0）
            start_b = Σ_s s × x[b, s]
            diff_ab = start_a - start_b
            abs_diff = |diff_ab|
            both_placed = placed_a AND placed_b
            effective = abs_diff × both_placed
        ペナルティ = weight × Σ_pairs effective

    「両者配置時のみ距離をペナルティ化」とすることで、片方未配置だけでペナルティが
    暴発しないようにする（big-M 線形化）。

    weight=0 のときは空リスト。
    """
    if constraint.weight == 0:
        return []
    target_is = [
        student_index_map[sn]
        for sn in constraint.student_numbers
        if sn in student_index_map
    ]
    if len(target_is) < 2:
        # 対象生徒が 1 名以下（受領無しなど）の場合はペナルティ無し
        return []
    # 各対象生徒の placed / start_pos 線形式を構築
    placed: dict[int, object] = {}
    start_pos: dict[int, object] = {}
    for i in target_is:
        if valid_starts[i]:
            placed[i] = sum(x[(i, s)] for s in valid_starts[i])
            start_pos[i] = sum(s * x[(i, s)] for s in valid_starts[i])
        else:
            placed[i] = 0
            start_pos[i] = 0
    penalty_terms: list[object] = []
    big_m = n_slots if n_slots > 0 else 1
    pair_idx = 0
    for idx_a in range(len(target_is)):
        for idx_b in range(idx_a + 1, len(target_is)):
            a = target_is[idx_a]
            b = target_is[idx_b]
            # diff = start_pos[a] - start_pos[b] ∈ [-n_slots, n_slots]
            diff_var = model.NewIntVar(-n_slots, n_slots, f"pair_diff_{pair_idx}")
            model.Add(diff_var == start_pos[a] - start_pos[b])
            abs_diff_var = model.NewIntVar(0, n_slots, f"pair_absdiff_{pair_idx}")
            model.AddAbsEquality(abs_diff_var, diff_var)
            # both_placed = placed[a] AND placed[b]
            both_var = model.NewBoolVar(f"pair_both_{pair_idx}")
            model.Add(both_var <= placed[a])
            model.Add(both_var <= placed[b])
            model.Add(both_var >= placed[a] + placed[b] - 1)
            # effective = abs_diff_var if both_var else 0
            #   - effective <= big_m * both_var          ← both=0 → effective=0 を強制
            #   - effective <= abs_diff_var              ← 上限を距離に
            #   - effective >= abs_diff_var - big_m*(1 - both_var)  ← both=1 → 距離と一致
            effective_var = model.NewIntVar(0, n_slots, f"pair_eff_{pair_idx}")
            model.Add(effective_var <= big_m * both_var)
            model.Add(effective_var <= abs_diff_var)
            model.Add(effective_var >= abs_diff_var - big_m * (1 - both_var))
            penalty_terms.append(constraint.weight * effective_var)
            pair_idx += 1
    return penalty_terms


def _add_avoid_time_penalty(
    x: dict[tuple[int, int], cp_model.IntVar],
    all_slots: list[tuple[date, time, time]],
    valid_starts: list[list[int]],
    student_index_map: dict[int, int],
    constraint: AvoidTimeConstraint,
) -> list[object]:
    """時間帯回避制約のペナルティ項を返す（ソフト制約 8）。

    定式化:
        対象生徒 i の各開始位置 s について、slot[s].start が avoid 範囲内なら
        x[(i, s)] にペナルティを加える。
        - avoid_after T: slot.start >= T のスロット
        - avoid_before T: slot.start < T のスロット

    両方指定時は両者を満たすスロットそれぞれにペナルティを加算（合算）する。
    weight=0 のときは空リスト。
    """
    if constraint.weight == 0:
        return []
    i = student_index_map.get(constraint.student_number)
    if i is None:
        return []
    penalty_terms: list[object] = []
    avoid_after = constraint.avoid_after
    avoid_before = constraint.avoid_before
    for s in valid_starts[i]:
        slot_start = all_slots[s][1]
        violating = False
        if avoid_after is not None and slot_start >= avoid_after:
            violating = True
        if avoid_before is not None and slot_start < avoid_before:
            violating = True
        if violating:
            penalty_terms.append(constraint.weight * x[(i, s)])
    return penalty_terms


def _add_prefer_time_penalty(
    x: dict[tuple[int, int], cp_model.IntVar],
    all_slots: list[tuple[date, time, time]],
    valid_starts: list[list[int]],
    student_index_map: dict[int, int],
    constraint: PreferTimeConstraint,
) -> list[object]:
    """時間帯優先制約のペナルティ項を返す（ソフト制約 9）。

    定式化:
        対象生徒 i の各開始位置 s について、slot[s].start が prefer 範囲の「外」
        にあれば x[(i, s)] にペナルティを加える。
        - prefer_before T: slot.start >= T （= 優先帯の外）
        - prefer_after T: slot.start < T  （= 優先帯の外）

    「優先帯への配置にボーナス（負ペナルティ）」ではなく「優先帯外にペナルティ」
    として実装した理由:
        - 未配置（x[i, s] が全部 0）の場合にペナルティが 0 になり、配置インセンティブを歪めない。
        - 配置数最大化（W_PLACE × 配置数）と独立に重み付けできる。

    weight=0 のときは空リスト。
    """
    if constraint.weight == 0:
        return []
    i = student_index_map.get(constraint.student_number)
    if i is None:
        return []
    penalty_terms: list[object] = []
    prefer_before = constraint.prefer_before
    prefer_after = constraint.prefer_after
    for s in valid_starts[i]:
        slot_start = all_slots[s][1]
        out_of_preferred = False
        if prefer_before is not None and slot_start >= prefer_before:
            out_of_preferred = True
        if prefer_after is not None and slot_start < prefer_after:
            out_of_preferred = True
        if out_of_preferred:
            penalty_terms.append(constraint.weight * x[(i, s)])
    return penalty_terms


def _compute_w_place(rules: Rules, n_slots: int, n_students: int) -> int:
    """配置インセンティブの大重み W_PLACE を計算する。

    辞書式優先「配置数 > ソフト制約遵守」を 1 つの目的関数で表現するため、
    W_PLACE を「ソフト制約ペナルティの理論最大値 + 1」以上に設定する。

    上限の概算（各ソフト制約の最悪値の和）:
        - 連続コマ: weight × n_slots（窓数の上限） × window_size の上限 ≤ DEFAULT × n_slots × n_slots
        - 1日上限: weight × Σ_d 1日のスロット数 ≤ DEFAULT × n_slots
        - ペアリング: weight × n_slots × (生徒対数の上限)
        - 時間帯回避/優先: weight × 1（生徒は最大 1 回配置）

    これらの和を bound として返す。値が大きすぎても CP-SAT は int64 で安全に扱える。

    Returns:
        W_PLACE: 配置 1 件あたりの目的関数加算値。max_soft_penalty + 1 以上を保証。
    """
    max_soft = 0
    # 連続コマ: 各窓で excess <= window_size、窓数 <= n_slots
    max_soft += DEFAULT_GLOBAL_SOFT_WEIGHT * n_slots * max(n_slots, 1)
    # 1日上限: 全日合計で excess <= n_slots
    max_soft += DEFAULT_GLOBAL_SOFT_WEIGHT * n_slots
    # per-student ソフト
    for c in rules.student_constraints:
        if isinstance(c, PairingConstraint):
            n_targets = len(c.student_numbers)
            n_pairs = n_targets * (n_targets - 1) // 2
            max_soft += c.weight * n_slots * n_pairs
        elif isinstance(c, AvoidTimeConstraint):
            # 1 生徒は最大 1 回配置 → ペナルティ最大 weight
            max_soft += c.weight
        elif isinstance(c, PreferTimeConstraint):
            max_soft += c.weight
    # +1 して厳密に上回るようにする。さらに n_students を足して安全マージン。
    return max_soft + n_students + 1


# ===== 公開 API =====


def solve(
    project: Project,
    responses: list[Response],
    rules: Rules,
    *,
    time_limit_seconds: float = DEFAULT_SOLVER_TIME_LIMIT_SECONDS,
) -> SchedulingResult:
    """ハード制約 + ソフト制約を考慮してスケジューリングを実施する純粋関数。

    Phase 3.2 (`solve_hard`) の機能（ハード制約 + 配置数最大化）に加え、
    Phase 3.3a でソフト制約 5 種を加味した目的関数最適化を行う。

    Args:
        project: プロジェクトメタ情報。`candidate_dates` × `candidate_time_slots` で
            候補スロット集合が決まる。
        responses: スケジューリング対象生徒の Response 一覧。
            未受領生徒の除外は呼び出し側（Phase 3.3b 想定）の責務。
            同一 `student_number` が複数あった場合は最初に出現したものを採用する。
        rules: グローバル制約と生徒別制約。Phase 3.3a 以降は
            `global_constraints` の max_consecutive_slots / forced_break_slots /
            max_slots_per_day もソフト制約として有効。
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
    student_index_map: dict[int, int] = {
        sn: i for i, sn in enumerate(student_numbers)
    }

    # 各生徒の申告可スロット index 集合（候補範囲外は除外済み）
    student_avail_indices: list[set[int]] = [
        _availability_to_slot_indices(r.availability, all_slots)
        for r in unique_responses
    ]

    # 各生徒の「開始可能スロット位置」
    # ハード制約 1/2/4 を満たす配置候補をここで事前列挙し CP-SAT 探索空間を最小化
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
    for i in range(len(student_numbers)):
        starts_i = [x[(i, s)] for s in valid_starts[i]]
        if starts_i:
            model.Add(sum(starts_i) <= 1)

    # 制約 B: 各スロット t は最大 1 名の生徒に占有される（ハード制約 3 + 4）
    n_slots = len(all_slots)
    for t in range(n_slots):
        occupants: list[cp_model.IntVar] = []
        for i in range(len(student_numbers)):
            mult = multipliers[i]
            for s in valid_starts[i]:
                if s <= t < s + mult:
                    occupants.append(x[(i, s)])
        if len(occupants) >= 2:
            model.Add(sum(occupants) <= 1)

    # ===== ソフト制約のペナルティ項（Phase 3.3a） =====
    soft_penalty_terms: list[object] = []

    if x:  # 決定変数が無ければソフト制約は無意味（trivial）
        occ_per_slot = _build_occupancy_expr(x, valid_starts, multipliers, n_slots)

        # 5. 連続コマ数上限・強制空きコマ（global）
        soft_penalty_terms.extend(
            _add_consecutive_slot_penalty(
                model,
                occ_per_slot,
                all_slots,
                rules.global_constraints.max_consecutive_slots,
                rules.global_constraints.forced_break_slots,
                DEFAULT_GLOBAL_SOFT_WEIGHT,
            )
        )
        # 6. 1 日あたりコマ数上限（global）
        soft_penalty_terms.extend(
            _add_daily_slot_penalty(
                model,
                occ_per_slot,
                all_slots,
                rules.global_constraints.max_slots_per_day,
                DEFAULT_GLOBAL_SOFT_WEIGHT,
            )
        )

        # 7-9. per-student ソフト制約
        for c in rules.student_constraints:
            if isinstance(c, PairingConstraint):
                soft_penalty_terms.extend(
                    _add_pairing_penalty(
                        model, x, valid_starts, student_index_map, c, n_slots
                    )
                )
            elif isinstance(c, AvoidTimeConstraint):
                soft_penalty_terms.extend(
                    _add_avoid_time_penalty(
                        x, all_slots, valid_starts, student_index_map, c
                    )
                )
            elif isinstance(c, PreferTimeConstraint):
                soft_penalty_terms.extend(
                    _add_prefer_time_penalty(
                        x, all_slots, valid_starts, student_index_map, c
                    )
                )
            # DurationMultiplierConstraint はハード制約なので無視

    # ===== 目的関数 =====
    # 辞書式優先: W_PLACE × Σ x[i, s] - Σ soft_penalty_terms
    if x:
        w_place = _compute_w_place(rules, n_slots, len(student_numbers))
        placement_term = w_place * sum(x.values())
        if soft_penalty_terms:
            model.Maximize(placement_term - sum(soft_penalty_terms))
        else:
            model.Maximize(placement_term)
    # x が空（valid_starts が全員ゼロ）の場合は自明に解く

    # ===== ソルバ実行 =====
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit_seconds)
    status = solver.Solve(model)

    # OPTIMAL / FEASIBLE 以外は理論上ここで現れないはず。
    # 「何も配置しない」が常に実行可能解のため UNSAT にはならない。
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


#: Phase 3.2 互換のエイリアス。
#: ハード制約のみの旧呼び出しコード（既存テスト・将来 API）はそのまま動作する。
#: ソフト制約が無い（または weight=0）の場合、`solve` はハード制約のみの結果を返すため、
#: Phase 3.2 の挙動は完全に保たれる。
solve_hard = solve
