"""Excel（.xlsx）出力サービス。

入力: Project + Draft（候補日・時間帯・割り当て情報）
出力: bytes（xlsx バイト列）

以下の3シートを持つブックを生成する。

1. 「日程案（出席番号）」
   PDF出力と同じマトリクス（行=時間帯、列=候補日、セル=出席番号）。
2. 「番号-氏名対応表」
   出席番号ごとに氏名を手動入力するための表。氏名列は空欄で作成する
   （アプリ側は氏名を一切保持していないため、Excel上でユーザーが記入する）。
3. 「日程案（氏名）」
   シート1と同じレイアウトだが、各セルはシート2をVLOOKUPする数式になっており、
   ユーザーがシート2に氏名を記入すると自動的に氏名入りの日程案として表示される。
   対応する氏名が未記入・未登録の場合は出席番号をそのまま表示する。
"""

from __future__ import annotations

import datetime
from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from app.models import Project
from app.models.draft import Draft

# ---------------------------------------------------------------------------
# シート名
# ---------------------------------------------------------------------------

SHEET_ASSIGNMENTS = "日程案（出席番号）"
SHEET_NAME_MAP = "番号-氏名対応表"
SHEET_ASSIGNMENTS_NAMED = "日程案（氏名）"

# ---------------------------------------------------------------------------
# スタイル定数
# ---------------------------------------------------------------------------

_HEADER_FILL = PatternFill(start_color="4A90A4", end_color="4A90A4", fill_type="solid")
_HEADER_FONT = Font(color="FFFFFF", bold=True)
_LABEL_FILL = PatternFill(start_color="F0F0F0", end_color="F0F0F0", fill_type="solid")
_CENTER = Alignment(horizontal="center", vertical="center")
_THIN_BORDER = Border(
    left=Side(style="thin", color="CCCCCC"),
    right=Side(style="thin", color="CCCCCC"),
    top=Side(style="thin", color="CCCCCC"),
    bottom=Side(style="thin", color="CCCCCC"),
)


# ---------------------------------------------------------------------------
# 公開 API
# ---------------------------------------------------------------------------


def generate_excel(project: Project, draft: Draft) -> bytes:
    """ドラフトデータから3シート構成の xlsx を生成する。

    Args:
        project: プロジェクト情報（candidate_dates, candidate_time_slots, student_numbers を使用）
        draft: ドラフト（assignments, unassigned_students を使用）

    Returns:
        bytes: xlsx バイト列
    """
    dates = sorted(project.candidate_dates)
    time_slots = sorted(project.candidate_time_slots, key=lambda ts: ts.start)

    assignment_map: dict[tuple[datetime.date, datetime.time], int] = {}
    for a in draft.assignments:
        assignment_map[(a.date, a.start)] = a.student_number

    wb = Workbook()

    ws_numbers = wb.active
    assert ws_numbers is not None
    ws_numbers.title = SHEET_ASSIGNMENTS
    _write_assignment_sheet(
        ws_numbers, dates, time_slots, assignment_map, draft.unassigned_students
    )

    ws_name_map = wb.create_sheet(SHEET_NAME_MAP)
    _write_name_map_sheet(ws_name_map, project.student_numbers)

    ws_named = wb.create_sheet(SHEET_ASSIGNMENTS_NAMED)
    _write_named_assignment_sheet(ws_named, dates, time_slots)

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 内部ヘルパ
# ---------------------------------------------------------------------------


def _write_assignment_sheet(
    ws: Worksheet,
    dates: list[datetime.date],
    time_slots: list[Any],
    assignment_map: dict[tuple[datetime.date, datetime.time], int],
    unassigned_students: list[int],
) -> None:
    """「日程案（出席番号）」シートを構築する。"""
    ws.cell(row=1, column=1, value="時間帯")
    for col_idx, d in enumerate(dates, start=2):
        ws.cell(row=1, column=col_idx, value=d.strftime("%m/%d"))

    for row_idx, ts in enumerate(time_slots, start=2):
        label = f"{ts.start.strftime('%H:%M')}-{ts.end.strftime('%H:%M')}"
        ws.cell(row=row_idx, column=1, value=label)
        for col_idx, d in enumerate(dates, start=2):
            student_num = assignment_map.get((d, ts.start))
            ws.cell(row=row_idx, column=col_idx, value=student_num)

    n_rows = len(time_slots) + 1
    n_cols = len(dates) + 1
    _apply_matrix_style(ws, n_rows, n_cols)
    _autofit_matrix_columns(ws, n_cols)

    if unassigned_students:
        footer_row = n_rows + 2
        text = "未配置: " + ", ".join(str(n) for n in sorted(unassigned_students))
        ws.cell(row=footer_row, column=1, value=text)


def _write_name_map_sheet(ws: Worksheet, student_numbers: list[int]) -> None:
    """「番号-氏名対応表」シートを構築する（氏名は手動入力のため空欄）。"""
    ws.cell(row=1, column=1, value="出席番号")
    ws.cell(row=1, column=2, value="氏名")
    for cell in (ws.cell(row=1, column=1), ws.cell(row=1, column=2)):
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = _CENTER
        cell.border = _THIN_BORDER

    for row_idx, num in enumerate(sorted(student_numbers), start=2):
        num_cell = ws.cell(row=row_idx, column=1, value=num)
        num_cell.alignment = _CENTER
        num_cell.border = _THIN_BORDER
        ws.cell(row=row_idx, column=2, value=None).border = _THIN_BORDER

    ws.column_dimensions["A"].width = 12
    ws.column_dimensions["B"].width = 24
    ws.freeze_panes = "A2"


def _write_named_assignment_sheet(
    ws: Worksheet,
    dates: list[datetime.date],
    time_slots: list[Any],
) -> None:
    """「日程案（氏名）」シートを構築する。

    セルは「日程案（出席番号）」の対応セルを ``番号-氏名対応表`` で VLOOKUP する数式。
    対応する氏名が見つからない・未記入の場合は出席番号をそのまま表示する。
    """
    ws.cell(row=1, column=1, value="時間帯")
    for col_idx, d in enumerate(dates, start=2):
        ws.cell(row=1, column=col_idx, value=d.strftime("%m/%d"))

    for row_idx, ts in enumerate(time_slots, start=2):
        label = f"{ts.start.strftime('%H:%M')}-{ts.end.strftime('%H:%M')}"
        ws.cell(row=row_idx, column=1, value=label)
        for col_idx in range(2, len(dates) + 2):
            col_letter = get_column_letter(col_idx)
            cell_ref = f"'{SHEET_ASSIGNMENTS}'!{col_letter}{row_idx}"
            lookup = f"VLOOKUP({cell_ref},'{SHEET_NAME_MAP}'!$A:$B,2,FALSE)"
            formula = (
                f'=IF({cell_ref}="","",'
                f'IF(IFERROR({lookup},"")="",{cell_ref},IFERROR({lookup},"")))'
            )
            ws.cell(row=row_idx, column=col_idx, value=formula)

    n_rows = len(time_slots) + 1
    n_cols = len(dates) + 1
    _apply_matrix_style(ws, n_rows, n_cols)
    _autofit_matrix_columns(ws, n_cols, extra_width=6)


def _apply_matrix_style(ws: Worksheet, n_rows: int, n_cols: int) -> None:
    """マトリクスシート共通のスタイル（ヘッダ強調・罫線・中央揃え）を適用する。"""
    for col_idx in range(1, n_cols + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = _CENTER
        cell.border = _THIN_BORDER

    for row_idx in range(2, n_rows + 1):
        label_cell = ws.cell(row=row_idx, column=1)
        label_cell.fill = _LABEL_FILL
        label_cell.alignment = _CENTER
        label_cell.border = _THIN_BORDER
        for col_idx in range(2, n_cols + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.alignment = _CENTER
            cell.border = _THIN_BORDER

    ws.freeze_panes = "B2"


def _autofit_matrix_columns(ws: Worksheet, n_cols: int, extra_width: int = 2) -> None:
    """列幅をおおまかに内容に合わせて調整する。"""
    ws.column_dimensions["A"].width = 14
    for col_idx in range(2, n_cols + 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = 10 + extra_width
