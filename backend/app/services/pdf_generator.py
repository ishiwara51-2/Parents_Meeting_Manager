"""PDF生成サービス（Phase 5.1）。

入力: Project + Draft（候補日・時間帯・割り当て情報）
出力: bytes（PDFバイト列。先頭は b"%PDF-"）

レイアウト:
    A4縦、マトリクス形式
    - 行 = 時間帯（candidate_time_slots の各スロット）
    - 列 = 日付（candidate_dates の各日付）
    - セル = 割り当てられた出席番号（未割り当ての場合は空）

フォント:
    Noto Sans CJK JP (OFL 1.1) を ReportLab TTFont で登録。
    フォントファイル: backend/app/fonts/NotoSansCJKjp-Regular.otf

1ページ超過時の挙動:
    列数が多い場合はフォントサイズを自動縮小しつつ列幅を均等調整して
    できる限り1ページに収める（docs/pdf_decisions.md 参照）。
    それでも収まらない場合はReportLabの自動改ページに委ねる。
"""

from __future__ import annotations

import datetime
import logging
from io import BytesIO
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT

from app.models import Project
from app.models.draft import Assignment, Draft

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# フォント設定
# ---------------------------------------------------------------------------

_FONTS_DIR = Path(__file__).parent.parent / "fonts"
_FONT_PATH = _FONTS_DIR / "NotoSansCJKjp-Regular.otf"
_FONT_NAME = "NotoSansCJKjp"

_font_registered = False


def _ensure_font_registered() -> None:
    """NotoSansCJKjp フォントをプロセス内で一度だけ登録する。"""
    global _font_registered
    if _font_registered:
        return
    if not _FONT_PATH.exists():
        raise FileNotFoundError(
            f"日本語フォントが見つかりません: {_FONT_PATH}\n"
            "backend/app/fonts/NotoSansCJKjp-Regular.otf を配置してください。"
        )
    pdfmetrics.registerFont(TTFont(_FONT_NAME, str(_FONT_PATH)))
    _font_registered = True
    logger.debug("Registered font: %s from %s", _FONT_NAME, _FONT_PATH)


# ---------------------------------------------------------------------------
# レイアウト定数
# ---------------------------------------------------------------------------

# A4縦のページ内幅（余白除き）: 210mm - 15mm*2 = 180mm
_PAGE_WIDTH_MM = 180.0
# セルの最小フォントサイズ
_MIN_CELL_FONT_SIZE = 6
# セルの基本フォントサイズ
_BASE_CELL_FONT_SIZE = 9
# タイトルフォントサイズ
_TITLE_FONT_SIZE = 14
# ヘッダ行フォントサイズ
_HEADER_FONT_SIZE = 9
# 行ラベル列の固定幅（mm）
_TIME_LABEL_COL_WIDTH_MM = 22.0


# ---------------------------------------------------------------------------
# 公開 API
# ---------------------------------------------------------------------------


def generate_pdf(project: Project, draft: Draft) -> bytes:
    """ドラフトデータからA4縦・マトリクス形式のPDFを生成する。

    Args:
        project: プロジェクト情報（display_name, candidate_dates, candidate_time_slots を使用）
        draft: ドラフト（assignments, unassigned_students を使用）

    Returns:
        bytes: PDF バイト列（先頭が b"%PDF-"）

    Raises:
        FileNotFoundError: フォントファイルが存在しない場合
    """
    _ensure_font_registered()

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title=project.display_name,
        author="保護者面談調整ツール",
    )

    # 候補日時の準備（ソート済み）
    dates = sorted(project.candidate_dates)
    time_slots = sorted(project.candidate_time_slots, key=lambda ts: ts.start)

    # 割り当てマップ: (date, start_time) → 出席番号
    # start は datetime.time だが Assignment.start も time なので直接比較可
    assignment_map: dict[tuple[datetime.date, datetime.time], int] = {}
    for a in draft.assignments:
        assignment_map[(a.date, a.start)] = a.student_number

    # フォントサイズを列数に応じて調整
    n_date_cols = len(dates)
    cell_font_size = _compute_cell_font_size(n_date_cols)

    # テーブルデータ構築
    table_data = _build_table_data(dates, time_slots, assignment_map)

    # 列幅計算
    col_widths = _compute_col_widths(n_date_cols)

    # スタイル定義
    title_style = ParagraphStyle(
        name="Title",
        fontName=_FONT_NAME,
        fontSize=_TITLE_FONT_SIZE,
        leading=_TITLE_FONT_SIZE * 1.4,
        alignment=TA_LEFT,
        spaceAfter=6,
    )
    footer_style = ParagraphStyle(
        name="Footer",
        fontName=_FONT_NAME,
        fontSize=8,
        leading=10,
        alignment=TA_LEFT,
        textColor=colors.grey,
    )

    elements: list[Any] = []

    # タイトル
    title_text = f"{project.display_name}　面談日程表"
    elements.append(Paragraph(title_text, title_style))
    elements.append(Spacer(1, 4 * mm))

    # マトリクス表
    table = _build_table(table_data, col_widths, cell_font_size)
    elements.append(table)
    elements.append(Spacer(1, 4 * mm))

    # 未配置生徒の表示
    if draft.unassigned_students:
        unassigned_text = f"未配置: {', '.join(str(n) for n in sorted(draft.unassigned_students))}"
        elements.append(Paragraph(unassigned_text, footer_style))

    doc.build(elements)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 内部ヘルパ
# ---------------------------------------------------------------------------


def _compute_cell_font_size(n_date_cols: int) -> int:
    """列数に応じてセルフォントサイズを決定する。

    列数が多いほど小さく。最小 _MIN_CELL_FONT_SIZE pt まで縮小。
    """
    if n_date_cols <= 3:
        return _BASE_CELL_FONT_SIZE
    elif n_date_cols <= 5:
        return 8
    elif n_date_cols <= 7:
        return 7
    else:
        return max(_MIN_CELL_FONT_SIZE, _BASE_CELL_FONT_SIZE - (n_date_cols - 3))


def _compute_col_widths(n_date_cols: int) -> list[float]:
    """列幅リストを返す（単位: mm→pt 変換済み）。

    最初の列（時間帯ラベル）は固定幅、残りの列は等分割。
    """
    time_col_width = _TIME_LABEL_COL_WIDTH_MM * mm
    if n_date_cols == 0:
        return [time_col_width]
    remaining = _PAGE_WIDTH_MM * mm - time_col_width
    date_col_width = remaining / n_date_cols
    return [time_col_width] + [date_col_width] * n_date_cols


def _build_table_data(
    dates: list[datetime.date],
    time_slots: list[Any],
    assignment_map: dict[tuple[datetime.date, datetime.time], int],
) -> list[list[str]]:
    """テーブルデータ（2次元リスト）を構築する。

    先頭行: ヘッダ（"時間帯" + 日付列）
    以降: 各時間帯の行（時間帯ラベル + 出席番号または空文字）
    """
    # ヘッダ行
    header = ["時間帯"] + [d.strftime("%m/%d") for d in dates]
    rows: list[list[str]] = [header]

    for ts in time_slots:
        start_str = ts.start.strftime("%H:%M")
        end_str = ts.end.strftime("%H:%M")
        label = f"{start_str}-{end_str}"
        row: list[str] = [label]
        for d in dates:
            student_num = assignment_map.get((d, ts.start))
            row.append(str(student_num) if student_num is not None else "")
        rows.append(row)

    return rows


def _build_table(
    data: list[list[str]],
    col_widths: list[float],
    cell_font_size: int,
) -> Table:
    """ReportLab Table オブジェクトを構築してスタイルを適用する。"""
    n_rows = len(data)
    n_cols = len(data[0]) if data else 1

    table = Table(data, colWidths=col_widths, repeatRows=1)

    # テーブルスタイル
    style_commands: list[tuple[Any, ...]] = [
        # 全セル: フォント・文字サイズ・中央揃え・パディング
        ("FONTNAME", (0, 0), (-1, -1), _FONT_NAME),
        ("FONTSIZE", (0, 0), (-1, -1), cell_font_size),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        # ヘッダ行: 背景色・太字代替（フォントは同一のため背景で区別）
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4A90A4")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, 0), _HEADER_FONT_SIZE),
        # 時間帯ラベル列: 薄いグレー背景
        ("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#F0F0F0")),
        # 全セルに罫線
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        # ヘッダ行下の太線
        ("LINEBELOW", (0, 0), (-1, 0), 1.5, colors.HexColor("#2C5F6E")),
        # 奇数行と偶数行で交互の背景色（データ行）
    ]

    # 偶数データ行（index 2, 4, 6, ...）に薄い背景
    for row_idx in range(2, n_rows, 2):
        style_commands.append(
            ("BACKGROUND", (1, row_idx), (-1, row_idx), colors.HexColor("#F8F8FF"))
        )

    table.setStyle(TableStyle(style_commands))
    return table
