"""ドラフト（日程案保存）モデル。

requirements.md §3.2 の ``drafts/draft_<timestamp>.json`` スキーマに対応。

スキーマ例::

    {
      "project_id": "2026-Q3-class-A",
      "saved_at": "2026-06-24T20:00:00+09:00",
      "locked": true,
      "assignments": [
        {"student_number": 15, "date": "2026-07-15", "start": "16:00", "end": "16:20"}
      ],
      "unassigned_students": [22],
      "violated_constraints": []
    }

``violated_constraints`` の要素スキーマは Phase 3.2 / 3.3 でスケジューラ実装と合わせて
確定する。本フェーズではプレースホルダの自由形 dict として保持する。
"""

from __future__ import annotations

import datetime as _dt
from datetime import datetime, time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Assignment(BaseModel):
    """1コマ分の割り当て。"""

    model_config = ConfigDict(extra="forbid")

    student_number: int = Field(..., description="出席番号")
    date: _dt.date = Field(..., description="面談日")
    start: time = Field(..., description="開始時刻")
    end: time = Field(..., description="終了時刻")


class Draft(BaseModel):
    """日程案ドラフト。

    保存時に ``locked=True`` でロックし、再編集時に ``locked=False`` に戻す
    （requirements.md §4.9）。
    """

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(..., description="所属プロジェクトID")
    saved_at: datetime = Field(..., description="保存日時（TZ 付き）")
    locked: bool = Field(..., description="ロック状態。True なら再編集前")
    assignments: list[Assignment] = Field(
        default_factory=list, description="採用された割り当て一覧"
    )
    unassigned_students: list[int] = Field(
        default_factory=list, description="未配置となった出席番号"
    )
    # 違反制約の要素スキーマは Phase 3.2/3.3 で確定。それまで自由形 dict で受ける。
    violated_constraints: list[dict[str, Any]] = Field(
        default_factory=list, description="違反したソフト制約の情報"
    )
