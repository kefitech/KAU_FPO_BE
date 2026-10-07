"""
DPR DOCX renderer — editable Word-file counterpart to the PDF.

KAU 2026-09-26 finalisation ask C.3:
    "The final DPR can be downloadable as DPR (Word). Will be helpful in
     rearranging and editing fitting every company's own narrative."

We produce a clean, structurally-editable .docx with the same content the
PDF renders — cover page, project-at-a-glance, cost + means-of-finance
tables, products, and all 11 AI narrative chapters. Not intended to match
the PDF pixel-for-pixel — python-docx lacks the layout primitives — but
content parity means an FPO / consultant can rearrange, edit, and re-brand
the document without losing any of the AI-generated draft.

Public entry points:
    * `render_docx_for_project(project) -> bytes`   — in-memory DOCX bytes
    * `save_docx_to_disk(project, path) -> path`    — dev/debug write

Author: Athul Gopan (Kefi Tech Solutions)
"""
from __future__ import annotations

import base64
import io
from datetime import datetime
from decimal import Decimal
from typing import Optional

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Inches, Mm, Pt, RGBColor

from apps.fpo.services.dpr.calculation import CalculationResult, compute
from apps.fpo.services.dpr.enum_display import (
    enum_display as _enum_display,
    display_or_undisclosed as _disclosed_or_default,
)
from apps.fpo.services.dpr.chart_helpers import (
    cost_breakdown_pie,
    pnl_trend_bar,
    repayment_schedule_bar,
)
from apps.fpo.services.dpr.pdf import (
    COST_LABELS,
    MOF_LABELS,
    _ai_chapters_for_pdf,
    _breakdown_rows,
    _debt_equity_ratio_display,
    _key_assumptions_rows,
    _products_for_pdf,
    _technologies_with_flow,
)

# KAU navy + orange, matching the PDF cover so the DOCX still feels part of
# the same product suite.
_KAU_NAVY = RGBColor(0x1F, 0x38, 0x64)
_KAU_ORANGE = RGBColor(0xE8, 0x6C, 0x1A)


# The 11 AI narrative chapters. Kept as a local tuple rather than importing
# CHAPTER_KEYS so this file survives even if that constant moves.
_CHAPTER_ORDER = (
    ('executive_summary', 'Executive Summary'),
    ('project_background', 'Project Background'),
    ('promoter_profile', 'Promoter Profile'),
    ('market_analysis', 'Market Analysis'),
    ('technical_feasibility', 'Technical Feasibility'),
    ('implementation_plan', 'Implementation Plan'),
    ('financial_analysis', 'Financial Analysis'),
    ('risk_analysis', 'Risk Analysis'),
    ('swot', 'SWOT Analysis'),
    ('environmental_impact', 'Environmental Impact'),
    ('conclusion', 'Conclusion'),
)


def _indian_group(int_str: str) -> str:
    """Format an unsigned integer string with Indian comma grouping
    (`1234567` → `12,34,567`)."""
    if len(int_str) <= 3:
        return int_str
    head, tail = int_str[:-3], int_str[-3:]
    pieces: list[str] = []
    while len(head) > 2:
        pieces.insert(0, head[-2:])
        head = head[:-2]
    if head:
        pieces.insert(0, head)
    return ','.join(pieces) + ',' + tail


def _fmt_inr(amount: Optional[Decimal]) -> str:
    """Render a Decimal ₹ amount as `₹ 12,34,567.89` (Indian numbering).

    Legacy helper kept for the few prose-style spots (cover headline, loan
    headline). Table cells use `_fmt_inr_table` instead so the Word output
    matches the PDF (no ₹ symbol, no paise — rounded to nearest rupee).
    """
    if amount is None:
        return '—'
    negative = amount < 0
    a = abs(amount).quantize(Decimal('0.01'))
    int_part, _, dec_part = str(a).partition('.')
    int_part = _indian_group(int_part)
    sign = '-' if negative else ''
    return f'₹ {sign}{int_part}.{dec_part or "00"}'


def _fmt_inr_table(amount: Optional[Decimal]) -> str:
    """Render a Decimal as a plain table cell: Indian comma grouping, no ₹
    symbol, no paise, accounting-style negatives — e.g. `6,00,000` or
    `(25,00,000)`.

    WP-11 (UAT): PDF money filter emits exactly this form; the old Word
    helper was adding `₹` and `.00` paise on every value which bloated
    columns and read as inconsistent next to the PDF.

    NEW-1 (UAT round-2): uses ROUND_HALF_UP so .5 always rounds UP
    (32,812.5 → 32,813, not 32,812 as Python's default ROUND_HALF_EVEN
    produces). Matches typical banking + schedule convention.
    """
    if amount is None:
        return '—'
    from decimal import ROUND_HALF_UP
    rounded = int(amount.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    if rounded == 0:
        return '0'
    s = _indian_group(str(abs(rounded)))
    return f'({s})' if rounded < 0 else s


def _fmt_pct(v, suffix: str = '%') -> str:
    """Percentage renderer that strips trailing .00 — `Decimal('68.00')` →
    `68%` (WP-11)."""
    if v is None:
        return '—'
    s = str(v)
    # Strip trailing zeros after the decimal point, then a dangling dot.
    if '.' in s:
        s = s.rstrip('0').rstrip('.')
    return f'{s}{suffix}'


def _fmt_num(v, suffix: str = '') -> str:
    """Legacy no-op formatter kept for callers that still need the raw
    decimal pass-through. Prefer `_fmt_pct` for percentages and
    `_fmt_inr_table` for currency."""
    if v is None:
        return '—'
    return f'{v}{suffix}'


# WP-05 (UAT Word-vs-PDF): map every risk class to a reader-friendly label +
# a hex colour. Shared across the overall badge, per-category class column,
# and any future risk-chapter use. `no_risks` and `not_assessed` are the two
# post-RCD classes that previously rendered as `No_risks` and `Not_assessed`
# in Word because the code called `.capitalize()` on the raw code.
_RISK_DISPLAY = {
    'low':          ('Low',               RGBColor(0x2E, 0x7D, 0x32)),
    'moderate':     ('Moderate',          RGBColor(0xB4, 0x60, 0x00)),
    'high':         ('High',              RGBColor(0xC0, 0x2D, 0x2D)),
    'not_assessed': ('Not assessed',      RGBColor(0x55, 0x55, 0x55)),
    'no_risks':     ('No risks entered',  RGBColor(0x55, 0x55, 0x55)),
}


def _risk_display(cls: str) -> tuple[str, RGBColor]:
    key = (cls or '').lower()
    return _RISK_DISPLAY.get(key, (key.replace('_', ' ').capitalize() or '—',
                                    RGBColor(0x33, 0x33, 0x33)))


def _bookmark_id_counter() -> int:
    """Monotonic bookmark id shared across the whole document."""
    _bookmark_id_counter.n = getattr(_bookmark_id_counter, 'n', 0) + 1
    return _bookmark_id_counter.n


def _add_bookmark(paragraph, bookmark_name: str) -> None:
    """Wrap the paragraph's content in bookmarkStart/bookmarkEnd so an
    internal hyperlink can target `bookmark_name`. python-docx has no direct
    API — go via raw OOXML."""
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    bid = str(_bookmark_id_counter())
    start = OxmlElement('w:bookmarkStart')
    start.set(qn('w:id'), bid)
    start.set(qn('w:name'), bookmark_name)
    end = OxmlElement('w:bookmarkEnd')
    end.set(qn('w:id'), bid)
    # Insert bookmark BEFORE the first run of the paragraph, close AFTER the
    # last run. Word/Google Docs treat this as the click target.
    paragraph._p.insert(0, start)
    paragraph._p.append(end)


def _add_heading(doc, text: str, level: int = 1,
                 bookmark: Optional[str] = None) -> None:
    """Add a heading with KAU navy colour and (optionally) an anchor
    bookmark so TOC hyperlinks can jump straight to it."""
    h = doc.add_heading(text, level=level)
    for run in h.runs:
        run.font.color.rgb = _KAU_NAVY
    if bookmark:
        _add_bookmark(h, bookmark)


def _add_toc_hyperlink(paragraph, anchor: str, text: str) -> None:
    """Turn `text` inside `paragraph` into a clickable internal hyperlink
    pointing to bookmark `anchor`. Styles it like a Word TOC entry —
    default text colour + underline appears when the reader hovers /
    Ctrl-clicks it, matching Word's native TOC behaviour."""
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    hyperlink = OxmlElement('w:hyperlink')
    hyperlink.set(qn('w:anchor'), anchor)
    hyperlink.set(qn('w:history'), '1')

    new_run = OxmlElement('w:r')
    rPr = OxmlElement('w:rPr')
    # Apply Hyperlink style so the entry looks like a Word link on click.
    rStyle = OxmlElement('w:rStyle')
    rStyle.set(qn('w:val'), 'Hyperlink')
    rPr.append(rStyle)
    new_run.append(rPr)

    t = OxmlElement('w:t')
    t.text = text
    t.set(qn('xml:space'), 'preserve')
    new_run.append(t)

    hyperlink.append(new_run)
    paragraph._p.append(hyperlink)


def _add_para(doc, text: str, *, bold: bool = False, italic: bool = False,
              size: Optional[int] = None, colour: Optional[RGBColor] = None) -> None:
    p = doc.add_paragraph()
    run = p.add_run(text)
    if bold:
        run.bold = True
    if italic:
        run.italic = True
    if size is not None:
        run.font.size = Pt(size)
    if colour is not None:
        run.font.color.rgb = colour


def _embed_data_url_chart(doc, data_url: str, width_inches: float = 6.0) -> None:
    """Decode a `data:image/png;base64,...` chart into bytes and embed.

    Silently no-ops when `data_url` is empty (chart helpers return `''` when
    the input data is insufficient — same convention as the PDF template).
    """
    if not data_url or not data_url.startswith('data:image/'):
        return
    try:
        _prefix, _, b64 = data_url.partition('base64,')
        if not b64:
            return
        raw = base64.b64decode(b64)
    except Exception:  # noqa: BLE001 — chart embed is best-effort
        return
    doc.add_picture(io.BytesIO(raw), width=Inches(width_inches))


def _embed_image_file(doc, path: str, width_inches: float = 5.5) -> None:
    """Embed a local image file (hero image, product photo). No-op on bad path."""
    if not path:
        return
    try:
        with open(path, 'rb') as f:
            data = f.read()
    except Exception:  # noqa: BLE001
        return
    try:
        doc.add_picture(io.BytesIO(data), width=Inches(width_inches))
    except Exception:  # noqa: BLE001 — python-docx rejects some image formats
        return


def _tag_header_row_repeat(table) -> None:
    """Mark the first row of `table` as a header row that repeats across page
    breaks (WP-10). python-docx has no API for this — set <w:tblHeader/> in
    the row's <w:trPr> directly."""
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    tr = table.rows[0]._tr
    trPr = tr.find(qn('w:trPr'))
    if trPr is None:
        trPr = OxmlElement('w:trPr')
        tr.insert(0, trPr)
    tbl_header = OxmlElement('w:tblHeader')
    tbl_header.set(qn('w:val'), 'true')
    trPr.append(tbl_header)


def _style_header_row_navy(table) -> None:
    """NEW-3 (UAT round-2): give the first row a KAU-navy fill with white
    bold text — matches the PDF table-header visual. Previously tables used
    the default `Light Grid Accent 1` light-blue header which read as
    casually inconsistent next to the PDF."""
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    for cell in table.rows[0].cells:
        tc_pr = cell._tc.get_or_add_tcPr()
        shading = OxmlElement('w:shd')
        shading.set(qn('w:val'), 'clear')
        shading.set(qn('w:color'), 'auto')
        shading.set(qn('w:fill'), '1F3864')  # KAU navy hex
        tc_pr.append(shading)
        for para in cell.paragraphs:
            for run in para.runs:
                run.bold = True
                run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)


def _start_landscape_section(doc) -> None:
    """WP-10 round-4 (UAT): wrap wide multi-year tables in a landscape
    A4 section so year columns fit without wrapping on long values.

    Depreciation / P&L / Cash Flow / Balance Sheet have 12-14 columns.
    Portrait A4 at 17 cm text frame gives ~572-743 twips per year
    column after the label; after cell padding, values up to 1,19,02,128
    (38.4 pt at Calibri 8 pt) break onto two lines. Landscape widens the
    text frame to 25.7 cm so each year column gets ~46 pt usable width
    — comfortable for 8-digit INR values.

    `_end_landscape_section` closes the block back to portrait so later
    sections (ratios, risk, products, AI chapters) are not stuck in
    landscape.
    """
    from docx.enum.section import WD_ORIENT, WD_SECTION
    section = doc.add_section(start_type=WD_SECTION.NEW_PAGE)
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width = Mm(297)
    section.page_height = Mm(210)
    section.top_margin = Cm(2)
    section.bottom_margin = Cm(2)
    section.left_margin = Cm(2)
    section.right_margin = Cm(2)


def _end_landscape_section(doc) -> None:
    """Close the landscape block and return to portrait A4 for later
    sections. See `_start_landscape_section`."""
    from docx.enum.section import WD_ORIENT, WD_SECTION
    section = doc.add_section(start_type=WD_SECTION.NEW_PAGE)
    section.orientation = WD_ORIENT.PORTRAIT
    section.page_width = Mm(210)
    section.page_height = Mm(297)
    section.top_margin = Cm(2)
    section.bottom_margin = Cm(2)
    section.left_margin = Cm(2)
    section.right_margin = Cm(2)


def _fix_table_width_to_text_frame(table, landscape: bool = False) -> None:
    """Clamp a table's rendered width to the current page's text frame and
    switch to fixed layout so Word respects column widths without
    auto-expanding to the widest cell content.

    WP-10 round-3: wrote tblLayout/tblW/tblGrid via raw OOXML.
    WP-10 round-4: `landscape=True` targets the wider landscape A4 text
    frame (14580 dxa ≈ 25.7 cm) instead of portrait's 9638 dxa (17 cm).
    Narrows the label column slightly so year columns breathe.
    """
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    tbl = table._tbl
    tbl_pr = tbl.find(qn('w:tblPr'))
    if tbl_pr is None:
        tbl_pr = OxmlElement('w:tblPr')
        tbl.insert(0, tbl_pr)
    layout = tbl_pr.find(qn('w:tblLayout'))
    if layout is None:
        layout = OxmlElement('w:tblLayout')
        tbl_pr.append(layout)
    layout.set(qn('w:type'), 'fixed')
    # NEW-6 round-5 (UAT): landscape text frame is 14570 twips (25.7 cm with
    # 2 cm margins), not 14580 — the earlier 10-twip overrun pushed the right
    # cell border past the margin by 0.5 pt. Cosmetic but easy to fix.
    frame_dxa = 14570 if landscape else 9638
    label_dxa = 1900 if landscape else 2200
    tbl_w = tbl_pr.find(qn('w:tblW'))
    if tbl_w is None:
        tbl_w = OxmlElement('w:tblW')
        tbl_pr.append(tbl_w)
    tbl_w.set(qn('w:w'), str(frame_dxa))
    tbl_w.set(qn('w:type'), 'dxa')
    cols = list(table.columns)
    n = len(cols)
    if n > 1:
        remaining = frame_dxa - label_dxa
        per = remaining // (n - 1)
        widths = [label_dxa] + [per] * (n - 1)
        widths[-1] = frame_dxa - sum(widths[:-1])
        for col, w in zip(cols, widths):
            col.width = Pt(w / 20)
        grid = tbl.find(qn('w:tblGrid'))
        if grid is None:
            grid = OxmlElement('w:tblGrid')
            tbl.insert(1, grid)
        for g in grid.findall(qn('w:gridCol')):
            grid.remove(g)
        for w in widths:
            gc = OxmlElement('w:gridCol')
            gc.set(qn('w:w'), str(w))
            grid.append(gc)


def _set_body_font_size(table, size_pt: int) -> None:
    """WP-10 (UAT round-2 Partial): shrink body cells on wide tables so
    year columns don't wrap. Applied to tables with ≥7 columns
    (Depreciation, P&L, Cash Flow, Balance Sheet, Capital Schedule)."""
    for row in table.rows[1:]:
        for cell in row.cells:
            for para in cell.paragraphs:
                for run in para.runs:
                    run.font.size = Pt(size_pt)


def _set_header_font_size(table, size_pt: int) -> None:
    """NEW-7 round-5 (UAT): shrink header row text on wide tables so column
    titles like "Initial cost" fit on one line in narrow data columns.
    Header stays bold; only size is reduced."""
    for cell in table.rows[0].cells:
        for para in cell.paragraphs:
            for run in para.runs:
                run.font.size = Pt(size_pt)


def _add_multi_year_table(
    doc,
    label: str,
    rows: list[dict],
    formatter=lambda v: _fmt_inr_table(v),
    heading_level: int = 1,
) -> None:
    """Render a multi-year financial table.

    `rows` is a list of dicts like `[{'label': 'Revenue', 'y1': ..., 'y2': ...}]`.
    Column headers come from the union of numeric keys sorted, so the caller
    doesn't have to hand-write header rows.

    WP-11 (UAT): default formatter is now `_fmt_inr_table` so cells read as
    `6,00,000` / `(25,00,000)` instead of `₹ 6,00,000.00`.

    WP-10 (UAT): the header row is tagged `<w:tblHeader/>` so Word repeats
    it when the table spills across a page.
    """
    if not rows:
        return
    if label:
        _add_heading(doc, label, level=heading_level)
    year_keys = sorted(
        {k for r in rows for k in r.keys() if k not in ('label',)},
        key=lambda k: (len(k), k),
    )
    header = ['Line'] + [k.upper() for k in year_keys]
    table = doc.add_table(rows=len(rows) + 1, cols=len(header))
    table.style = 'Light Grid Accent 1'
    for i, h in enumerate(header):
        cell = table.rows[0].cells[i]
        cell.text = h
        for para in cell.paragraphs:
            for run in para.runs:
                run.bold = True
    _tag_header_row_repeat(table)
    _style_header_row_navy(table)
    for i, row in enumerate(rows, start=1):
        cells = table.rows[i].cells
        cells[0].text = str(row.get('label') or '—')
        for j, k in enumerate(year_keys, start=1):
            v = row.get(k)
            cells[j].text = formatter(v) if v is not None else '—'
    # WP-10 (UAT round-2): wide multi-year tables (≥8 cols including the
    # label) shrink body cells to 8 pt so Y7–Y10 columns don't wrap.
    # Round-3: ALSO clamp table width via tblLayout=fixed + tblW.
    # Round-4: multi-year tables (P&L / Cash Flow / Balance Sheet) are
    # rendered inside the landscape section opened in the main orchestrator,
    # so the width-fix targets the 25.7 cm landscape text frame.
    # Round-5 NEW-7: header font also shrinks to 9 pt so long column titles
    # ("Initial cost") fit without wrapping onto a second line.
    if len(header) >= 8:
        _set_body_font_size(table, 8)
        _set_header_font_size(table, 8)
        _fix_table_width_to_text_frame(table, landscape=True)


def _add_two_col_table(doc, rows: list[tuple[str, str]]) -> None:
    """Add a 2-column key/value table. Skips rows where value is empty."""
    filtered = [(k, v) for k, v in rows if v not in ('', None, '—')]
    if not filtered:
        return
    table = doc.add_table(rows=len(filtered), cols=2)
    table.style = 'Light Grid Accent 1'
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    for i, (key, value) in enumerate(filtered):
        table.rows[i].cells[0].text = str(key)
        table.rows[i].cells[1].text = str(value)
        # First column bold so it reads as a label.
        for para in table.rows[i].cells[0].paragraphs:
            for run in para.runs:
                run.bold = True


def _set_cell_border(cell, *, color: str = 'DDDDDD', size_pt: float = 0.75) -> None:
    """Apply a border on all 4 sides of a table cell via raw OOXML.

    python-docx has no direct API for cell borders — we go through the
    <w:tcPr>/<w:tcBorders> tree. `color` is a 6-char hex without leading #.
    `size_pt` is measured in eighths of a point (Word convention) — a 0.75pt
    line is `sz="6"` in OOXML.
    """
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_borders = OxmlElement('w:tcBorders')
    sz = str(int(round(size_pt * 8)))
    for edge in ('top', 'left', 'bottom', 'right'):
        el = OxmlElement(f'w:{edge}')
        el.set(qn('w:val'), 'single')
        el.set(qn('w:sz'), sz)
        el.set(qn('w:color'), color)
        tc_borders.append(el)
    tc_pr.append(tc_borders)


def _set_cell_shading(cell, hex_color: str) -> None:
    """Fill a cell with a background colour (6-char hex, no leading #)."""
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hex_color)
    tc_pr.append(shd)


def _render_cover(doc, project, version_label: str, generated_at: str,
                  projection_years: Optional[int] = None) -> None:
    """Cover page — 1:1 with the PDF cover recipe in report.html §.cover.

    Element order (top → bottom):
      1. FPO name (22pt navy, bold)
      2. FPO location (12pt italic gray — district + Kerala, or fallback)
      3. "Detailed Project Report" title (32pt navy, bold)
      4. "Prepared under the KAU-FPO Linkage Programme" (13pt gray)
      5. Project title (15pt orange, bold)
      6. Hero image (if any product has a photo)
      7. Bordered meta-block: DPR Version / Generated / Status / Horizon / Commodity
      8. Platform attribution (italic light gray)
      9. Orange-bordered disclaimer box with uppercase title + body
     10. Page break
    """
    # Small helper to add a single centred paragraph with styled text.
    def _cover_para(text: str, *, size: int, color: RGBColor = None,
                    bold: bool = False, italic: bool = False,
                    space_after_pt: int = 0) -> None:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(text)
        run.font.size = Pt(size)
        if color is not None:
            run.font.color.rgb = color
        run.bold = bold
        run.italic = italic
        if space_after_pt:
            p.paragraph_format.space_after = Pt(space_after_pt)

    # ── 1. FPO name ──
    fpo_name = project.fpo.name if project.fpo_id else '—'
    _cover_para(fpo_name, size=22, color=_KAU_NAVY, bold=True, space_after_pt=4)

    # ── 2. FPO location ──
    district_display = ''
    if project.fpo_id and getattr(project.fpo, 'district', None):
        fpo = project.fpo
        try:
            district_display = fpo.get_district_display() or fpo.district
        except Exception:  # noqa: BLE001
            district_display = fpo.district
    location_text = f'{district_display}, Kerala' if district_display else 'Farmer Producer Organisation'
    _cover_para(location_text, size=12, color=RGBColor(0x66, 0x66, 0x66),
                italic=True, space_after_pt=24)

    # ── 3. Title ──
    _cover_para('Detailed Project Report', size=32, color=_KAU_NAVY,
                bold=True, space_after_pt=8)

    # ── 4. Subtitle ──
    _cover_para('Prepared under the KAU-FPO Linkage Programme',
                size=13, color=RGBColor(0x44, 0x44, 0x44), space_after_pt=40)

    # ── 5. Project name (orange) ──
    _cover_para(project.title or 'Untitled Project', size=15, color=_KAU_ORANGE,
                bold=True, space_after_pt=30)

    # ── 6. Hero image ──
    _, hero_path = _products_for_pdf(project)
    if hero_path:
        _embed_image_file(doc, hero_path, width_inches=3.2)
        doc.add_paragraph()  # visual spacer between hero + meta box

    # ── 7. Meta-block — a 1-column table so we can put a border around
    #      the content. Each row: bold-navy label + value.
    commodity_name = ''
    if project.primary_commodity_id:
        try:
            commodity_name = project.primary_commodity.get_name('en') or ''
        except Exception:  # noqa: BLE001
            commodity_name = ''
    try:
        status_display = project.get_status_display() if hasattr(project, 'get_status_display') else str(project.status)
    except Exception:  # noqa: BLE001
        status_display = str(getattr(project, 'status', '—'))

    meta_rows: list[tuple[str, str]] = [
        ('DPR Version:', version_label),
        ('Generated:', generated_at),
        ('Status:', status_display),
    ]
    if projection_years is not None:
        meta_rows.append(('Projection horizon:', f'{projection_years} years'))
    if commodity_name:
        meta_rows.append(('Primary commodity:', commodity_name))

    # Build a centered 2-col table for the meta block. python-docx doesn't
    # auto-center a table — we set the row alignment on each cell + wrap
    # in a paragraph-alignment trick isn't possible without OOXML. Instead
    # we simply set column widths tight enough that the natural layout
    # feels centered on the page.
    meta_table = doc.add_table(rows=len(meta_rows), cols=2)
    meta_table.autofit = False
    meta_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, (label, value) in enumerate(meta_rows):
        cell_l, cell_v = meta_table.rows[i].cells
        cell_l.width = Inches(1.9)
        cell_v.width = Inches(2.8)
        # Label — bold navy, right-aligned so labels align to their values.
        cell_l.text = ''
        p_l = cell_l.paragraphs[0]
        p_l.alignment = WD_ALIGN_PARAGRAPH.LEFT
        run_l = p_l.add_run(label)
        run_l.bold = True
        run_l.font.color.rgb = _KAU_NAVY
        run_l.font.size = Pt(10.5)
        # Value
        cell_v.text = ''
        p_v = cell_v.paragraphs[0]
        run_v = p_v.add_run(str(value))
        run_v.font.size = Pt(10.5)
        # Light-grey border + very light background so the block feels boxed.
        _set_cell_border(cell_l, color='DDDDDD', size_pt=0.75)
        _set_cell_border(cell_v, color='DDDDDD', size_pt=0.75)
        _set_cell_shading(cell_l, 'FAFAFA')
        _set_cell_shading(cell_v, 'FAFAFA')

    # ── 8. Platform attribution ──
    doc.add_paragraph()  # small spacer
    _cover_para('Prepared using the Kerala Agricultural University DPR platform',
                size=9, color=RGBColor(0x99, 0x99, 0x99), italic=True,
                space_after_pt=16)

    # ── 9. Disclaimer box — orange border, warm background ──
    disc_table = doc.add_table(rows=1, cols=1)
    disc_table.autofit = False
    disc_cell = disc_table.rows[0].cells[0]
    disc_cell.width = Inches(6.0)
    disc_cell.text = ''
    # Title
    p_title = disc_cell.paragraphs[0]
    p_title.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run_t = p_title.add_run('DISCLAIMER')
    run_t.bold = True
    run_t.font.size = Pt(8)
    run_t.font.color.rgb = RGBColor(0x9A, 0x34, 0x12)  # #9a3412
    # Body
    p_body = disc_cell.add_paragraph()
    p_body.alignment = WD_ALIGN_PARAGRAPH.LEFT
    body = (
        'This Detailed Project Report has been prepared by the above-named '
        'Farmer Producer Organisation using the Kerala Agricultural University '
        '(KAU) DPR platform. Generation of this report through the platform '
        'does not imply that KAU has approved, certified or endorsed its '
        'contents. Its acceptance for bank submission, scheme application or '
        'any other purpose is subject to the requirements of the concerned '
        'bank, implementing agency or authority. Figures are rounded to the '
        'nearest rupee.'
    )
    run_b = p_body.add_run(body)
    run_b.font.size = Pt(8.5)
    run_b.font.color.rgb = RGBColor(0x78, 0x35, 0x0F)  # #78350f
    _set_cell_border(disc_cell, color='E86C1A', size_pt=1.0)
    _set_cell_shading(disc_cell, 'FFF7ED')  # warm cream
    disc_table.alignment = WD_TABLE_ALIGNMENT.CENTER

    doc.add_page_break()


def _render_project_at_a_glance(doc, project, r: CalculationResult) -> None:
    """1:1 rebuild of the PDF's §1 Project at a Glance (report.html §sec-1).

    17 numbered rows + indented cost / MoF sub-breakdown rows + footer note
    (implementation period · overall risk · variance status). Row numbers on
    the left, bold navy label in the middle, value on the right — matches
    the PDF's `.glance-table` layout column by column.
    """
    _add_heading(doc, '1. Project at a Glance', level=1, bookmark='sec_1')

    fpo = project.fpo if project.fpo_id else None

    # ── Prepare human-readable values ────────────────────────────────────
    def _fmt_natures() -> str:
        parts: list[str] = []
        commodity = ''
        if project.primary_commodity_id:
            try:
                commodity = project.primary_commodity.get_name('en') or ''
            except Exception:  # noqa: BLE001
                commodity = ''
        if commodity:
            parts.append(commodity)
        try:
            pt_names = ', '.join(str(pt) for pt in project.project_types.all())
        except Exception:  # noqa: BLE001
            pt_names = ''
        if pt_names:
            parts.append(pt_names)
        return ' — '.join(parts) if parts else '—'

    district = ''
    if fpo and getattr(fpo, 'district', None):
        try:
            district = fpo.get_district_display() or fpo.district
        except Exception:  # noqa: BLE001
            district = fpo.district
    district_display = f'{district}, Kerala' if district else '—'

    def _pat_first_three() -> str:
        # WP-11 round-3 (UAT): the Glance Y1/Y2/Y3 PAT prose row previously
        # printed "₹ 12,67,433.12" paise-included. Now matches PDF table-cell
        # convention — plain Indian grouping, no ₹, no paise.
        if not r.profit_loss or not r.profit_loss.rows:
            return '—'
        parts = []
        for row in r.profit_loss.rows[:3]:
            parts.append(f'Y{row.year}: {_fmt_inr_table(row.pat)}')
        return ' · '.join(parts)

    def _dscr_avg() -> str:
        if not r.ratios or r.ratios.dscr_avg is None:
            return 'n/a (no debt)'
        return f'{r.ratios.dscr_avg}x'

    def _payback() -> str:
        if not r.ratios or r.ratios.payback_period_years is None:
            return '—'
        return f'{r.ratios.payback_period_years} years'

    def _npv_label() -> tuple[str, str]:
        # WP-11 round-3 (UAT): NPV display switches to the table formatter
        # so Glance reads "84,28,024" matching PDF §1, not "₹ 84,28,024.49".
        rate = r.ratios.discount_rate_pct if r.ratios and r.ratios.discount_rate_pct is not None else None
        label = f'Net Present Value ({_fmt_pct(rate)})' if rate is not None else 'Net Present Value'
        val = _fmt_inr_table(r.ratios.npv) if r.ratios and r.ratios.npv is not None else '—'
        return label, val

    def _irr() -> str:
        # WP-11 round-3 (UAT): strip trailing `.00` so Glance shows "68%"
        # like the PDF, not "68.00%".
        if not r.ratios or r.ratios.irr_pct is None:
            return 'Not solvable — see §11'
        return _fmt_pct(r.ratios.irr_pct)

    def _break_even() -> str:
        if not r.ratios or getattr(r.ratios, 'break_even_year', None) is None:
            return 'Not reached in projection'
        return f'Year {r.ratios.break_even_year}'

    npv_label, npv_value = _npv_label()

    # ── Main rows (17 primary + inline breakdown sub-rows) ───────────────
    top_rows: list[tuple[str, str, str, bool]] = [
        # (row_number, label, value, is_bold_value)
        ('1',  'Name of the proposed project',      project.title or '—', False),
        ('2',  'Name of the FPO',                   (fpo.name if fpo else '—'), False),
        ('3',  'Nature of proposed project',        _fmt_natures(), False),
        ('4',  'District',                          district_display, False),
        ('5',  'Legal structure',                   (_enum_display('legal_structure', getattr(fpo, 'legal_structure', '')) or '—') if fpo else '—', False),
        ('6',  'Number of members / shareholders',  str(getattr(fpo, 'total_members', '') or '—') if fpo else '—', False),
        ('7',  'Promoting agency',                  (_enum_display('promoting_agency', getattr(fpo, 'promoting_agency', '')) or '—') if fpo else '—', False),
        ('8',  'Facilitating agency',               (_disclosed_or_default(getattr(fpo, 'facilitating_agency_name', '')) if fpo else '—'), False),
        ('9',  'Total project cost',                _fmt_inr_table(r.cost.total), True),
    ]
    cost_sub_rows = _breakdown_rows(r.cost.by_field, COST_LABELS)
    # BUG-37: WC facility (cash credit) is not project funding — headline
    # shows project_funding_total; the facility gets its own sub-row.
    mof_row = ('10', 'Means of finance', _fmt_inr_table(r.mof.project_funding_total), True)
    mof_sub_rows = _breakdown_rows(
        {k: v for k, v in r.mof.by_field.items()
         if k != 'mof_working_capital_loan'},
        MOF_LABELS,
    )
    if r.mof.wc_facility:
        mof_sub_rows.append((
            'Working-capital facility (cash credit) — outside project cost',
            r.mof.wc_facility,
        ))
    bottom_rows: list[tuple[str, str, str, bool]] = [
        ('11', 'Debt : Equity ratio',                     _debt_equity_ratio_display(r.mof.by_field), False),
        ('12', 'Profit after tax (PAT) — first 3 years', _pat_first_three(), False),
        ('13', 'Average DSCR',                            _dscr_avg(), False),
        ('14', 'Payback period',                          _payback(), False),
        ('15', npv_label,                                 npv_value, False),
        ('16', 'Internal Rate of Return (IRR)',           _irr(), False),
        ('17', 'Break-even year',                         _break_even(), False),
    ]

    total_rows = (
        len(top_rows) + len(cost_sub_rows) + 1 + len(mof_sub_rows) + len(bottom_rows)
    )
    table = doc.add_table(rows=total_rows, cols=3)
    table.style = 'Light Grid Accent 1'
    table.autofit = False
    # Column widths — mirror the PDF's 8mm / 65mm / rest layout.
    for col, w in zip(table.columns, (Inches(0.35), Inches(2.6), Inches(3.5))):
        col.width = w

    def _emit(idx: int, num: str, label: str, value: str,
              *, bold_value: bool = False, sub: bool = False) -> None:
        cells = table.rows[idx].cells
        for c, w in zip(cells, (Inches(0.35), Inches(2.6), Inches(3.5))):
            c.width = w
        # Row-number cell
        cells[0].text = ''
        p_num = cells[0].paragraphs[0]
        p_num.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run_n = p_num.add_run(num)
        run_n.bold = True
        run_n.font.size = Pt(9)
        run_n.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
        if not sub:
            _set_cell_shading(cells[0], 'F2F2F2')
        # Label cell
        cells[1].text = ''
        p_lbl = cells[1].paragraphs[0]
        if sub:
            # Indented label with leading dot
            p_lbl.paragraph_format.left_indent = Inches(0.25)
            run_l = p_lbl.add_run(f'· {label}')
            run_l.font.size = Pt(9.5)
            run_l.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
            _set_cell_shading(cells[1], 'FAFAFA')
        else:
            run_l = p_lbl.add_run(label)
            run_l.bold = True
            run_l.font.size = Pt(10)
            run_l.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
        # Value cell
        cells[2].text = ''
        p_val = cells[2].paragraphs[0]
        if sub:
            p_val.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            _set_cell_shading(cells[2], 'FAFAFA')
        else:
            p_val.alignment = WD_ALIGN_PARAGRAPH.LEFT
        run_v = p_val.add_run(str(value))
        run_v.font.size = Pt(10)
        run_v.font.color.rgb = _KAU_NAVY
        run_v.bold = bold_value

    idx = 0
    for num, label, value, bold_v in top_rows:
        _emit(idx, num, label, value, bold_value=bold_v)
        idx += 1
    for sub_label, sub_val in cost_sub_rows:
        _emit(idx, '', str(sub_label), _fmt_inr_table(sub_val) if isinstance(sub_val, Decimal) else str(sub_val), sub=True)
        idx += 1
    _emit(idx, mof_row[0], mof_row[1], mof_row[2], bold_value=mof_row[3])
    idx += 1
    for sub_label, sub_val in mof_sub_rows:
        _emit(idx, '', str(sub_label), _fmt_inr_table(sub_val) if isinstance(sub_val, Decimal) else str(sub_val), sub=True)
        idx += 1
    for num, label, value, bold_v in bottom_rows:
        _emit(idx, num, label, value, bold_value=bold_v)
        idx += 1

    # ── Footer note (implementation period · overall risk · variance) ───
    cap = getattr(r, 'capital_schedule', None)
    period_bits = []
    if cap and getattr(cap, 'implementation_period_months', None):
        note = f'Implementation period: {cap.implementation_period_months} months'
        if getattr(cap, 'is_estimated', False):
            note += ' (estimated)'
        period_bits.append(note)
    else:
        period_bits.append('Implementation period: —')
    if r.risk_assessment:
        period_bits.append(f'Overall project risk: {r.risk_assessment.overall_class.capitalize()}')
    if r.variance:
        if r.variance.exceeds_threshold:
            period_bits.append(f'Cost/MoF variance {r.variance.pct}% exceeds threshold')
        elif r.variance.delta != 0:
            period_bits.append(f'Cost/MoF variance {r.variance.pct}%')
        else:
            period_bits.append('Cost/MoF balanced ✓')

    note_p = doc.add_paragraph()
    note_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_note = note_p.add_run(' · '.join(period_bits))
    r_note.italic = True
    r_note.font.size = Pt(9)
    r_note.font.color.rgb = RGBColor(0x66, 0x66, 0x66)


def _render_fixed_capital_investment(doc, r: CalculationResult) -> None:
    """PDF §2 Fixed Capital Investment — cost heads table + pie chart."""
    rows = _breakdown_rows(r.cost.by_field, COST_LABELS)
    if not rows:
        return
    _add_heading(doc, '2. Fixed Capital Investment', level=1, bookmark='sec_2')
    table = doc.add_table(rows=len(rows) + 2, cols=2)
    table.style = 'Light Grid Accent 1'
    # Header
    hdr = table.rows[0].cells
    hdr[0].text = 'Cost head'
    hdr[1].text = 'Amount (₹)'
    for cell in hdr:
        for para in cell.paragraphs:
            for run in para.runs:
                run.bold = True
    # NEW-4 round-3 (UAT): bring §2 header into the KAU-navy style the
    # other data tables already use so the Word output reads consistently.
    _style_header_row_navy(table)
    # Data rows
    for i, (label, value) in enumerate(rows, start=1):
        table.rows[i].cells[0].text = str(label)
        table.rows[i].cells[1].text = _fmt_inr_table(value) if isinstance(value, Decimal) else str(value)
    # Total row
    total_cells = table.rows[-1].cells
    total_cells[0].text = 'Total Project Cost'
    total_cells[1].text = _fmt_inr_table(r.cost.total)
    for cell in total_cells:
        for para in cell.paragraphs:
            for run in para.runs:
                run.bold = True

    # Embed the pie chart underneath the table with a caption.
    _embed_data_url_chart(doc, cost_breakdown_pie(r.cost.by_field), width_inches=5.5)
    caption = doc.add_paragraph()
    caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap_r = caption.add_run('Figure — Distribution of project cost across cost heads')
    cap_r.italic = True
    cap_r.font.size = Pt(9)
    cap_r.font.color.rgb = RGBColor(0x66, 0x66, 0x66)


def _render_cost_breakdown(doc, r: CalculationResult) -> None:
    rows = _breakdown_rows(r.cost.by_field, COST_LABELS)
    if not rows:
        return
    _add_heading(doc, 'Cost Breakdown', level=2)
    table = doc.add_table(rows=len(rows) + 1, cols=2)
    table.style = 'Light Grid Accent 1'
    hdr = table.rows[0].cells
    hdr[0].text = 'Component'
    hdr[1].text = 'Amount'
    for cell in hdr:
        for para in cell.paragraphs:
            for run in para.runs:
                run.bold = True
    for i, (label, value) in enumerate(rows, start=1):
        table.rows[i].cells[0].text = str(label)
        table.rows[i].cells[1].text = _fmt_inr_table(value) if isinstance(value, Decimal) else str(value)


def _render_means_of_finance(doc, r: CalculationResult) -> None:
    """PDF §3 Means of Finance — sources table with total.

    BUG-37: the WC facility (cash credit) is excluded from the sources
    table and shown as a separate note below it — it funds operations,
    not the project, so it never counts toward Total Means of Finance.
    """
    rows = _breakdown_rows(
        {k: v for k, v in r.mof.by_field.items()
         if k != 'mof_working_capital_loan'},
        MOF_LABELS,
    )
    if not rows:
        return
    _add_heading(doc, '3. Means of Finance', level=1, bookmark='sec_3')
    table = doc.add_table(rows=len(rows) + 2, cols=2)
    table.style = 'Light Grid Accent 1'
    hdr = table.rows[0].cells
    hdr[0].text = 'Source'
    hdr[1].text = 'Amount (₹)'
    for cell in hdr:
        for para in cell.paragraphs:
            for run in para.runs:
                run.bold = True
    # NEW-4 round-3 (UAT): §3 header now styled navy-fill + white bold,
    # matching the rest of the data tables.
    _style_header_row_navy(table)
    for i, (label, value) in enumerate(rows, start=1):
        table.rows[i].cells[0].text = str(label)
        table.rows[i].cells[1].text = _fmt_inr_table(value) if isinstance(value, Decimal) else str(value)
    total_cells = table.rows[-1].cells
    total_cells[0].text = 'Total Means of Finance'
    total_cells[1].text = _fmt_inr_table(r.mof.project_funding_total)
    for cell in total_cells:
        for para in cell.paragraphs:
            for run in para.runs:
                run.bold = True
    if r.mof.wc_facility:
        note = doc.add_paragraph()
        note_run = note.add_run(
            'In addition to the project funding above, a working-capital '
            'facility (cash credit) of ₹ '
            f'{_fmt_inr_table(r.mof.wc_facility)} is proposed. This is a '
            'revolving operating line used to fund day-to-day working '
            'capital — it is not part of the project cost or its funding, '
            'and is covered in the Working Capital Statement (§6B).'
        )
        note_run.font.size = Pt(8)
        note_run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
        note_run.italic = True


def _render_products(doc, project) -> None:
    """Render one card per product — photo in left cell, details in right.

    Mirrors the PDF's card layout (report.html §products). Products without a
    photo just render the details cell — the layout still holds because the
    left cell stays empty rather than collapsing.
    """
    products, _hero = _products_for_pdf(project)
    if not products:
        return
    _add_heading(doc, 'Proposed Products & Services', level=1, bookmark='sec_products')
    for p in products:
        img_path = p.get('image_path') or ''

        # BUG-22 (KAU §6): when a product has NO uploaded image, skip the
        # placeholder tile entirely and emit a full-width details-only card.
        # Previously a greyed-out "No photo" tile sat on the left of every
        # photoless product; KAU asked for empty blocks to be hidden.
        if img_path:
            # 1 row × 2 cols. Image on the left (2 inches), details on the right.
            card = doc.add_table(rows=1, cols=2)
            card.style = 'Light Grid Accent 1'
            card.autofit = False
            img_col_width = Inches(2.0)
            details_col_width = Inches(4.5)
            card.columns[0].width = img_col_width
            card.columns[1].width = details_col_width
            img_cell, details_cell = card.rows[0].cells
            img_cell.width = img_col_width
            details_cell.width = details_col_width

            # Left cell: product image.
            para = img_cell.paragraphs[0]
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            try:
                with open(img_path, 'rb') as f:
                    img_bytes = f.read()
                para.add_run().add_picture(io.BytesIO(img_bytes), width=Inches(1.8))
            except Exception:  # noqa: BLE001 — bad image path shouldn't kill the DOCX
                para.add_run('(image unavailable)').italic = True
        else:
            # 1-column full-width card — no image placeholder.
            card = doc.add_table(rows=1, cols=1)
            card.style = 'Light Grid Accent 1'
            card.autofit = False
            card.columns[0].width = Inches(6.5)
            details_cell = card.rows[0].cells[0]
            details_cell.width = Inches(6.5)

        # ── Right cell: product details ──────────────────────────────────
        details_cell.text = ''  # clear default empty paragraph
        p_name = details_cell.paragraphs[0]
        name_run = p_name.add_run(str(p.get('name') or '—'))
        name_run.bold = True
        name_run.font.size = Pt(12)
        name_run.font.color.rgb = _KAU_NAVY

        def _kv(label: str, value: str) -> None:
            if not value or value == '—':
                return
            p = details_cell.add_paragraph()
            label_run = p.add_run(f'{label}: ')
            label_run.bold = True
            p.add_run(value)

        _kv('Category', str(p.get('category') or ''))
        _kv('Product type', str(p.get('product_type') or ''))
        qty = p.get('quantity')
        unit = p.get('unit') or ''
        _kv('Annual quantity', f'{qty} {unit}'.strip() if qty is not None else '')
        price = p.get('price')
        selling_unit = p.get('selling_unit') or ''
        _kv(
            'Selling price',
            f'{_fmt_inr(price)} per {selling_unit}' if price is not None else '',
        )
        desc = (p.get('description') or '').strip()
        if desc:
            details_cell.add_paragraph(desc)

        # Spacer paragraph between cards so consecutive tables don't sit
        # flush against each other.
        doc.add_paragraph()


def _render_ai_chapter(doc, key: str, label: str, text: str) -> None:
    """Add one narrative chapter — heading + AI label + prose paragraphs.

    Matches PDF's per-AI-chapter layout: <h2>{label}</h2> followed by the
    orange "AI-generated narrative · KAU platform" tag and the prose.
    Each chapter gets a bookmark `sec_ai_<key>` so the Table of Contents can
    jump to it via internal hyperlink (Ctrl+click in Word).

    Preserves `[TO BE FILLED: ...]` markers verbatim so editors see them.
    Renders those markers in KAU orange bold so they're visually obvious.
    """
    _add_heading(doc, label, level=1, bookmark=f'sec_ai_{key}')

    # AI-narrative label — matches PDF's `.ai-narrative-label` styling
    # (orange, small, uppercase, letter-spaced).
    label_p = doc.add_paragraph()
    label_run = label_p.add_run('AI-GENERATED NARRATIVE · KAU PLATFORM')
    label_run.bold = True
    label_run.font.size = Pt(7.5)
    label_run.font.color.rgb = _KAU_ORANGE
    label_p.paragraph_format.space_after = Pt(3)
    # LLM output paragraphs are separated by blank lines. Split + emit.
    for para_text in text.split('\n\n'):
        stripped = para_text.strip()
        if not stripped:
            continue
        p = doc.add_paragraph()
        # Inline splitting on [TO BE FILLED: ...] markers to highlight them.
        remaining = stripped
        while '[TO BE FILLED:' in remaining.upper():
            idx = remaining.upper().find('[TO BE FILLED:')
            end = remaining.find(']', idx)
            if end == -1:
                break
            before = remaining[:idx]
            marker = remaining[idx:end + 1]
            if before:
                p.add_run(before)
            run = p.add_run(marker)
            run.bold = True
            run.font.color.rgb = _KAU_ORANGE
            remaining = remaining[end + 1:]
        if remaining:
            p.add_run(remaining)


def _rows_from_pl(r: CalculationResult) -> list[dict]:
    """Flatten ProfitLoss.rows into per-line-item dicts for the multi-year table."""
    if not r.profit_loss or not r.profit_loss.rows:
        return []
    fields = [
        ('Revenue', 'revenue'),
        ('Operating cost', 'operating_cost'),
        ('EBITDA', 'ebitda'),
        ('Depreciation', 'depreciation'),
        ('EBIT', 'ebit'),
        ('Interest — term loan', 'interest'),
        ('Interest on working capital', 'wc_interest'),
        ('PBT', 'pbt'),
        ('Tax', 'tax'),
        ('PAT', 'pat'),
    ]
    out: list[dict] = []
    for label, attr in fields:
        row: dict = {'label': label}
        for pl in r.profit_loss.rows:
            row[f'y{pl.year}'] = getattr(pl, attr, None)
        out.append(row)
    return out


def _rows_from_cashflow(r: CalculationResult) -> list[dict]:
    # WP-08 (UAT): row set + labels now mirror the PDF (report.html §8) 1:1.
    # Previous Word version carried extra "Working capital Δ" + "Opening cash"
    # rows and used "Cash from…" labels; PDF uses the shorter "CF from…"
    # convention. Working capital delta already feeds into cash_from_operations
    # upstream, so showing it as its own line double-counted it visually.
    if not r.cash_flow or not r.cash_flow.rows:
        return []
    fields = [
        ('PAT', 'pat'),
        ('Depreciation add-back', 'depreciation_addback'),
        ('CF from Operations', 'cash_from_operations'),
        ('Capex', 'capex'),
        ('CF from Investing', 'cash_from_investing'),
        ('MoF inflow', 'mof_inflow'),
        ('Loan repayment', 'loan_principal_repayment'),
        ('CF from Financing', 'cash_from_financing'),
        ('Net cash flow', 'net_cash_flow'),
        ('Closing cash', 'closing_cash'),
    ]
    out: list[dict] = []
    for label, attr in fields:
        row: dict = {'label': label}
        for cf in r.cash_flow.rows:
            row[f'y{cf.year}'] = getattr(cf, attr, None)
        out.append(row)
    return out


def _rows_from_balance_sheet(r: CalculationResult) -> list[dict]:
    # WP-02 (UAT): added term loan + liabilities + totals + invariant row so
    # the Word balance sheet actually balances like the PDF does. Previous
    # version stopped at Retained earnings and omitted the entire liabilities
    # side, so the sheet appeared broken to any reviewer.
    if not r.balance_sheet or not getattr(r.balance_sheet, 'rows', None):
        return []
    fields = [
        ('Land', 'land'),
        ('CWIP', 'cwip'),
        ('Gross fixed assets', 'gross_fixed_assets'),
        ('Accumulated depreciation', 'accumulated_depreciation'),
        ('Net fixed assets', 'net_fixed_assets'),
        ('Working capital', 'working_capital'),
        ('Cash & bank', 'cash_and_bank'),
        ('Total assets', 'total_assets'),
        ('Promoter equity', 'promoter_equity'),
        ('Capital reserve', 'capital_reserve'),
        ('Retained earnings', 'retained_earnings'),
        ('Total equity', 'total_equity'),
        ('Term loan outstanding', 'term_loan_outstanding'),
        ('WC loan outstanding', 'wc_loan_outstanding'),
        ('WC gap — short-term borrowings (to be arranged)', 'wc_shortfall_borrowings'),
        ('Other liabilities', 'other_liabilities'),
        ('Total liabilities', 'total_liabilities'),
        ('Total equity & liabilities', 'total_equity_and_liabilities'),
    ]
    out: list[dict] = []
    for label, attr in fields:
        row: dict = {'label': label}
        for bs in r.balance_sheet.rows:
            row[f'y{bs.year}'] = getattr(bs, attr, None)
        out.append(row)
    return out


def _rows_from_interest(r: CalculationResult) -> list[dict]:
    """WP-09 (UAT): rows are now YEARS (not line items). Columns become
    Opening / Interest / Principal / Closing — matching the PDF table at
    §6. Previous shape had those four as rows + years spread across
    columns, which transposed the table and made it unreadable."""
    sched = r.interest_schedule
    if not sched or not sched.rows:
        return []
    out: list[dict] = []
    for row in sched.rows:
        out.append({
            'label':    f'Y{row.year}',
            'opening':  getattr(row, 'opening_balance', None),
            'interest': getattr(row, 'interest', None),
            'principal': getattr(row, 'principal', None),
            'closing':  getattr(row, 'closing_balance', None),
        })
    return out


def _add_loan_repayment_table(doc, rows: list[dict]) -> None:
    """WP-09 (UAT): render loan repayment with four fixed columns —
    Year | Opening | Interest | Principal | Closing. Years run down the
    rows, matching the PDF."""
    if not rows:
        return
    headers = ['Year', 'Opening balance', 'Interest', 'Principal', 'Closing balance']
    table = doc.add_table(rows=len(rows) + 1, cols=len(headers))
    table.style = 'Light Grid Accent 1'
    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = h
        for para in cell.paragraphs:
            for run in para.runs:
                run.bold = True
    _tag_header_row_repeat(table)
    _style_header_row_navy(table)
    for i, row in enumerate(rows, start=1):
        cells = table.rows[i].cells
        cells[0].text = str(row.get('label') or '—')
        for j, k in enumerate(('opening', 'interest', 'principal', 'closing'), start=1):
            cells[j].text = _fmt_inr_table(row.get(k))


_WC_BASIS_DISPLAY_DOCX = {
    'seasonal_peak':   'Seasonal peak amount (KAU §2.4 C3 — overrides operating-cycle)',
    'operating_cycle': 'Operating-cycle method (KAU §2.4)',
    'operating_cycle_higher_than_peak': 'Operating-cycle method (entered seasonal peak was lower — peak is a floor, not a cap)',
    'margin_only':     'Fallback: WC margin on cost of project',
    'none':            'Not computed — days/costs not entered',
}


def _render_working_capital_statement(doc, r: CalculationResult) -> None:
    """BUG-06 (KAU §2.4) — Working Capital Statement in the Word export.

    Mirrors the PDF §6B layout: basis + days + annual opex + requirement
    + seasonal override + funding reconciliation + optional shortfall row.
    Skips when the project has no WC statement (should always be present
    once compute() runs, but defensive).
    """
    wc = getattr(r, 'working_capital_statement', None)
    if wc is None:
        return
    _add_heading(doc, '6B. Working Capital Statement (KAU §2.4 operating-cycle method)',
                 level=1, bookmark='sec_6b')
    basis_label = _WC_BASIS_DISPLAY_DOCX.get(wc.basis_used, wc.basis_used)
    _add_para(
        doc,
        f'Basis: {basis_label}  ·  Operating cycle: {wc.operating_cycle_days} days '
        f'({wc.inventory_days} inventory + {wc.receivable_days} receivable − '
        f'{wc.payable_days} payable)',
        italic=True, size=9,
    )

    rows: list[tuple[str, str, bool]] = [
        ('Annual opex (WC basis)',
         _fmt_inr_table(wc.annual_wc_opex), False),
        ('WC requirement — operating-cycle method',
         _fmt_inr_table(wc.wc_requirement_operating_cycle), False),
    ]
    if wc.is_seasonal and wc.peak_amount:
        rows.append((
            'Seasonal override — peak-period amount (KAU §2.4 C3)',
            _fmt_inr_table(wc.peak_amount), False,
        ))
    rows.append((
        'WC requirement used in projections',
        _fmt_inr_table(wc.wc_requirement_used), True,
    ))
    rows.append((
        'Funded by: WC loan',
        _fmt_inr_table(wc.mof_working_capital_loan), False,
    ))
    rows.append((
        'Funded by: WC margin on cost of project',
        _fmt_inr_table(wc.margin_for_working_capital), False,
    ))
    rows.append((
        'Total funded WC',
        _fmt_inr_table(wc.funded_wc_total), True,
    ))
    if wc.funding_gap > 0:
        rows.append((
            f'SHORTFALL vs requirement ({wc.funding_gap_pct_of_requirement}%)',
            _fmt_inr_table(wc.funding_gap), True,
        ))
    if getattr(wc, 'wc_interest_annual', None):
        rows.append((
            f'Interest on WC borrowings @ {wc.wc_interest_rate_pct}% p.a. (charged in P&L)',
            f'{_fmt_inr_table(wc.wc_interest_annual)} / year', False,
        ))

    table = doc.add_table(rows=len(rows), cols=2)
    table.style = 'Light Grid Accent 1'
    for i, (label, value, bold) in enumerate(rows):
        cells = table.rows[i].cells
        cells[0].text = label
        cells[1].text = value
        if bold:
            for cell in cells:
                for para in cell.paragraphs:
                    for run in para.runs:
                        run.bold = True
    _tag_header_row_repeat(table)

    if wc.peak_notes:
        _add_para(
            doc,
            f'Peak-period notes: {wc.peak_notes}',
            italic=True, size=9,
        )
    _add_para(
        doc,
        'The DPR uses the operating-cycle method per KAU §2.4 (Pre-UAT reply, '
        'Approved as-is). For seasonal enterprises the FPO may enter a '
        'peak-period amount, which overrides the operating-cycle estimate for '
        'projection purposes.',
        italic=True, size=8,
    )


def _render_ratios(doc, r: CalculationResult) -> None:
    """Financial Appraisal (§10) — explicit label + formatter per ratio.

    WP-03 (UAT): the previous version read raw attr names via `.title()`
    which produced "Dscr Avg", "Irr (%)", "Npv" (and dropped payback /
    break-even entirely because the attr names didn't match). Now matches
    the PDF (report.html §10) 1:1: NPV, IRR, Payback, Break-even year,
    Min DSCR, Avg DSCR + an operating break-even sub-table under it.
    """
    ratios = r.ratios
    if not ratios:
        return
    _add_heading(doc, '10. Financial Appraisal', level=1, bookmark='sec_10')

    npv = getattr(ratios, 'npv', None)
    irr = getattr(ratios, 'irr_pct', None)
    payback = getattr(ratios, 'payback_period_years', None) or getattr(ratios, 'payback_years', None)
    break_even_year = getattr(ratios, 'break_even_year', None)
    dscr_min = getattr(ratios, 'dscr_min', None) or getattr(ratios, 'dscr_minimum', None)
    dscr_avg = getattr(ratios, 'dscr_avg', None)
    discount_rate = getattr(ratios, 'discount_rate_pct', None)

    def _fmt_years(v):
        if v is None:
            return '—'
        s = str(v).rstrip('0').rstrip('.')
        return f'{s} years'

    def _fmt_dscr(v):
        if v is None:
            return '—'
        return f'{v}x'

    rows = [
        ('NPV' + (f' (@ {_fmt_pct(discount_rate)})' if discount_rate is not None else ''),
            _fmt_inr_table(npv)),
        ('IRR', _fmt_pct(irr)),
        ('Payback period', _fmt_years(payback)),
        ('Break-even year', f'Y{break_even_year}' if break_even_year else '—'),
        ('Minimum DSCR', _fmt_dscr(dscr_min)),
        ('Average DSCR', _fmt_dscr(dscr_avg)),
    ]
    _add_two_col_table(doc, rows)

    # Operating break-even sub-table (matches report.html §10 operating-BE panel)
    be_sales = getattr(ratios, 'break_even_sales_inr', None)
    be_util = getattr(ratios, 'break_even_capacity_utilisation_pct', None)
    contribution = getattr(ratios, 'break_even_contribution_margin_pct', None)
    if any(v is not None for v in (be_sales, be_util, contribution)):
        _add_para(doc, 'Operating break-even (Y1 basis)', bold=True, size=11)
        _add_two_col_table(doc, [
            ('Break-even sales', _fmt_inr_table(be_sales)),
            ('Break-even capacity utilisation', _fmt_pct(be_util)),
            ('Contribution margin', _fmt_pct(contribution)),
        ])


def _render_depreciation_schedule(doc, r: CalculationResult) -> None:
    """Per-asset-class × per-year depreciation table — matches PDF §5.

    Renders one row per depreciable asset class with initial cost, rate %,
    per-year depreciation charge, and closing net block. Totals row at the
    bottom.
    """
    dep = r.depreciation
    if not dep or not dep.classes:
        return
    _add_heading(doc, '5. Depreciation Schedule (SLM)', level=1, bookmark='sec_5')
    _add_para(
        doc,
        'Straight-Line Method (SLM) at the rates configured for the KAU DPR '
        'platform. Indicative for project appraisal — may differ from '
        'statutory / Income Tax depreciation rates.',
        italic=True,
    )
    years = list(range(1, dep.projection_years + 1))
    header = ['Asset class', 'Rate %', 'Initial cost'] + [f'Y{y}' for y in years] + ['Net Y' + str(dep.projection_years)]
    table = doc.add_table(rows=len(dep.classes) + 2, cols=len(header))
    table.style = 'Light Grid Accent 1'
    for i, h in enumerate(header):
        cell = table.rows[0].cells[i]
        cell.text = h
        for para in cell.paragraphs:
            for run in para.runs:
                run.bold = True
    _tag_header_row_repeat(table)
    _style_header_row_navy(table)
    for i, cls in enumerate(dep.classes, start=1):
        cells = table.rows[i].cells
        cells[0].text = cls.label
        cells[1].text = _fmt_num(cls.rate_pct, '%')
        cells[2].text = _fmt_inr_table(cls.initial_cost)
        for j, row in enumerate(cls.rows):
            cells[3 + j].text = _fmt_inr_table(row.depreciation)
        # Net block at end of horizon = closing_gross - closing_accum_dep from last row.
        net_last = (cls.rows[-1].net_block if cls.rows else None)
        cells[-1].text = _fmt_inr_table(net_last) if net_last is not None else '—'
    # Totals row.
    total_cells = table.rows[-1].cells
    total_cells[0].text = 'Total'
    for para in total_cells[0].paragraphs:
        for run in para.runs:
            run.bold = True
    total_cells[2].text = _fmt_inr_table(dep.total_initial_cost)
    for j, y in enumerate(years):
        total_cells[3 + j].text = _fmt_inr_table(dep.total_depreciation_by_year.get(y, Decimal('0')))
    if len(header) >= 8:
        _set_body_font_size(table, 8)
        _set_header_font_size(table, 8)
        _fix_table_width_to_text_frame(table, landscape=True)


def _render_capital_schedule(doc, r: CalculationResult) -> None:
    """Per-month capital + MoF flow during the implementation period —
    matches PDF §4. Only rendered when tranches are configured; otherwise
    silently omitted so an early-stage DPR doesn't ship an empty table.
    """
    sched = getattr(r, 'capital_schedule', None)
    if not sched or not getattr(sched, 'rows', None):
        return
    _add_heading(doc, '4. Capital Investment Schedule (Implementation Period)', level=1, bookmark='sec_4')
    _add_para(
        doc,
        getattr(sched, 'distribution_note', '') or (
            'Per-month capex + means-of-finance plan for the implementation '
            'period. Unfunded column shows the running cost−MoF gap.'
        ),
        italic=True,
    )
    header = ['Month', 'Cost incurred', 'MoF received', 'Cum cost', 'Cum MoF', 'Unfunded']
    table = doc.add_table(rows=len(sched.rows) + 1, cols=len(header))
    table.style = 'Light Grid Accent 1'
    for i, h in enumerate(header):
        cell = table.rows[0].cells[i]
        cell.text = h
        for para in cell.paragraphs:
            for run in para.runs:
                run.bold = True
    _tag_header_row_repeat(table)
    _style_header_row_navy(table)
    for i, row in enumerate(sched.rows, start=1):
        cells = table.rows[i].cells
        cells[0].text = str(getattr(row, 'month', '—'))
        cells[1].text = _fmt_inr_table(getattr(row, 'cost_incurred', None))
        cells[2].text = _fmt_inr_table(getattr(row, 'mof_received', None))
        cells[3].text = _fmt_inr_table(getattr(row, 'cumulative_cost', None))
        cells[4].text = _fmt_inr_table(getattr(row, 'cumulative_mof', None))
        cells[5].text = _fmt_inr_table(getattr(row, 'unfunded', None))
    _fix_table_width_to_text_frame(table)


def _render_risk_assessment(doc, r: CalculationResult) -> None:
    """Structured risk-matrix rendering matching PDF §11.

    Renders:
      * Overall project risk badge (Low / Moderate / High) + summary
      * Per-category breakdown table (Category / Risks entered / Scored /
        Low / Moderate / High / Category class)
      * Optional auto-pulled risks from other sections (Raw Material / Market
        / Technology / ESS) as a secondary table

    Skipped silently when the calc engine didn't produce a RiskAssessment.
    """
    ra = getattr(r, 'risk_assessment', None)
    if not ra:
        return
    _add_heading(doc, '11. Risk Assessment', level=1, bookmark='sec_11')

    # WP-05 (UAT): use the shared label map so "no_risks" / "not_assessed"
    # render as "No risks entered" / "Not assessed" instead of the
    # auto-capitalised raw code ("No_risks").
    overall_label, overall_colour = _risk_display(ra.overall_class)

    p_summary = doc.add_paragraph()
    p_summary.add_run('Overall project risk: ').bold = True
    badge_run = p_summary.add_run(overall_label)
    badge_run.bold = True
    badge_run.font.color.rgb = overall_colour
    p_summary.add_run(
        f'   ·   {ra.total_risks_scored} of {ra.total_risks_added} risks scored via matrix'
    )
    # WP-05 (UAT): the matrix_note field carries internal admin plumbing
    # ("25 matrix cells configured. Admin edits at /api/admin/dpr/risk-matrix/.")
    # and never appeared in the PDF. Keep it out of the bank-facing Word
    # export too — only surface strings that don't advertise admin paths.
    note = getattr(ra, 'matrix_note', '') or ''
    if note and '/api/admin/' not in note and 'matrix cells configured' not in note.lower():
        _add_para(doc, note, italic=True, size=9)

    if ra.categories:
        headers = ['Category', 'Risks entered', 'Scored', 'Low',
                   'Moderate', 'High', 'Category class']
        table = doc.add_table(rows=len(ra.categories) + 1, cols=len(headers))
        table.style = 'Light Grid Accent 1'
        for i, h in enumerate(headers):
            cell = table.rows[0].cells[i]
            cell.text = h
            for para in cell.paragraphs:
                for run in para.runs:
                    run.bold = True
        _style_header_row_navy(table)
        for i, cat in enumerate(ra.categories, start=1):
            row = table.rows[i].cells
            row[0].text = cat.category_label
            row[1].text = str(cat.risk_count)
            row[2].text = str(cat.scored_count)
            row[3].text = str(cat.class_counts.get('low', 0))
            row[4].text = str(cat.class_counts.get('moderate', 0))
            row[5].text = str(cat.class_counts.get('high', 0))
            # WP-05 (UAT): category class now flows through the shared label
            # map so "no_risks" / "not_assessed" surface as reader-friendly
            # text instead of "No_risks" / "Not_assessed".
            cat_label, cat_colour = _risk_display(cat.category_class)
            row[6].text = cat_label
            for para in row[6].paragraphs:
                for run in para.runs:
                    run.bold = True
                    run.font.color.rgb = cat_colour

    _add_para(
        doc,
        'Classification rule: any category High → overall High; else any '
        'Moderate → overall Moderate; else Low.',
        italic=True, size=8,
    )

    # ── Auto-pulled risks from other sections ─────────────────────────────
    auto = getattr(ra, 'auto_pulled', None) or []
    if auto:
        _add_para(
            doc,
            'Additional Risks — Aggregated from Other Sections',
            bold=True, size=12,
        )
        _add_para(
            doc,
            'The following risks were captured in the Raw Material, Market, '
            'Technology, and ESS (Climate) sections. They are shown here for '
            'completeness of the risk register.',
            italic=True, size=9,
        )
        headers2 = ['Source section', 'Category', 'Risk', 'Mitigation strategy']
        table2 = doc.add_table(rows=len(auto) + 1, cols=len(headers2))
        table2.style = 'Light Grid Accent 1'
        for i, h in enumerate(headers2):
            cell = table2.rows[0].cells[i]
            cell.text = h
            for para in cell.paragraphs:
                for run in para.runs:
                    run.bold = True
        for i, ap in enumerate(auto, start=1):
            row = table2.rows[i].cells
            row[0].text = ap.source_label
            row[1].text = ap.category_label
            row[2].text = ap.risk_label
            row[3].text = ap.mitigation_strategy or '—'


def _render_toc(doc, project, ai: dict, has_products: bool,
                has_tech_flows: bool) -> None:
    """Clickable Table of Contents matching PDF's TOC recipe.

    Each entry is an internal Word hyperlink pointing to a bookmark on the
    corresponding heading. Reader clicks (or Ctrl+clicks in Word) the entry
    and Word scrolls straight to that section — same UX as PDF anchor links.

    Page numbers aren't auto-populated (that requires a Word TOC field which
    only fills on manual F9 refresh); the click-to-jump behaviour is the
    important part.
    """
    _add_heading(doc, 'Table of Contents', level=1)

    # (label, bookmark_anchor) tuples.
    entries: list[tuple[str, str]] = []
    if ai.get('executive_summary'):
        entries.append(('Executive Summary', 'sec_ai_executive_summary'))
    if ai.get('project_background'):
        entries.append(('Project Background', 'sec_ai_project_background'))
    if ai.get('promoter_profile'):
        entries.append(('Promoter Profile', 'sec_ai_promoter_profile'))

    entries += [
        ('1. Project at a Glance', 'sec_1'),
        ('2. Fixed Capital Investment', 'sec_2'),
        ('3. Means of Finance', 'sec_3'),
        ('4. Capital Investment Schedule', 'sec_4'),
        ('5. Depreciation Schedule (SLM)', 'sec_5'),
        ('6. Loan Repayment Schedule', 'sec_6'),
        ('6B. Working Capital Statement (KAU §2.4)', 'sec_6b'),
        ('7. Projected Profit & Loss', 'sec_7'),
        ('8. Projected Cash Flow', 'sec_8'),
        ('9. Projected Balance Sheet', 'sec_9'),
        ('10. Financial Appraisal', 'sec_10'),
        ('11. Risk Assessment', 'sec_11'),
    ]
    if has_products:
        entries.append(('Proposed Products & Services', 'sec_products'))
    if has_tech_flows:
        entries.append(('12. Manufacturing Process', 'sec_12'))

    # WP-01 (UAT): Risk Analysis AI chapter was missing from both the TOC
    # map and the body loop. Added here + in the body renderer below.
    trailing_map = {
        'market_analysis': ('Market Analysis (AI)', 'sec_ai_market_analysis'),
        'technical_feasibility': ('Technical Feasibility (AI)', 'sec_ai_technical_feasibility'),
        'financial_analysis': ('Financial Analysis (AI)', 'sec_ai_financial_analysis'),
        'implementation_plan': ('Implementation Plan (AI)', 'sec_ai_implementation_plan'),
        'swot': ('SWOT Analysis (AI)', 'sec_ai_swot'),
        'risk_analysis': ('Risk Analysis (AI)', 'sec_ai_risk_analysis'),
        'environmental_impact': ('Environmental Impact (AI)', 'sec_ai_environmental_impact'),
        'conclusion': ('Conclusion', 'sec_ai_conclusion'),
    }
    for key, entry in trailing_map.items():
        if ai.get(key):
            entries.append(entry)

    entries.append(('Key Assumptions Used', 'sec_assumptions'))
    entries.append(('Limitations & Guidelines for Entrepreneurs', 'sec_guidelines'))

    # WP-07 (UAT): previous version applied the "List Number" style which
    # prepended an auto-counter to each entry; the entry text already carried
    # the manual section number ("1. Project at a Glance", "10. Financial
    # Appraisal", …) so Word rendered "4. 1. Project at a Glance" / "13. 10.
    # Financial Appraisal". Dropped the style so the manual prefixes stand
    # alone and read as a clean TOC.
    for label, anchor in entries:
        p = doc.add_paragraph()
        _add_toc_hyperlink(p, anchor, label)
        p.paragraph_format.space_after = Pt(2)

    doc.add_page_break()


def _render_limitations(doc) -> None:
    """Static "Limitations & Guidelines for Entrepreneurs" chapter —
    matches the PDF's closing section (report.html §sec-guidelines).
    Content mirrors that template verbatim.
    """
    _add_heading(doc, 'Limitations & Guidelines for Entrepreneurs', level=1, bookmark='sec_guidelines')

    _add_para(doc, 'Limitations of this model DPR', bold=True, size=12)
    limitations = [
        'Financial projections in this DPR are indicative. Actual costs may vary '
        'based on prevailing market rates, project location, technology choice '
        'and vendor selection.',
        'Revenue, capacity utilisation and price assumptions have been provided '
        'by the promoter; assumptions must be revisited annually and adjusted '
        'for market conditions.',
        'Interest rate, moratorium and repayment tenure follow current standard '
        'lending terms; the sanctioned terms from the lending bank supersede '
        'these figures.',
        'Subsidy amounts and eligibility conditions are subject to the current '
        'scheme guidelines issued by the concerned Central / State Government agency.',
        'The break-even analysis assumes steady-state operations. Actual break-even '
        'may shift due to trial runs, working capital availability, or seasonal '
        'demand variations.',
    ]
    for item in limitations:
        p = doc.add_paragraph(item, style='List Bullet')
        p.paragraph_format.space_after = Pt(2)

    doc.add_paragraph()  # spacer
    _add_para(doc, 'Guidelines for entrepreneurs', bold=True, size=12)
    guidelines = [
        'Conduct a detailed market survey in the target catchment before commissioning '
        'the plant, and validate the demand-price assumptions used in this report.',
        'Obtain firm quotations from at least three machinery suppliers and finalise '
        'vendor selection based on total cost of ownership (including installation, '
        'commissioning, spares and after-sales support), not landed cost alone.',
        'Complete all statutory registrations (Udyam / MSME, FSSAI, GSTIN, PCB, '
        'Trade Licence, factory registration where applicable) before commencing operations.',
        'Maintain separate books-of-account for the project; monthly MIS review of '
        'production, sales, receivables and inventory is strongly recommended.',
        'Insure the plant, machinery, stocks and work-in-progress; opt for a group '
        'insurance scheme for workers.',
        'Adhere to KAU-recommended good manufacturing practices and quality standards; '
        'product traceability records help build brand credibility and unlock premium markets.',
        'Reserve at least 3 months of working capital as a contingency buffer, especially '
        'during the first year of operations.',
    ]
    for item in guidelines:
        p = doc.add_paragraph(item, style='List Bullet')
        p.paragraph_format.space_after = Pt(2)

    doc.add_paragraph()
    footer = doc.add_paragraph()
    r = footer.add_run(
        'Prepared using the KAU-FPO Platform DPR module. All financial '
        'assumptions and defaults are controlled by the KAU Central Administrator.'
    )
    r.italic = True
    r.font.size = Pt(9)


def _render_technologies(doc, project) -> None:
    """Text-only rendering of each technology's process flow."""
    techs = _technologies_with_flow(project)
    if not techs:
        return
    _add_heading(doc, '12. Manufacturing Process', level=1, bookmark='sec_12')
    for tech in techs:
        _add_para(doc, tech['name'], bold=True)
        if tech.get('description'):
            doc.add_paragraph(tech['description'])
        for i, step in enumerate(tech['steps'], start=1):
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.25)
            p.add_run(f'{i}. ').bold = True
            p.add_run(step)


def _render_key_assumptions(doc, project=None) -> None:
    # DPR-10 (UAT): pass project through so project-entered rates
    # (loan interest, inflation) are labelled as such instead of being
    # mis-labelled as 'KAU DPR platform default'.
    rows = _key_assumptions_rows(project)
    if not rows:
        return
    _add_heading(doc, 'Key Assumptions Used', level=1, bookmark='sec_assumptions')
    table = doc.add_table(rows=len(rows) + 1, cols=3)
    table.style = 'Light Grid Accent 1'
    hdr = table.rows[0].cells
    for i, label in enumerate(['Parameter', 'Value', 'Source']):
        hdr[i].text = label
        for para in hdr[i].paragraphs:
            for run in para.runs:
                run.bold = True
    _style_header_row_navy(table)
    for i, row in enumerate(rows, start=1):
        cells = table.rows[i].cells
        cells[0].text = str(row.get('label') or '—')
        # WP-04 (UAT): the dict shape from `_key_assumptions_rows()` is
        # `{label, value_pct, source}` — the old `.get('value')` always
        # missed and emitted "—" for every row. Prefer the explicit
        # value_pct key, keep a `.get('value')` fallback for any future
        # row shape that uses the shorter name.
        cells[1].text = str(row.get('value_pct') or row.get('value') or '—')
        cells[2].text = str(row.get('source') or '—')
    _tag_header_row_repeat(table)


def _configure_page_setup(doc, fpo_name: str, project_title: str,
                          version_label: str) -> None:
    """WP-10 (UAT): switch Word page setup from the python-docx default
    (US Letter, 1" margins, no header/footer) to the PDF's convention —
    A4 portrait, 2 cm margins, running header with FPO + project, running
    footer with version + "Page X of Y".
    """
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    section = doc.sections[0]
    section.page_width = Mm(210)
    section.page_height = Mm(297)
    section.top_margin = Cm(2)
    section.bottom_margin = Cm(2)
    section.left_margin = Cm(2)
    section.right_margin = Cm(2)

    # Running header — FPO + project title on the left, version on the right.
    # NEW-5 round-5 (UAT): replaced the fixed RIGHT tab stop at 17 cm with
    # a section-aware `w:ptab relativeTo="margin" alignment="right"`. A fixed
    # tab works for portrait (right margin at 17 cm) but on the landscape
    # section (right margin at 25.7 cm) it leaves "DPR vN" mid-page. A ptab
    # auto-snaps to the current section's right margin, so one header
    # definition suits portrait + landscape + portrait without duplication.
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    header_para = section.header.paragraphs[0]
    header_para.alignment = WD_ALIGN_PARAGRAPH.LEFT
    header_run = header_para.add_run(f'{fpo_name} — {project_title}')
    header_run.font.size = Pt(9)
    header_run.font.color.rgb = _KAU_NAVY
    header_run.bold = True
    # Section-aware right-align tab via w:ptab inside its own run.
    ptab_run = header_para.add_run()
    ptab_run.font.size = Pt(9)
    ptab = OxmlElement('w:ptab')
    ptab.set(qn('w:relativeTo'), 'margin')
    ptab.set(qn('w:alignment'), 'right')
    ptab.set(qn('w:leader'), 'none')
    ptab_run._r.append(ptab)
    version_run = header_para.add_run(f'DPR {version_label}')
    version_run.font.size = Pt(9)
    version_run.font.color.rgb = _KAU_NAVY

    # Running footer — centred version + "Page X of Y" using fields that
    # Word fills on open / F9 refresh.
    footer_para = section.footer.paragraphs[0]
    footer_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    fpref = footer_para.add_run(f'DPR {version_label}   ·   Page ')
    fpref.font.size = Pt(9)
    fpref.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
    # PAGE field
    fld_begin = OxmlElement('w:fldChar'); fld_begin.set(qn('w:fldCharType'), 'begin')
    instr = OxmlElement('w:instrText'); instr.text = ' PAGE '
    fld_end = OxmlElement('w:fldChar'); fld_end.set(qn('w:fldCharType'), 'end')
    page_run = footer_para.add_run()
    page_run._r.append(fld_begin); page_run._r.append(instr); page_run._r.append(fld_end)
    page_run.font.size = Pt(9)
    page_run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
    of_run = footer_para.add_run(' of ')
    of_run.font.size = Pt(9)
    of_run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
    # NUMPAGES field
    nb = OxmlElement('w:fldChar'); nb.set(qn('w:fldCharType'), 'begin')
    ni = OxmlElement('w:instrText'); ni.text = ' NUMPAGES '
    ne = OxmlElement('w:fldChar'); ne.set(qn('w:fldCharType'), 'end')
    num_run = footer_para.add_run()
    num_run._r.append(nb); num_run._r.append(ni); num_run._r.append(ne)
    num_run.font.size = Pt(9)
    num_run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)


def _resolve_version_label(project, version_number: Optional[int]) -> str:
    """WP-06 (UAT): the cover + header/footer used to read "Preview" when
    `version_number` wasn't passed in. Now falls back to the latest non-
    archived DPRDocument.version_number so a reviewer sees `v35` instead of
    `Preview` when the Manage DPRs page has already produced versioned
    PDFs."""
    if version_number is not None:
        return f'v{version_number}'
    try:
        from apps.database.models import DPRDocument
        latest = (
            DPRDocument.objects
            .filter(project=project, is_archived=False)
            .order_by('-version_number')
            .first()
        )
        if latest and latest.version_number:
            return f'v{latest.version_number}'
    except Exception:  # noqa: BLE001 — model lookup is best-effort
        pass
    return 'Preview'


def render_docx_for_project(
    project,
    version_number: Optional[int] = None,
    mode: str = 'preview',
) -> bytes:
    """Full pipeline: compute → build DOCX → return bytes.

    `mode` is accepted for API parity with the PDF renderer but currently
    has no visible effect on the DOCX output — editors get the same content
    either way. The flag is reserved so future runs can add preview-only
    provenance markers if KAU asks for them.
    """
    if mode not in ('preview', 'final'):
        raise ValueError(f"mode must be 'preview' or 'final', got {mode!r}")

    result: CalculationResult = compute(project)

    doc = Document()

    # Global default font — Calibri 11 pt matches Word's OOTB "Normal" style
    # so a reviewer can paste-into or copy-out of the document without a
    # visible style break.
    normal = doc.styles['Normal']
    normal.font.name = 'Calibri'
    normal.font.size = Pt(11)

    version_label = _resolve_version_label(project, version_number)
    fpo_name = project.fpo.name if project.fpo_id else '—'
    _configure_page_setup(doc, fpo_name, project.title or '(untitled)',
                          version_label)
    generated_at = datetime.now().strftime('%d %b %Y · %I:%M %p')
    _render_cover(doc, project, version_label, generated_at,
                  projection_years=result.projection_years)

    # Table of Contents — matches PDF's TOC recipe. Rendered right after the
    # cover so a reader can jump directly to the section they need.
    ai_map = _ai_chapters_for_pdf(project)
    products_list, _hero_temp = _products_for_pdf(project)
    tech_flows = _technologies_with_flow(project)
    _render_toc(doc, project, ai_map,
                has_products=bool(products_list),
                has_tech_flows=bool(tech_flows))

    ai = _ai_chapters_for_pdf(project)

    # ── Section order — 1:1 with the PDF template (report.html) ─────────
    #
    # PDF order:
    #   Executive Summary (AI)
    #   Project Background (AI)
    #   Promoter Profile (AI)
    #   §1 Project at a Glance
    #   §2 Fixed Capital Investment (cost table + pie chart)
    #   §3 Means of Finance
    #   §4 Capital Investment Schedule
    #   §5 Depreciation Schedule (SLM)
    #   §6 Loan Repayment Schedule (+ bar chart)
    #   §7 Projected Profit & Loss (+ bar chart)
    #   §8 Projected Cash Flow
    #   §9 Projected Balance Sheet
    #   §10 Financial Appraisal (ratios)
    #   §11 Risk Assessment
    #   Proposed Products & Services (image cards)
    #   §12 Manufacturing Process
    #   Market Analysis (AI)
    #   Technical Feasibility (AI)
    #   Financial Analysis (AI)
    #   Implementation Plan (AI)
    #   SWOT Analysis (AI)
    #   Environmental Impact (AI)
    #   Conclusion (AI)
    #   Key Assumptions Used
    #   Limitations & Guidelines for Entrepreneurs

    # 1. AI narrative chapters that lead the report — Executive Summary,
    # Project Background, Promoter Profile.
    for key, label in [
        ('executive_summary', 'Executive Summary'),
        ('project_background', 'Project Background'),
        ('promoter_profile', 'Promoter Profile'),
    ]:
        text = ai.get(key)
        if text:
            _render_ai_chapter(doc, key, label, text)

    # 2. Numbered data chapters §1-§10.
    _render_project_at_a_glance(doc, project, result)
    _render_fixed_capital_investment(doc, result)
    _render_means_of_finance(doc, result)
    _render_capital_schedule(doc, result)

    # WP-10 round-4 (UAT): wrap §5–§9 (the four 12-14 column wide tables)
    # in a landscape A4 section. Portrait couldn't give the year columns
    # enough width even with 8 pt body font; landscape widens the text
    # frame from 17 cm to 25.7 cm — year columns now get ~46 pt usable
    # which is comfortable for 8-digit INR values like "1,19,02,128".
    # Section break closes before §10 to put ratios + risk + products +
    # trailing AI chapters back on portrait pages.
    _start_landscape_section(doc)
    _render_depreciation_schedule(doc, result)

    # §6 Loan Repayment Schedule (chart + transposed table).
    # WP-09 (UAT): rows = years, columns = Opening / Interest / Principal /
    # Closing — matches the PDF's §6 shape.
    if result.interest_schedule and getattr(result.interest_schedule, 'rows', None):
        _add_heading(doc, '6. Loan Repayment Schedule (₹)', level=1, bookmark='sec_6')
        sched = result.interest_schedule
        loan_bits = []
        if getattr(sched, 'loan_amount', None) is not None:
            loan_bits.append(f'Loan: ₹{_fmt_inr_table(sched.loan_amount)}')
        if getattr(sched, 'interest_rate_pct', None) is not None:
            loan_bits.append(f'@ {_fmt_pct(sched.interest_rate_pct)}')
        if getattr(sched, 'tenure_years', None):
            loan_bits.append(f'Tenure: {sched.tenure_years} years')
        if getattr(sched, 'moratorium_months', None) is not None:
            loan_bits.append(f'Moratorium: {sched.moratorium_months} months')
        if loan_bits:
            _add_para(doc, '   ·   '.join(loan_bits), italic=True, size=9)
        _embed_data_url_chart(doc, repayment_schedule_bar(sched.rows))
        _add_loan_repayment_table(doc, _rows_from_interest(result))
    # §6B Working Capital Statement (KAU §2.4, BUG-06)
    _render_working_capital_statement(doc, result)
    # §7 P&L (+ chart)
    if result.profit_loss:
        _add_heading(doc, '7. Projected Profit & Loss', level=1, bookmark='sec_7')
        _embed_data_url_chart(doc, pnl_trend_bar(result.profit_loss.rows))
        _add_multi_year_table(doc, '', _rows_from_pl(result), heading_level=2)
    # §8 Cash Flow
    if result.cash_flow and getattr(result.cash_flow, 'rows', None):
        _add_heading(doc, '8. Projected Cash Flow', level=1, bookmark='sec_8')
        _add_multi_year_table(doc, '', _rows_from_cashflow(result), heading_level=2)
    # §9 Balance Sheet
    if result.balance_sheet and getattr(result.balance_sheet, 'rows', None):
        _add_heading(doc, '9. Projected Balance Sheet', level=1, bookmark='sec_9')
        _add_multi_year_table(doc, '', _rows_from_balance_sheet(result), heading_level=2)
    # WP-10 round-4: close the landscape block so §10+ reverts to portrait.
    _end_landscape_section(doc)
    # §10 Financial Appraisal (ratios)
    _render_ratios(doc, result)
    # §11 Risk Assessment
    _render_risk_assessment(doc, result)

    # 3. Products & Services — cards with images.
    _render_products(doc, project)
    # §12 Manufacturing Process
    _render_technologies(doc, project)

    # 4. Trailing AI narrative chapters — Market, Tech, Finance, Impl,
    #    SWOT, Env, Conclusion (Project Background + Promoter Profile
    #    already rendered above).
    # WP-01 (UAT): Risk Analysis AI chapter is now part of the trailing
    # stack. Order mirrors the PDF (after SWOT, before Environmental Impact).
    trailing_ai = [
        ('market_analysis', 'Market Analysis'),
        ('technical_feasibility', 'Technical Feasibility'),
        ('financial_analysis', 'Financial Analysis'),
        ('implementation_plan', 'Implementation Plan'),
        ('swot', 'SWOT Analysis'),
        ('risk_analysis', 'Risk Analysis'),
        ('environmental_impact', 'Environmental Impact'),
        ('conclusion', 'Conclusion'),
    ]
    for key, label in trailing_ai:
        text = ai.get(key)
        if text:
            _render_ai_chapter(doc, key, label, text)

    # 5. Reference sections.
    _render_key_assumptions(doc, project)
    _render_limitations(doc)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def save_docx_to_disk(project, output_path: str) -> str:
    """Dev/debug: render + write to `output_path`. Returns the same path."""
    data = render_docx_for_project(project)
    with open(output_path, 'wb') as f:
        f.write(data)
    return output_path
