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
from docx.shared import Inches, Pt, RGBColor

from apps.fpo.services.dpr.calculation import CalculationResult, compute
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


def _fmt_inr(amount: Optional[Decimal]) -> str:
    """Render a Decimal ₹ amount as `₹ 12,34,567.89` (Indian numbering)."""
    if amount is None:
        return '—'
    negative = amount < 0
    a = abs(amount).quantize(Decimal('0.01'))
    int_part, _, dec_part = str(a).partition('.')
    if len(int_part) > 3:
        head, tail = int_part[:-3], int_part[-3:]
        pieces = []
        while len(head) > 2:
            pieces.insert(0, head[-2:])
            head = head[:-2]
        if head:
            pieces.insert(0, head)
        int_part = ','.join(pieces) + ',' + tail
    sign = '-' if negative else ''
    return f'₹ {sign}{int_part}.{dec_part or "00"}'


def _fmt_num(v, suffix: str = '') -> str:
    if v is None:
        return '—'
    return f'{v}{suffix}'


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


def _add_multi_year_table(
    doc,
    label: str,
    rows: list[dict],
    formatter=lambda v: _fmt_inr(v),
    heading_level: int = 1,
) -> None:
    """Render a multi-year financial table.

    `rows` is a list of dicts like `[{'label': 'Revenue', 'y1': ..., 'y2': ...}]`.
    Column headers come from the union of numeric keys sorted, so the caller
    doesn't have to hand-write header rows.
    """
    if not rows:
        return
    if label:
        _add_heading(doc, label, level=heading_level)
    # Column order: label first, then y1..yN (or year1..).
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
    for i, row in enumerate(rows, start=1):
        cells = table.rows[i].cells
        cells[0].text = str(row.get('label') or '—')
        for j, k in enumerate(year_keys, start=1):
            v = row.get(k)
            cells[j].text = formatter(v) if v is not None else '—'


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
        if not r.profit_loss or not r.profit_loss.rows:
            return '—'
        parts = []
        for row in r.profit_loss.rows[:3]:
            parts.append(f'Y{row.year}: {_fmt_inr(row.pat)}')
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
        rate = r.ratios.discount_rate_pct if r.ratios and r.ratios.discount_rate_pct is not None else None
        label = f'Net Present Value ({rate}%)' if rate is not None else 'Net Present Value'
        val = _fmt_inr(r.ratios.npv) if r.ratios and r.ratios.npv is not None else '—'
        return label, val

    def _irr() -> str:
        if not r.ratios or r.ratios.irr_pct is None:
            return 'Not solvable — see §11'
        return f'{r.ratios.irr_pct}%'

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
        ('5',  'Legal structure',                   (getattr(fpo, 'legal_structure', '') or '—') if fpo else '—', False),
        ('6',  'Number of members / shareholders',  str(getattr(fpo, 'total_members', '') or '—') if fpo else '—', False),
        ('7',  'Promoting agency',                  (getattr(fpo, 'promoting_agency', '') or '—') if fpo else '—', False),
        ('8',  'Facilitating agency',               (getattr(fpo, 'facilitating_agency_name', '') or '—') if fpo else '—', False),
        ('9',  'Total project cost',                _fmt_inr(r.cost.total), True),
    ]
    cost_sub_rows = _breakdown_rows(r.cost.by_field, COST_LABELS)
    mof_row = ('10', 'Means of finance', _fmt_inr(r.mof.total), True)
    mof_sub_rows = _breakdown_rows(r.mof.by_field, MOF_LABELS)
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
        _emit(idx, '', str(sub_label), _fmt_inr(sub_val) if isinstance(sub_val, Decimal) else str(sub_val), sub=True)
        idx += 1
    _emit(idx, mof_row[0], mof_row[1], mof_row[2], bold_value=mof_row[3])
    idx += 1
    for sub_label, sub_val in mof_sub_rows:
        _emit(idx, '', str(sub_label), _fmt_inr(sub_val) if isinstance(sub_val, Decimal) else str(sub_val), sub=True)
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
    # Data rows
    for i, (label, value) in enumerate(rows, start=1):
        table.rows[i].cells[0].text = str(label)
        table.rows[i].cells[1].text = _fmt_inr(value) if isinstance(value, Decimal) else str(value)
    # Total row
    total_cells = table.rows[-1].cells
    total_cells[0].text = 'Total Project Cost'
    total_cells[1].text = _fmt_inr(r.cost.total)
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
        table.rows[i].cells[1].text = _fmt_inr(value) if isinstance(value, Decimal) else str(value)


def _render_means_of_finance(doc, r: CalculationResult) -> None:
    """PDF §3 Means of Finance — sources table with total."""
    rows = _breakdown_rows(r.mof.by_field, MOF_LABELS)
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
    for i, (label, value) in enumerate(rows, start=1):
        table.rows[i].cells[0].text = str(label)
        table.rows[i].cells[1].text = _fmt_inr(value) if isinstance(value, Decimal) else str(value)
    total_cells = table.rows[-1].cells
    total_cells[0].text = 'Total Means of Finance'
    total_cells[1].text = _fmt_inr(r.mof.total)
    for cell in total_cells:
        for para in cell.paragraphs:
            for run in para.runs:
                run.bold = True


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
        # 1 row × 2 cols. Image on the left (2 inches), details on the right.
        card = doc.add_table(rows=1, cols=2)
        card.style = 'Light Grid Accent 1'
        card.autofit = False
        # Column widths — python-docx sets width per cell for reliability
        # across word processors (Word ignores table-level widths sometimes).
        img_col_width = Inches(2.0)
        details_col_width = Inches(4.5)
        card.columns[0].width = img_col_width
        card.columns[1].width = details_col_width
        img_cell, details_cell = card.rows[0].cells
        img_cell.width = img_col_width
        details_cell.width = details_col_width

        # ── Left cell: product image ─────────────────────────────────────
        img_path = p.get('image_path') or ''
        if img_path:
            # First paragraph of a table cell exists by default — write into it.
            para = img_cell.paragraphs[0]
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            try:
                with open(img_path, 'rb') as f:
                    img_bytes = f.read()
                para.add_run().add_picture(io.BytesIO(img_bytes), width=Inches(1.8))
            except Exception:  # noqa: BLE001 — bad image path shouldn't kill the DOCX
                para.add_run('(image unavailable)').italic = True
        else:
            img_cell.paragraphs[0].text = ''

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
        ('Interest', 'interest'),
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
    if not r.cash_flow or not r.cash_flow.rows:
        return []
    fields = [
        ('PAT', 'pat'),
        ('Depreciation add-back', 'depreciation_addback'),
        ('Working capital Δ', 'working_capital_change'),
        ('Cash from operations', 'cash_from_operations'),
        ('Capex', 'capex'),
        ('Cash from investing', 'cash_from_investing'),
        ('MoF inflow', 'mof_inflow'),
        ('Loan principal repayment', 'loan_principal_repayment'),
        ('Cash from financing', 'cash_from_financing'),
        ('Net cash flow', 'net_cash_flow'),
        ('Opening cash', 'opening_cash'),
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
    ]
    out: list[dict] = []
    for label, attr in fields:
        row: dict = {'label': label}
        for bs in r.balance_sheet.rows:
            row[f'y{bs.year}'] = getattr(bs, attr, None)
        out.append(row)
    return out


def _rows_from_interest(r: CalculationResult) -> list[dict]:
    sched = r.interest_schedule
    if not sched or not sched.rows:
        return []
    fields = [
        ('Opening balance', 'opening_balance'),
        ('Interest', 'interest'),
        ('Principal', 'principal'),
        ('Closing balance', 'closing_balance'),
    ]
    out: list[dict] = []
    for label, attr in fields:
        row: dict = {'label': label}
        for r_ in sched.rows:
            row[f'y{r_.year}'] = getattr(r_, attr, None)
        out.append(row)
    return out


def _render_ratios(doc, r: CalculationResult) -> None:
    """Ratios don't fit the year-by-year layout — render as key/value."""
    ratios = r.ratios
    if not ratios:
        return
    _add_heading(doc, '10. Financial Appraisal', level=1, bookmark='sec_10')
    rows = []
    for attr in (
        'dscr_avg', 'dscr_minimum', 'irr_pct', 'npv', 'bcr', 'roi_pct',
        'payback_years', 'break_even_pct',
    ):
        v = getattr(ratios, attr, None) if hasattr(ratios, attr) else None
        if v is not None:
            pretty = attr.replace('_pct', ' (%)').replace('_', ' ').title()
            display = _fmt_inr(v) if attr == 'npv' else _fmt_num(v)
            rows.append((pretty, display))
    _add_two_col_table(doc, rows)


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
    for i, cls in enumerate(dep.classes, start=1):
        cells = table.rows[i].cells
        cells[0].text = cls.label
        cells[1].text = _fmt_num(cls.rate_pct, '%')
        cells[2].text = _fmt_inr(cls.initial_cost)
        for j, row in enumerate(cls.rows):
            cells[3 + j].text = _fmt_inr(row.depreciation)
        # Net block at end of horizon = closing_gross - closing_accum_dep from last row.
        net_last = (cls.rows[-1].net_block if cls.rows else None)
        cells[-1].text = _fmt_inr(net_last) if net_last is not None else '—'
    # Totals row.
    total_cells = table.rows[-1].cells
    total_cells[0].text = 'Total'
    for para in total_cells[0].paragraphs:
        for run in para.runs:
            run.bold = True
    total_cells[2].text = _fmt_inr(dep.total_initial_cost)
    for j, y in enumerate(years):
        total_cells[3 + j].text = _fmt_inr(dep.total_depreciation_by_year.get(y, Decimal('0')))


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
    for i, row in enumerate(sched.rows, start=1):
        cells = table.rows[i].cells
        cells[0].text = str(getattr(row, 'month', '—'))
        cells[1].text = _fmt_inr(getattr(row, 'cost_incurred', None))
        cells[2].text = _fmt_inr(getattr(row, 'mof_received', None))
        cells[3].text = _fmt_inr(getattr(row, 'cumulative_cost', None))
        cells[4].text = _fmt_inr(getattr(row, 'cumulative_mof', None))
        cells[5].text = _fmt_inr(getattr(row, 'unfunded', None))


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

    overall = (ra.overall_class or 'low').lower()
    badge_colour = {
        'high': RGBColor(0xC0, 0x2D, 0x2D),
        'moderate': RGBColor(0xB4, 0x60, 0x00),
        'low': RGBColor(0x2E, 0x7D, 0x32),
    }.get(overall, RGBColor(0x33, 0x33, 0x33))

    p_summary = doc.add_paragraph()
    p_summary.add_run('Overall project risk: ').bold = True
    badge_run = p_summary.add_run(overall.capitalize())
    badge_run.bold = True
    badge_run.font.color.rgb = badge_colour
    p_summary.add_run(
        f'   ·   {ra.total_risks_scored} of {ra.total_risks_added} risks scored via matrix'
    )
    if getattr(ra, 'matrix_note', ''):
        _add_para(doc, ra.matrix_note, italic=True, size=9)

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
        for i, cat in enumerate(ra.categories, start=1):
            row = table.rows[i].cells
            row[0].text = cat.category_label
            row[1].text = str(cat.risk_count)
            row[2].text = str(cat.scored_count)
            row[3].text = str(cat.class_counts.get('low', 0))
            row[4].text = str(cat.class_counts.get('moderate', 0))
            row[5].text = str(cat.class_counts.get('high', 0))
            # Category class colour to mirror the PDF badge visual.
            cclass = (cat.category_class or 'low').lower()
            row[6].text = cclass.capitalize()
            for para in row[6].paragraphs:
                for run in para.runs:
                    run.bold = True
                    run.font.color.rgb = {
                        'high': RGBColor(0xC0, 0x2D, 0x2D),
                        'moderate': RGBColor(0xB4, 0x60, 0x00),
                        'low': RGBColor(0x2E, 0x7D, 0x32),
                    }.get(cclass, RGBColor(0x33, 0x33, 0x33))

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

    trailing_map = {
        'market_analysis': ('Market Analysis (AI)', 'sec_ai_market_analysis'),
        'technical_feasibility': ('Technical Feasibility (AI)', 'sec_ai_technical_feasibility'),
        'financial_analysis': ('Financial Analysis (AI)', 'sec_ai_financial_analysis'),
        'implementation_plan': ('Implementation Plan (AI)', 'sec_ai_implementation_plan'),
        'swot': ('SWOT Analysis (AI)', 'sec_ai_swot'),
        'environmental_impact': ('Environmental Impact (AI)', 'sec_ai_environmental_impact'),
        'conclusion': ('Conclusion', 'sec_ai_conclusion'),
    }
    for key, entry in trailing_map.items():
        if ai.get(key):
            entries.append(entry)

    entries.append(('Key Assumptions Used', 'sec_assumptions'))
    entries.append(('Limitations & Guidelines for Entrepreneurs', 'sec_guidelines'))

    for i, (label, anchor) in enumerate(entries, start=1):
        # Numbered list style so entries visually align like PDF TOC.
        p = doc.add_paragraph(style='List Number')
        # Add the hyperlink inside the paragraph — Word treats it as a
        # clickable target with underline + blue-ish colour from Hyperlink
        # character style.
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


def _render_key_assumptions(doc) -> None:
    rows = _key_assumptions_rows()
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
    for i, row in enumerate(rows, start=1):
        cells = table.rows[i].cells
        cells[0].text = str(row.get('label') or '—')
        cells[1].text = str(row.get('value') or '—')
        cells[2].text = str(row.get('source') or '—')


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

    version_label = f'v{version_number}' if version_number else 'Preview'
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
    _render_depreciation_schedule(doc, result)

    # §6 Loan Repayment Schedule (chart + table).
    if result.interest_schedule and getattr(result.interest_schedule, 'rows', None):
        _add_heading(doc, '6. Loan Repayment Schedule', level=1, bookmark='sec_6')
        _embed_data_url_chart(doc, repayment_schedule_bar(result.interest_schedule.rows))
        _add_multi_year_table(doc, '', _rows_from_interest(result), heading_level=2)
        # Blank string heading to skip drawing an inner sub-heading; but
        # `_add_multi_year_table` unconditionally calls _add_heading. Simpler
        # to just re-emit the section title as sub-header for the table.
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
    trailing_ai = [
        ('market_analysis', 'Market Analysis'),
        ('technical_feasibility', 'Technical Feasibility'),
        ('financial_analysis', 'Financial Analysis'),
        ('implementation_plan', 'Implementation Plan'),
        ('swot', 'SWOT Analysis'),
        ('environmental_impact', 'Environmental Impact'),
        ('conclusion', 'Conclusion'),
    ]
    for key, label in trailing_ai:
        text = ai.get(key)
        if text:
            _render_ai_chapter(doc, key, label, text)

    # 5. Reference sections.
    _render_key_assumptions(doc)
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
