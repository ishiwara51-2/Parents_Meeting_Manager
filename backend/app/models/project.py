"""プロジェクトメタ情報モデル。

requirements.md §3.2 の ``project.json`` スキーマに対応する Pydantic モデル群を定義する。

スキーマ例（requirements.md §3.2 より抜粋）::

    {
      "project_id": "2026-Q3-class-A",
      "display_name": "3年A組 7月面談",
      "created_at": "2026-06-24T10:00:00+09:00",
      "status": "in_progress | draft_saved | finalized",
      "slot_minutes": 20,
      "candidate_dates": ["2026-07-15", "2026-07-16", "2026-07-17"],
      "candidate_time_slots": [
        {"start": "16:00", "end": "16:20"},
        {"start": "16:20", "end": "16:40"}
      ],
      "student_numbers": [1, 2, 3, 4, 5]
    }

本フェーズではモデル定義のみで、永続化ロジックは ``app.repositories.file_repository`` の
骨格に ``NotImplementedError`` として置く（Phase 2.1 で実装予定）。
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

#: プロジェクトのステータス。requirements.md §3.2 の ``status`` フィールドの列挙。
ProjectStatus = Literal["in_progress", "draft_saved", "finalized"]


class TimeSlot(BaseModel):
    """候補時間枠（``candidate_time_slots[]`` の要素）。

    requirements.md §3.2 の ``project.json`` で ``{"start": "16:00", "end": "16:20"}`` 形式で
    表現される時間枠を保持する。
    """

    model_config = ConfigDict(extra="forbid")

    start: time = Field(..., description="開始時刻（HH:MM）")
    end: time = Field(..., description="終了時刻（HH:MM）")


class Project(BaseModel):
    """プロジェクトメタ情報。

    1プロジェクト = 1面談実施単位（例：3年A組の7月面談）。``project_id`` で一意に識別される。
    """

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(..., description="プロジェクト一意ID。ディレクトリ名にも使用")
    display_name: str = Field(..., description="UI 表示用の名前")
    created_at: datetime = Field(..., description="作成日時。TZ 付き ISO 8601")
    status: ProjectStatus = Field(..., description="進行状況")
    slot_minutes: int = Field(..., gt=0, description="1コマの長さ（分）")
    candidate_dates: list[date] = Field(default_factory=list, description="候補日リスト")
    candidate_time_slots: list[TimeSlot] = Field(
        default_factory=list, description="候補時間枠リスト（全候補日共通）"
    )
    student_numbers: list[int] = Field(
        default_factory=list, description="対象生徒の出席番号リスト"
    )
