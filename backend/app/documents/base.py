"""Shared layout for customer-facing PDFs (quotations, invoices, credit notes, receipts,
inspection reports).

Documents are drawn from the same read models the API returns, so they show exactly what
staff see on screen; no amounts are calculated here. Built-in PDF fonts (Helvetica) are
used so generation needs no font files or network access. Colours follow the product
palette: deep slate text, thin borders, no orange text (CLAUDE.md §9).
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from typing import Any
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

SLATE = colors.HexColor("#202A34")
STEEL = colors.HexColor("#30485B")
MUTED = colors.HexColor("#5B6670")
BORDER = colors.HexColor("#DDE2E6")
MIST = colors.HexColor("#F3F5F6")

PAGE_W, PAGE_H = A4
MARGIN = 16 * mm
# SimpleDocTemplate frames add 6pt padding on each side.
CONTENT_W = PAGE_W - 2 * MARGIN - 12


def _style(name: str, **kw: Any) -> ParagraphStyle:
    base = {"fontName": "Helvetica", "fontSize": 9, "leading": 12, "textColor": SLATE}
    return ParagraphStyle(name, **{**base, **kw})


S = {
    "body": _style("body"),
    "small": _style("small", fontSize=8, leading=10, textColor=MUTED),
    "org": _style("org", fontName="Helvetica-Bold", fontSize=13, leading=16),
    "title": _style(
        "title", fontName="Helvetica-Bold", fontSize=16, leading=20, alignment=TA_RIGHT
    ),
    "h2": _style(
        "h2", fontName="Helvetica-Bold", fontSize=10, leading=13, spaceBefore=8, spaceAfter=3
    ),
    "label": _style("label", fontSize=7.5, leading=9, textColor=MUTED),
    "right": _style("right", alignment=TA_RIGHT),
    "right_bold": _style("right_bold", fontName="Helvetica-Bold", alignment=TA_RIGHT),
    "bold": _style("bold", fontName="Helvetica-Bold"),
    "notice": _style("notice", fontName="Helvetica-Bold", fontSize=9, textColor=SLATE),
}


def text(value: Any) -> str:
    """Escape user-entered text for ReportLab paragraph markup and keep line breaks."""
    return escape("" if value is None else str(value)).replace("\n", "<br/>")


def p(value: Any, style: str = "body") -> Paragraph:
    return Paragraph(text(value), S[style])


def money(amount: Decimal | str, currency: str) -> str:
    """N$ 1,234.50 — same format as the web app."""
    value = Decimal(str(amount))
    symbol = "N$" if currency == "NAD" else currency
    sign = "-" if value < 0 else ""
    return f"{sign}{symbol} {abs(value):,.2f}"


def quantity(value: Decimal | str) -> str:
    q = Decimal(str(value)).normalize()
    return f"{q:f}"


@dataclass(frozen=True)
class OrgInfo:
    name: str
    legal_name: str | None
    address: list[str]
    contact: list[str]
    tax_number: str | None
    registration_number: str | None
    footer: str | None
    date_format: str
    timezone: str

    def date(self, value: date | datetime | None) -> str:
        if value is None:
            return "—"
        if isinstance(value, datetime):
            value = value.astimezone(ZoneInfo(self.timezone)).date()
        return {
            "DD/MM/YYYY": value.strftime("%d/%m/%Y"),
            "MM/DD/YYYY": value.strftime("%m/%d/%Y"),
        }.get(self.date_format, value.isoformat())

    def datetime(self, value: datetime | None) -> str:
        if value is None:
            return "—"
        local = value.astimezone(ZoneInfo(self.timezone))
        return f"{self.date(local)} {local:%H:%M}"


@dataclass(frozen=True)
class Party:
    name: str
    lines: list[str] = field(default_factory=list)


@dataclass
class Document:
    """One PDF. `meta` appears under the title (number, dates); `body` is the content."""

    org: OrgInfo
    title: str
    meta: list[tuple[str, str]]
    customer: Party | None = None
    vehicle: list[tuple[str, str]] = field(default_factory=list)
    notice: str | None = None
    body: list[Flowable] = field(default_factory=list)
    party_label: str = "Customer"

    def render(self) -> bytes:
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=MARGIN,
            rightMargin=MARGIN,
            topMargin=MARGIN,
            bottomMargin=MARGIN + 8 * mm,
            title=self.title,
            author=self.org.name,
            creator="WorkshopPro",
        )
        story: list[Flowable] = [self._header(), Spacer(1, 6 * mm)]
        if self.notice:
            story += [_box([p(self.notice, "notice")]), Spacer(1, 4 * mm)]
        parties = self._parties()
        if parties:
            story += [parties, Spacer(1, 5 * mm)]
        story += self.body
        doc.build(story, onFirstPage=self._footer, onLaterPages=self._footer)
        return buffer.getvalue()

    def _header(self) -> Table:
        o = self.org
        left: list[Flowable] = [p(o.name, "org")]
        if o.legal_name and o.legal_name != o.name:
            left.append(p(o.legal_name, "small"))
        for line in [*o.address, *o.contact]:
            left.append(p(line, "small"))
        ids = []
        if o.tax_number:
            ids.append(f"Tax number {o.tax_number}")
        if o.registration_number:
            ids.append(f"Registration {o.registration_number}")
        if ids:
            left.append(p(" · ".join(ids), "small"))

        meta = Table(
            [[p(label, "label"), p(value, "right")] for label, value in self.meta],
            colWidths=[30 * mm, 45 * mm],
            hAlign="RIGHT",
        )
        meta.setStyle(_plain())
        right: list[Flowable] = [p(self.title, "title"), Spacer(1, 2 * mm), meta]
        t = Table([[left, right]], colWidths=[CONTENT_W - 80 * mm, 80 * mm])
        t.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.75, SLATE),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4 * mm),
                ]
            )
        )
        return t

    def _parties(self) -> Table | None:
        cells: list[list[Flowable]] = []
        if self.customer:
            cells.append(
                [p(self.party_label, "label"), p(self.customer.name, "bold")]
                + [p(line) for line in self.customer.lines]
            )
        if self.vehicle:
            cells.append(
                [p("Vehicle", "label")]
                + [p(f"{label}: {value}" if label else value) for label, value in self.vehicle]
            )
        if not cells:
            return None
        widths = [CONTENT_W / len(cells)] * len(cells)
        t = Table([cells], colWidths=widths)
        t.setStyle(_plain(valign="TOP"))
        return t

    def _footer(self, canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setStrokeColor(BORDER)
        canvas.line(MARGIN, MARGIN + 5 * mm, PAGE_W - MARGIN, MARGIN + 5 * mm)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        footer = (self.org.footer or "").replace("\n", " · ")[:180]
        if footer:
            canvas.drawString(MARGIN, MARGIN + 1.5 * mm, footer)
        canvas.drawRightString(PAGE_W - MARGIN, MARGIN + 1.5 * mm, f"Page {doc.page}")
        canvas.restoreState()


def _plain(valign: str = "TOP") -> TableStyle:
    return TableStyle(
        [
            ("VALIGN", (0, 0), (-1, -1), valign),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]
    )


def _box(flowables: list[Flowable]) -> Table:
    t = Table([[flowables]], colWidths=[CONTENT_W])
    t.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.75, SLATE),
                ("BACKGROUND", (0, 0), (-1, -1), MIST),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return t


def heading(value: str) -> Paragraph:
    return p(value, "h2")


def data_table(
    header: Sequence[str],
    rows: Iterable[Sequence[Any]],
    widths: Sequence[float],
    *,
    right_cols: Sequence[int] = (),
) -> Table:
    """A dense bordered table. Cells may be strings or flowables; right_cols are numeric."""

    def cell(value: Any, col: int, head: bool = False) -> Flowable | list[Flowable]:
        if isinstance(value, Flowable):
            return value
        if isinstance(value, list | tuple):  # several flowables stacked in one cell
            return list(value)
        style = "label" if head else ("right" if col in right_cols else "body")
        if head and col in right_cols:
            return Paragraph(
                text(value), ParagraphStyle("hr", parent=S["label"], alignment=TA_RIGHT)
            )
        return p(value, style)

    data = [[cell(h, i, True) for i, h in enumerate(header)]] if header else []
    data += [[cell(v, i) for i, v in enumerate(row)] for row in rows]
    t = Table(data, colWidths=list(widths), repeatRows=1 if header else 0)
    t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (-1, 0), MIST if header else colors.white),
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, BORDER),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return t


def totals(rows: list[tuple[str, str]], *, bold_last: bool = True) -> Table:
    data = []
    for i, (label, value) in enumerate(rows):
        strong = bold_last and i == len(rows) - 1
        data.append(
            [
                p(label, "right_bold" if strong else "right"),
                p(value, "right_bold" if strong else "right"),
            ]
        )
    t = Table(data, colWidths=[45 * mm, 35 * mm], hAlign="RIGHT")
    style = _plain()
    if bold_last and rows:
        style.add("LINEABOVE", (0, len(rows) - 1), (-1, len(rows) - 1), 0.75, SLATE)
    t.setStyle(style)
    return t


def keep(*flowables: Flowable) -> KeepTogether:
    return KeepTogether(list(flowables))


def paragraph_block(title: str, value: str | None) -> list[Flowable]:
    if not value:
        return []
    return [heading(title), p(value)]


def small(value: str) -> Paragraph:
    return p(value, "small")
