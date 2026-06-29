"""Phase 5.1: PDF生成サービスのテスト。

テスト対象: app.services.pdf_generator.generate_pdf

テストケース:
1. PDFマジックバイト確認 -- 先頭が b"%PDF-"
2. 複数日の列展開 -- 複数日付の割り当てを渡したとき両日付がPDFテキストに含まれること
3. スパース割り当て（空きコマ） -- 全スロットが埋まっていない場合もエラーなく生成できること
4. 日本語非文字化け -- プロジェクト名など日本語テキストがPDFから抽出できること

RED フェーズ: app.services.pdf_generator が存在しないため全テストが ImportError で失敗する。
"""

from __future__ import annotations

import datetime
from io import BytesIO

import pytest
from pypdf import PdfReader

from app.models import Project, TimeSlot
from app.models.draft import Assignment, Draft
from app.services.pdf_generator import generate_pdf


# ---------------------------------------------------------------------------
# テスト用ファクトリ関数
# ---------------------------------------------------------------------------

_TZ_JST = datetime.timezone(datetime.timedelta(hours=9))


def _make_project(
    project_id: str = "test-project",
    display_name: str = "テストプロジェクト",
    candidate_dates: list[datetime.date] | None = None,
    candidate_time_slots: list[TimeSlot] | None = None,
    student_numbers: list[int] | None = None,
) -> Project:
    if candidate_dates is None:
        candidate_dates = [
            datetime.date(2026, 7, 15),
            datetime.date(2026, 7, 16),
        ]
    if candidate_time_slots is None:
        candidate_time_slots = [
            TimeSlot(start=datetime.time(16, 0), end=datetime.time(16, 20)),
            TimeSlot(start=datetime.time(16, 20), end=datetime.time(16, 40)),
        ]
    if student_numbers is None:
        student_numbers = [1, 2, 3]
    return Project(
        project_id=project_id,
        display_name=display_name,
        created_at=datetime.datetime(2026, 6, 24, 10, 0, 0, tzinfo=_TZ_JST),
        status="in_progress",
        slot_minutes=20,
        candidate_dates=candidate_dates,
        candidate_time_slots=candidate_time_slots,
        student_numbers=student_numbers,
    )


def _make_draft(
    project_id: str = "test-project",
    assignments: list[Assignment] | None = None,
    unassigned_students: list[int] | None = None,
) -> Draft:
    if assignments is None:
        assignments = [
            Assignment(
                student_number=1,
                date=datetime.date(2026, 7, 15),
                start=datetime.time(16, 0),
                end=datetime.time(16, 20),
            ),
        ]
    if unassigned_students is None:
        unassigned_students = []
    return Draft(
        project_id=project_id,
        saved_at=datetime.datetime(2026, 6, 24, 20, 0, 0, tzinfo=_TZ_JST),
        locked=True,
        assignments=assignments,
        unassigned_students=unassigned_students,
        violated_constraints=[],
    )


# ---------------------------------------------------------------------------
# テスト本体
# ---------------------------------------------------------------------------


class TestGeneratePdf:
    """generate_pdf のテスト群。"""

    def test_pdf_magic_bytes(self) -> None:
        """生成されたPDFが %PDF- で始まること（マジックバイト確認）。"""
        project = _make_project()
        draft = _make_draft()
        result = generate_pdf(project, draft)

        assert isinstance(result, bytes), "generate_pdf は bytes を返すこと"
        assert result[:5] == b"%PDF-", f"先頭5バイトが %PDF- でない: {result[:5]!r}"

    def test_multiple_date_columns(self) -> None:
        """複数日の割り当てを渡したとき、両日付がPDFテキストに展開されること。"""
        project = _make_project(
            candidate_dates=[
                datetime.date(2026, 7, 15),
                datetime.date(2026, 7, 16),
            ],
            student_numbers=[1, 2],
        )
        assignments = [
            Assignment(
                student_number=1,
                date=datetime.date(2026, 7, 15),
                start=datetime.time(16, 0),
                end=datetime.time(16, 20),
            ),
            Assignment(
                student_number=2,
                date=datetime.date(2026, 7, 16),
                start=datetime.time(16, 0),
                end=datetime.time(16, 20),
            ),
        ]
        draft = _make_draft(assignments=assignments)

        pdf_bytes = generate_pdf(project, draft)
        reader = PdfReader(BytesIO(pdf_bytes))
        text = "".join(page.extract_text() or "" for page in reader.pages)

        # 07/15 と 07/16 のどちらかの形式で両日付が含まれる
        assert (
            "07/15" in text or "7/15" in text or "07-15" in text
        ), f"7/15 の日付文字列がPDFテキストに見つからない: {text[:500]!r}"
        assert (
            "07/16" in text or "7/16" in text or "07-16" in text
        ), f"7/16 の日付文字列がPDFテキストに見つからない: {text[:500]!r}"

    def test_sparse_assignments_no_error(self) -> None:
        """割り当てがスパースな場合も空セルを含むPDFが正常に生成されること。"""
        project = _make_project(
            candidate_dates=[
                datetime.date(2026, 7, 15),
                datetime.date(2026, 7, 16),
                datetime.date(2026, 7, 17),
            ],
            candidate_time_slots=[
                TimeSlot(start=datetime.time(16, 0), end=datetime.time(16, 20)),
                TimeSlot(start=datetime.time(16, 20), end=datetime.time(16, 40)),
                TimeSlot(start=datetime.time(16, 40), end=datetime.time(17, 0)),
            ],
            student_numbers=[1, 2, 3, 4, 5],
        )
        # 3日×3コマのうち1コマだけ割り当て（残りは空きコマ）
        assignments = [
            Assignment(
                student_number=1,
                date=datetime.date(2026, 7, 15),
                start=datetime.time(16, 0),
                end=datetime.time(16, 20),
            ),
        ]
        draft = _make_draft(assignments=assignments, unassigned_students=[2, 3, 4, 5])

        pdf_bytes = generate_pdf(project, draft)

        assert pdf_bytes[:5] == b"%PDF-", "スパース割り当て時のPDFマジックバイト確認"
        reader = PdfReader(BytesIO(pdf_bytes))
        assert len(reader.pages) >= 1, "少なくとも1ページのPDFが生成されること"

    def test_japanese_text_not_garbled(self) -> None:
        """日本語プロジェクト名がPDFテキストとして抽出できること（文字化けなし）。"""
        display_name = "3年A組 7月面談"
        project = _make_project(display_name=display_name)
        assignments = [
            Assignment(
                student_number=15,
                date=datetime.date(2026, 7, 15),
                start=datetime.time(16, 0),
                end=datetime.time(16, 20),
            ),
        ]
        draft = _make_draft(assignments=assignments)

        pdf_bytes = generate_pdf(project, draft)
        reader = PdfReader(BytesIO(pdf_bytes))
        text = "".join(page.extract_text() or "" for page in reader.pages)

        # 日本語プロジェクト名の一部が含まれること
        assert "3年A組" in text or "7月面談" in text, (
            f"日本語テキストがPDFから抽出できない。抽出テキスト先頭: {text[:500]!r}"
        )
