"""Form回答モデル。

requirements.md §3.2 の ``responses/<出席番号>/<timestamp>.json`` スキーマに対応。

スキーマ例::

    {
      "project_id": "2026-Q3-class-A",
      "student_number": 15,
      "submitted_at": "2026-06-24T15:30:12+09:00",
      "google_form_response_id": "ABCDEF...",
      "availability": [
        {"date": "2026-07-15", "start": "16:00", "end": "16:20"},
        {"date": "2026-07-15", "start": "16:20", "end": "16:40"},
        {"date": "2026-07-16", "start": "17:00", "end": "17:20"}
      ]
    }
"""

from __future__ import annotations

import datetime as _dt
from datetime import datetime, time

from pydantic import BaseModel, ConfigDict, Field


class Availability(BaseModel):
    """回答者が可と申告した1スロット。"""

    model_config = ConfigDict(extra="forbid")

    date: _dt.date = Field(..., description="候補日")
    start: time = Field(..., description="開始時刻")
    end: time = Field(..., description="終了時刻")


class Response(BaseModel):
    """Form 回答1件。

    同一生徒からの複数回答は別ファイルとして保存され、最新を採用する
    （requirements.md §4.4）。
    """

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(..., description="所属プロジェクトID")
    student_number: int = Field(..., description="出席番号")
    submitted_at: datetime = Field(..., description="送信日時（TZ 付き）")
    google_form_response_id: str = Field(
        ..., description="Google Forms の responseId（重複検知に使用）"
    )
    availability: list[Availability] = Field(
        default_factory=list, description="申告された可スロット一覧"
    )
