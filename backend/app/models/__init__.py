"""Pydantic モデルパッケージ。

requirements.md §3.2 のデータスキーマを Pydantic v2 で表現する。
各モデルはファイル分割し、本モジュールで再エクスポートする。
"""

from __future__ import annotations

from app.models.draft import Assignment, Draft
from app.models.form import FormInfo
from app.models.project import Project, ProjectStatus, TimeSlot
from app.models.response import Availability, Response
from app.models.rules import (
    AvoidTimeConstraint,
    DurationMultiplierConstraint,
    GlobalConstraints,
    PairingConstraint,
    PreferTimeConstraint,
    Rules,
    StudentConstraint,
    TeacherUnavailable,
)

__all__ = [
    # project
    "Project",
    "ProjectStatus",
    "TimeSlot",
    # rules
    "Rules",
    "GlobalConstraints",
    "TeacherUnavailable",
    "StudentConstraint",
    "PairingConstraint",
    "AvoidTimeConstraint",
    "PreferTimeConstraint",
    "DurationMultiplierConstraint",
    # response
    "Response",
    "Availability",
    # draft
    "Draft",
    "Assignment",
    # form
    "FormInfo",
]
