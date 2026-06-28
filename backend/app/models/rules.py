"""ルール（制約）モデル。

requirements.md §3.2 の ``rules.json`` スキーマおよび §4.5 / §4.6.2 に対応する。

スキーマ例（requirements.md §3.2 より抜粋）::

    {
      "global_constraints": {
        "max_consecutive_slots": 3,
        "forced_break_slots": 1,
        "max_slots_per_day": 10,
        "teacher_unavailable": [
          {"date": "2026-07-16", "start": "18:00", "end": "19:00"}
        ]
      },
      "student_constraints": [
        {"type": "pairing", "student_numbers": [5, 12], "weight": 8},
        {"type": "avoid_time", "student_number": 7, "avoid_after": "18:00", "weight": 5},
        {"type": "prefer_time", "student_number": 3, "prefer_before": "17:00", "weight": 5},
        {"type": "duration_multiplier", "student_number": 9, "multiplier": 2}
      ]
    }

生徒別制約は ``type`` フィールドによる discriminated union で表現する。
重みは 0〜10 の整数（requirements.md §4.5.2）。
``duration_multiplier`` はハード制約のため重みを持たない（requirements.md §4.6.2）。
"""

from __future__ import annotations

import datetime as _dt
from datetime import time
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

#: 制約重みの上限・下限（requirements.md §4.5.2「重み（0〜10）」）。
WEIGHT_MIN = 0
WEIGHT_MAX = 10


class TeacherUnavailable(BaseModel):
    """教師不可時間帯（ハード制約）。

    requirements.md §3.2 の ``global_constraints.teacher_unavailable[]`` の要素。
    """

    model_config = ConfigDict(extra="forbid")

    date: _dt.date = Field(..., description="不可日")
    start: time = Field(..., description="不可時間帯の開始")
    end: time = Field(..., description="不可時間帯の終了")


class GlobalConstraints(BaseModel):
    """全体に作用する制約。"""

    model_config = ConfigDict(extra="forbid")

    max_consecutive_slots: int = Field(..., ge=1, description="連続コマ数の上限")
    forced_break_slots: int = Field(..., ge=0, description="強制空きコマ数")
    max_slots_per_day: int = Field(..., ge=1, description="1日あたりコマ数の上限")
    teacher_unavailable: list[TeacherUnavailable] = Field(
        default_factory=list, description="教師不可時間帯リスト"
    )


class PairingConstraint(BaseModel):
    """ペアリング制約（兄弟関係などで連続枠を希望、ソフト）。"""

    model_config = ConfigDict(extra="forbid")

    type: Literal["pairing"] = "pairing"
    student_numbers: list[int] = Field(..., min_length=2, description="ペアにする出席番号")
    weight: int = Field(..., ge=WEIGHT_MIN, le=WEIGHT_MAX, description="ソフト制約重み 0〜10")


class AvoidTimeConstraint(BaseModel):
    """特定時間帯回避制約（ソフト）。

    ``avoid_after`` 指定で「この時刻以降を避ける」を表現する。
    将来 ``avoid_before`` 等の派生が必要になれば本モデルを拡張する。
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["avoid_time"] = "avoid_time"
    student_number: int = Field(..., description="対象生徒の出席番号")
    avoid_after: time | None = Field(None, description="この時刻以降を回避")
    avoid_before: time | None = Field(None, description="この時刻以前を回避")
    weight: int = Field(..., ge=WEIGHT_MIN, le=WEIGHT_MAX, description="ソフト制約重み 0〜10")


class PreferTimeConstraint(BaseModel):
    """特定時間帯選好制約（ソフト）。"""

    model_config = ConfigDict(extra="forbid")

    type: Literal["prefer_time"] = "prefer_time"
    student_number: int = Field(..., description="対象生徒の出席番号")
    prefer_before: time | None = Field(None, description="この時刻以前を優先")
    prefer_after: time | None = Field(None, description="この時刻以降を優先")
    weight: int = Field(..., ge=WEIGHT_MIN, le=WEIGHT_MAX, description="ソフト制約重み 0〜10")


class DurationMultiplierConstraint(BaseModel):
    """所要時間倍率制約（ハード）。

    特定生徒の面談時間を倍率分だけ長く確保する。
    requirements.md §4.6.2 でハード制約に分類されているため、重みは持たない。
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["duration_multiplier"] = "duration_multiplier"
    student_number: int = Field(..., description="対象生徒の出席番号")
    multiplier: int = Field(..., ge=1, description="所要コマ数の倍率（1=既定）")


#: 生徒別制約の union。``type`` フィールドを discriminator として用いる。
StudentConstraint = Annotated[
    Union[
        PairingConstraint,
        AvoidTimeConstraint,
        PreferTimeConstraint,
        DurationMultiplierConstraint,
    ],
    Field(discriminator="type"),
]


class Rules(BaseModel):
    """ルール一式（グローバルルール / プロジェクトルール共通）。"""

    model_config = ConfigDict(extra="forbid")

    global_constraints: GlobalConstraints
    student_constraints: list[StudentConstraint] = Field(default_factory=list)
