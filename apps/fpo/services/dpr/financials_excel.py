"""
DPR financials → Excel workbook exporter.

Per KAU pre-UAT reply §6.3 (2026-09-08): bankers and appraisal officers need
the projected financial tables in a spreadsheet, not just a PDF, so they can
verify the calc engine's numbers cell-by-cell against their own models.

Public entry point:
    * `render_financials_workbook(project) -> BytesIO`

Produced sheets (fixed order — banker-familiar):
    A. Project Summary       — meta + top-line ratios
    B. Cost & MoF Variance   — user vs derived + gap
    C. Capital Schedule      — per-month capex plan
    D. Depreciation          — per asset class + per year
    E. Interest Schedule     — per year amortisation
    F. Profit & Loss         — Y1..YN
    G. Cash Flow             — Y0..YN
    H. Balance Sheet         — Y0..YN + invariant check
    I. Ratios                — NPV / IRR / DSCR / payback / break-even
    J. DSCR per year         — year-by-year debt service coverage
    K. Products              — commodities, quantities, prices (KAU 2026-09-26)
    L. Process Flows         — per-technology steps                (KAU 2026-09-26)
    M. Narratives            — AI-generated chapter prose          (KAU 2026-09-26)
    N. Key Assumptions       — every DPRConfig-driven rate the calc engine used

Content-parity update (2026-09-26): the earlier scope was financial-only.
KAU asked us to fold in ALL the PDF sections so bankers who prefer Excel
get the same information — hence sheets K-N.

Author: Athul Gopan (Kefi Tech Solutions)
"""
from __future__ import annotations

import base64
from decimal import Decimal
from io import BytesIO
from typing import Iterable, Optional

import openpyxl
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from apps.fpo.services.dpr.calculation import CalculationResult, compute
from apps.fpo.services.dpr.chart_helpers import (
    cost_breakdown_pie,
    pnl_trend_bar,
    repayment_schedule_bar,
)


# ── Styling constants ─────────────────────────────────────────────────────
_HEADER_FILL = PatternFill(start_color='1F3864', end_color='1F3864', fill_type='solid')
_HEADER_FONT = Font(name='Calibri', size=11, bold=True, color='FFFFFF')
_SECTION_FILL = PatternFill(start_color='E86C1A', end_color='E86C1A', fill_type='solid')
_SECTION_FONT = Font(name='Calibri', size=12, bold=True, color='FFFFFF')
_ROW_ALT_FILL = PatternFill(start_color='F5F5F5', end_color='F5F5F5', fill_type='solid')
_NUM_FMT = '#,##0.00'
_INT_FMT = '#,##0'
_PCT_FMT = '0.00"%"'


def render_financials_workbook(project) -> BytesIO:
    """Compute the DPR then materialise all 14 sheets. Returns an in-memory
    BytesIO with the .xlsx bytes ready to stream via `FileResponse`.
    """
    result: CalculationResult = compute(project)
    wb = openpyxl.Workbook()

    # openpyxl creates a default sheet — repurpose it for the summary
    # instead of leaving an empty first tab.
    _write_summary_sheet(wb.active, project, result)

    # Hero product image on the Summary tab so the file's cover matches the
    # PDF's cover. Anchored below the ratios strip. No-op when no product has
    # a photo — same fallback as the PDF template.
    from apps.fpo.services.dpr.pdf import _products_for_pdf
    _, hero_path = _products_for_pdf(project)
    if hero_path:
        _embed_image_file(wb.active, hero_path, anchor='D2', width_px=320)

    _write_cost_mof_sheet(wb.create_sheet('B — Cost & MoF'), result)
    _write_capital_schedule_sheet(wb.create_sheet('C — Capital Schedule'), result)
    _write_depreciation_sheet(wb.create_sheet('D — Depreciation'), result)
    _write_interest_sheet(wb.create_sheet('E — Interest'), result)
    _write_pnl_sheet(wb.create_sheet('F — P&L'), result)
    _write_cash_flow_sheet(wb.create_sheet('G — Cash Flow'), result)
    _write_balance_sheet_sheet(wb.create_sheet('H — Balance Sheet'), result)
    _write_ratios_sheet(wb.create_sheet('I — Ratios'), result)
    _write_dscr_sheet(wb.create_sheet('J — DSCR by Year'), result)

    # KAU 2026-09-26 content-parity — everything the PDF ships.
    _write_products_sheet(wb.create_sheet('K — Products'), project)
    _write_process_flows_sheet(wb.create_sheet('L — Process Flows'), project)
    _write_narratives_sheet(wb.create_sheet('M — Narratives'), project)
    _write_key_assumptions_sheet(wb.create_sheet('N — Key Assumptions'))

    out = BytesIO()
    wb.save(out)
    out.seek(0)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Sheet writers
# ─────────────────────────────────────────────────────────────────────────────

def _write_summary_sheet(ws, project, r: CalculationResult) -> None:
    """Cover-styled summary sheet — matches the PDF's Chapter 0 (cover +
    project meta box + key ratios strip + disclaimer).

    Layout convention:
      * Rows 1-3   → FPO name / project title / KAU-FPO branding
      * Rows 4-7   → Big centred "Detailed Project Report" heading
      * Rows 9-15  → Project meta box (bordered)
      * Rows 17-24 → Key Ratios strip
      * Rows 26-28 → Disclaimer block
      * Rows 30+   → Cost + MoF snapshot (kept from earlier version so the
        summary tab is standalone-useful, not just cover art).
    """
    ws.title = 'A — Summary'
    # Column widths tuned so the cover fits on a portrait A4 page (both in
    # Excel's print preview + LibreOffice conversion for KAU review).
    _set_col_widths(ws, [26, 24, 20])

    # Page setup for the cover — portrait, fit to 1 page wide, centred.
    ws.page_setup.orientation = ws.ORIENTATION_PORTRAIT
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_options.horizontalCentered = True
    ws.page_margins.left = 0.5
    ws.page_margins.right = 0.5

    # ── FPO name (small, top-left — parallel to the PDF's cover header) ──
    fpo_name = getattr(getattr(project, 'fpo', None), 'name', '') or '—'
    c = ws.cell(row=1, column=1, value=fpo_name)
    c.font = Font(name='Calibri', size=14, bold=True, color='1F3864')
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=3)

    # ── Big centred title ────────────────────────────────────────────────
    c = ws.cell(row=3, column=1, value='DETAILED PROJECT REPORT')
    c.font = Font(name='Calibri', size=22, bold=True, color='1F3864')
    c.alignment = Alignment(horizontal='center', vertical='center')
    ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=3)
    ws.row_dimensions[3].height = 32

    c = ws.cell(row=4, column=1, value='Prepared under the KAU-FPO Linkage Programme')
    c.font = Font(name='Calibri', size=11, italic=True, color='6B6B6B')
    c.alignment = Alignment(horizontal='center')
    ws.merge_cells(start_row=4, start_column=1, end_row=4, end_column=3)

    # Project title in KAU orange, matches PDF cover accent
    c = ws.cell(row=6, column=1, value=project.title or '—')
    c.font = Font(name='Calibri', size=16, bold=True, color='E86C1A')
    c.alignment = Alignment(horizontal='center')
    ws.merge_cells(start_row=6, start_column=1, end_row=6, end_column=3)

    # ── Project meta box (like the PDF's bordered info panel) ────────────
    _write_section_title(ws, 8, 1, 'Project Details')
    ws.merge_cells(start_row=8, start_column=1, end_row=8, end_column=3)

    thin_border = Border(
        left=Side(style='thin', color='D0D0D0'),
        right=Side(style='thin', color='D0D0D0'),
        top=Side(style='thin', color='D0D0D0'),
        bottom=Side(style='thin', color='D0D0D0'),
    )
    meta_rows = [
        ('DPR version', 'v-preview'),
        ('Generated', ''),  # filled by caller before write? Keep placeholder.
        ('Status', 'Preview'),
        ('Projection horizon', f'{r.projection_years} years'),
        ('Primary commodity', (
            project.primary_commodity.get_name('en')
            if getattr(project, 'primary_commodity_id', None) else '—'
        )),
        ('Project UUID', str(project.uuid)),
    ]
    from datetime import datetime as _dt
    meta_rows[1] = ('Generated', _dt.now().strftime('%d %b %Y · %I:%M %p'))
    row = 9
    for label, value in meta_rows:
        c1 = ws.cell(row=row, column=1, value=label)
        c1.font = Font(bold=True, color='1F3864')
        c1.border = thin_border
        c1.alignment = Alignment(vertical='center')
        c2 = ws.cell(row=row, column=2, value=value)
        c2.border = thin_border
        c2.alignment = Alignment(vertical='center')
        # Merge value cell across cols 2-3 for readability of long values.
        ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=3)
        row += 1

    # ── Key Ratios strip ─────────────────────────────────────────────────
    row += 1
    _write_section_title(ws, row, 1, 'Key Ratios')
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=3)
    row += 1
    ratios = r.ratios
    if ratios:
        pairs = [
            ('Total project cost (₹)', r.cost.total, 'num'),
            # BUG-37: headline MoF excludes the WC facility (cash credit) —
            # it is an operating line, not project funding.
            ('Total means of finance (₹)', r.mof.project_funding_total, 'num'),
            ('MoF − Cost delta (₹)', r.variance.delta, 'num'),
            ('Variance %', r.variance.pct, 'pct'),
            ('Discount rate', ratios.discount_rate_pct, 'pct'),
            ('NPV (₹)', ratios.npv, 'num'),
            ('IRR (%)', ratios.irr_pct, 'pct'),
            ('Min DSCR', ratios.dscr_min, 'num'),
            ('Avg DSCR', ratios.dscr_avg, 'num'),
            ('Payback (years)', ratios.payback_period_years, 'num'),
            ('Break-even year', ratios.break_even_year, 'raw'),
        ]
        for label, value, kind in pairs:
            c1 = ws.cell(row=row, column=1, value=label)
            c1.font = Font(bold=True)
            c1.border = thin_border
            if kind == 'num':
                _num_cell(ws, row, 2, value)
            elif kind == 'pct':
                _pct_cell(ws, row, 2, value)
            else:
                ws.cell(row=row, column=2, value=value if value is not None else '—')
            ws.cell(row=row, column=2).border = thin_border
            row += 1
    else:
        c = ws.cell(row=row, column=1, value='(Ratios not available — insufficient data)')
        c.font = Font(italic=True)
        row += 1

    # ── Disclaimer (mirrors the PDF cover's orange-bordered box) ────────
    row += 1
    disclaimer_cell = ws.cell(
        row=row, column=1,
        value=(
            'DISCLAIMER — This Detailed Project Report has been prepared by the '
            'above-named Farmer Producer Organisation using the Kerala Agricultural '
            'University (KAU) DPR platform. Generation of this report through the '
            'platform does not imply that KAU has approved, certified or endorsed '
            'its contents. Its acceptance for bank submission, scheme application '
            'or any other purpose is subject to the requirements of the concerned '
            'bank, implementing agency or authority. Figures are rounded to the '
            'nearest rupee.'
        ),
    )
    disclaimer_cell.font = Font(size=9, italic=True, color='6B6B6B')
    disclaimer_cell.alignment = Alignment(wrap_text=True, vertical='top')
    disclaimer_cell.border = Border(
        left=Side(style='medium', color='E86C1A'),
        right=Side(style='medium', color='E86C1A'),
        top=Side(style='medium', color='E86C1A'),
        bottom=Side(style='medium', color='E86C1A'),
    )
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=3)
    ws.row_dimensions[row].height = 90


def _write_cost_mof_sheet(ws, r: CalculationResult) -> None:
    _set_col_widths(ws, [40, 22, 22, 22])
    _write_section_title(ws, 1, 1, 'A. Project Cost — Line-item Breakdown')
    _write_header(ws, 2, ['Cost line', 'Amount (₹)'])
    ws.freeze_panes = 'A3'
    row = 3
    data_start = row
    for k, v in sorted(r.cost.by_field.items()):
        ws.cell(row=row, column=1, value=k)
        _num_cell(ws, row, 2, v); row += 1
    _apply_zebra(ws, data_start, row - 1, cols=2)
    ws.cell(row=row, column=1, value='TOTAL').font = Font(bold=True)
    _num_cell(ws, row, 2, r.cost.total); row += 2

    # Embed the cost breakdown pie chart to the right of the totals — same
    # visual the PDF surfaces in "Project at a Glance". Positioned at col D
    # so the tabular data stays readable in cols A-B.
    _embed_chart(ws, cost_breakdown_pie(r.cost.by_field), anchor='D2')

    _write_section_title(ws, row, 1, 'B. Means of Finance — Line-item Breakdown')
    row += 1
    _write_header(ws, row, ['MoF line', 'Amount (₹)']); row += 1
    # BUG-37: the WC facility is listed after the TOTAL as a separate
    # facility line — it never counts toward project funding.
    for k, v in sorted(r.mof.by_field.items()):
        if k == 'mof_working_capital_loan':
            continue
        ws.cell(row=row, column=1, value=k)
        _num_cell(ws, row, 2, v); row += 1
    ws.cell(row=row, column=1, value='TOTAL').font = Font(bold=True)
    _num_cell(ws, row, 2, r.mof.project_funding_total); row += 1
    if r.mof.wc_facility:
        ws.cell(
            row=row, column=1,
            value='Working-capital facility (cash credit) — outside project funding',
        ).font = Font(italic=True)
        _num_cell(ws, row, 2, r.mof.wc_facility); row += 1
    row += 1

    _write_section_title(ws, row, 1, 'C. Cost ↔ MoF Reconciliation')
    row += 1
    ws.cell(row=row, column=1, value='Total project cost').font = Font(bold=True)
    _num_cell(ws, row, 2, r.variance.cost_total); row += 1
    ws.cell(row=row, column=1, value='Total MoF').font = Font(bold=True)
    _num_cell(ws, row, 2, r.variance.mof_total); row += 1
    ws.cell(row=row, column=1, value='MoF − Cost delta').font = Font(bold=True)
    _num_cell(ws, row, 2, r.variance.delta); row += 1
    ws.cell(row=row, column=1, value='Variance %').font = Font(bold=True)
    _pct_cell(ws, row, 2, r.variance.pct); row += 1
    ws.cell(row=row, column=1, value='Threshold %').font = Font(bold=True)
    _pct_cell(ws, row, 2, r.variance.threshold_pct); row += 1
    ws.cell(row=row, column=1, value='Exceeds threshold?').font = Font(bold=True)
    ws.cell(row=row, column=2, value='Yes' if r.variance.exceeds_threshold else 'No')


def _write_capital_schedule_sheet(ws, r: CalculationResult) -> None:
    _set_col_widths(ws, [10, 18, 18, 20, 20, 20])
    sched = r.capital_schedule
    if not sched:
        ws.cell(row=1, column=1, value='(Capital schedule not available — no tranches recorded)')
        return
    _write_section_title(ws, 1, 1, 'Capital Schedule (per-month capex plan)')
    ws.cell(row=2, column=1, value=sched.distribution_note).font = Font(italic=True)
    ws.cell(row=3, column=1, value=f'is_estimated: {"Yes" if sched.is_estimated else "No"} · '
                                    f'implementation period: {sched.implementation_period_months} months').font = Font(italic=True)
    _write_header(ws, 5, ['Month', 'Cost incurred', 'MoF received',
                          'Cum cost', 'Cum MoF', 'Unfunded'])
    row = 6
    for r_row in sched.rows:
        ws.cell(row=row, column=1, value=f'M{r_row.month}')
        _num_cell(ws, row, 2, r_row.cost_incurred)
        _num_cell(ws, row, 3, r_row.mof_received)
        _num_cell(ws, row, 4, r_row.cumulative_cost)
        _num_cell(ws, row, 5, r_row.cumulative_mof)
        _num_cell(ws, row, 6, r_row.unfunded_balance)
        row += 1
    ws.cell(row=row, column=1, value='FINAL').font = Font(bold=True)
    _num_cell(ws, row, 4, sched.final_cost)
    _num_cell(ws, row, 5, sched.final_mof)


def _write_depreciation_sheet(ws, r: CalculationResult) -> None:
    dep = r.depreciation
    if not dep:
        ws.cell(row=1, column=1, value='(Depreciation schedule not available)')
        return
    _write_section_title(ws, 1, 1, 'Depreciation Schedule — SLM, per asset class')
    years = list(range(1, r.projection_years + 1))
    header = ['Asset class', 'Initial cost (₹)', 'Rate (%)', *[f'Y{y} dep' for y in years], 'Total dep']
    _set_col_widths(ws, [22, 20, 12] + [14] * len(years) + [20])
    _write_header(ws, 2, header)
    row = 3
    for cls in dep.classes:
        ws.cell(row=row, column=1, value=cls.label or cls.key)
        _num_cell(ws, row, 2, cls.initial_cost)
        _pct_cell(ws, row, 3, cls.rate_pct)
        col = 4
        cls_rows = {ar.year: ar.depreciation for ar in cls.rows}
        for y in years:
            _num_cell(ws, row, col, cls_rows.get(y, Decimal('0')))
            col += 1
        _num_cell(ws, row, col, sum((ar.depreciation for ar in cls.rows), Decimal('0')))
        row += 1
    # Yearly totals (already computed on dep.total_depreciation_by_year)
    ws.cell(row=row, column=1, value='TOTAL').font = Font(bold=True)
    col = 4
    for y in years:
        _num_cell(ws, row, col, dep.total_depreciation_by_year.get(y, Decimal('0')))
        col += 1


def _write_interest_sheet(ws, r: CalculationResult) -> None:
    isch = r.interest_schedule
    _set_col_widths(ws, [8, 22, 22, 22, 22])
    _write_section_title(ws, 1, 1, 'Interest & Principal Amortisation Schedule')
    if not isch or not isch.rows:
        ws.cell(row=2, column=1, value='(No loan proposed — schedule empty)')
        return
    ws.cell(row=2, column=1, value=f'Method: {isch.repayment_method}').font = Font(italic=True)
    ws.cell(row=3, column=1, value=f'Moratorium: {isch.moratorium_months} months · '
                                    f'{isch.moratorium_interest_treatment}').font = Font(italic=True)
    _write_header(ws, 5, ['Year', 'Opening bal', 'Interest', 'Principal', 'Closing bal'])
    ws.freeze_panes = 'A6'
    data_start = 6
    row = 6
    for r_row in isch.rows:
        ws.cell(row=row, column=1, value=r_row.year)
        _num_cell(ws, row, 2, r_row.opening_balance)
        _num_cell(ws, row, 3, r_row.interest)
        _num_cell(ws, row, 4, r_row.principal)
        _num_cell(ws, row, 5, r_row.closing_balance)
        row += 1
    _apply_zebra(ws, data_start, row - 1, cols=5)

    # Repayment bar chart to the right of the table — matches the PDF's
    # per-year interest vs principal visualisation.
    _embed_chart(ws, repayment_schedule_bar(isch.rows), anchor='G2')


def _write_pnl_sheet(ws, r: CalculationResult) -> None:
    pl = r.profit_loss
    _set_col_widths(ws, [22, 8] + [16] * 10)
    _write_section_title(ws, 1, 1, 'Projected Profit & Loss (₹)')
    if not pl:
        ws.cell(row=2, column=1, value='(P&L not available)')
        return
    years = [row.year for row in pl.rows]
    _write_header(ws, 2, ['Line item', ''] + [f'Y{y}' for y in years])
    ws.freeze_panes = 'C3'

    lines = [
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
    row = 3
    data_start = row
    for label, attr in lines:
        ws.cell(row=row, column=1, value=label).font = Font(bold=(label in ('EBITDA', 'EBIT', 'PBT', 'PAT')))
        col = 3
        for r_row in pl.rows:
            _num_cell(ws, row, col, getattr(r_row, attr))
            col += 1
        row += 1
    _apply_zebra(ws, data_start, row - 1, cols=2 + len(years))

    # P&L trend bar chart below the table.
    _embed_chart(ws, pnl_trend_bar(pl.rows), anchor=f'A{row + 3}')

    # Cumulative PAT row for banker sight-line
    row += 1
    ws.cell(row=row, column=1, value='Cumulative PAT').font = Font(bold=True, italic=True)
    col = 3
    for y in years:
        _num_cell(ws, row, col, pl.cumulative_pat_by_year.get(y, Decimal('0')))
        col += 1


def _write_cash_flow_sheet(ws, r: CalculationResult) -> None:
    cf = r.cash_flow
    _set_col_widths(ws, [30, 8] + [16] * 11)
    _write_section_title(ws, 1, 1, 'Projected Cash Flow (₹)')
    if not cf:
        ws.cell(row=2, column=1, value='(Cash flow not available)')
        return
    years = [row.year for row in cf.rows]
    _write_header(ws, 2, ['Line item', ''] + [f'Y{y}' for y in years])

    # BUG-38: WC lines included only when Y0 carries a value.
    y0 = cf.rows[0]
    lines = [
        ('PAT', 'pat'),
        ('Depreciation add-back', 'depreciation_addback'),
        ('WC change', 'working_capital_change'),
        ('Cash from operations', 'cash_from_operations'),
        ('Capex', 'capex'),
    ]
    if y0.wc_investment:
        lines.append(('Investment in working capital', 'wc_investment'))
    lines += [
        ('Cash from investing', 'cash_from_investing'),
        ('Means of finance (project funding)', 'mof_inflow'),
    ]
    if y0.wc_facility_drawdown:
        lines.append(('WC facility drawdown (cash credit)', 'wc_facility_drawdown'))
    if y0.wc_shortfall_borrowing:
        lines.append(('WC shortfall borrowing (to be arranged)', 'wc_shortfall_borrowing'))
    lines += [
        ('Loan principal repayment', 'loan_principal_repayment'),
        ('Cash from financing', 'cash_from_financing'),
        ('Net cash flow', 'net_cash_flow'),
        ('Opening cash', 'opening_cash'),
        ('Closing cash', 'closing_cash'),
    ]
    row = 3
    for label, attr in lines:
        bold = label in (
            'Cash from operations', 'Cash from investing', 'Cash from financing',
            'Net cash flow', 'Closing cash',
        )
        ws.cell(row=row, column=1, value=label).font = Font(bold=bold)
        col = 3
        for r_row in cf.rows:
            _num_cell(ws, row, col, getattr(r_row, attr))
            col += 1
        row += 1

    row += 1
    ws.cell(row=row, column=1, value='Ending cash').font = Font(bold=True, italic=True)
    _num_cell(ws, row, 3, cf.ending_cash)


def _write_balance_sheet_sheet(ws, r: CalculationResult) -> None:
    bs = r.balance_sheet
    _set_col_widths(ws, [32, 8] + [16] * 11)
    _write_section_title(ws, 1, 1, 'Projected Balance Sheet (₹)')
    if not bs:
        ws.cell(row=2, column=1, value='(Balance sheet not available)')
        return
    years = [row.year for row in bs.rows]
    _write_header(ws, 2, ['Line item', ''] + [f'Y{y}' for y in years])

    lines = [
        ('— ASSETS —', None),
        ('Land', 'land'),
        ('CWIP', 'cwip'),
        ('Gross fixed assets', 'gross_fixed_assets'),
        ('Accumulated depreciation', 'accumulated_depreciation'),
        ('Net fixed assets', 'net_fixed_assets'),
        ('Working capital', 'working_capital'),
        ('Cash & bank', 'cash_and_bank'),
        ('TOTAL ASSETS', 'total_assets'),
        ('— EQUITY & LIABILITIES —', None),
        ('Promoter equity', 'promoter_equity'),
        ('Capital reserve', 'capital_reserve'),
        ('Retained earnings', 'retained_earnings'),
        ('Total equity', 'total_equity'),
        ('Term loan outstanding', 'term_loan_outstanding'),
        ('Other liabilities', 'other_liabilities'),
        ('Total liabilities', 'total_liabilities'),
        ('TOTAL EQUITY & LIABILITIES', 'total_equity_and_liabilities'),
        ('Invariant delta (should ≈ 0)', 'invariant_delta'),
        ('Invariant OK', 'invariant_ok'),
    ]
    row = 3
    for label, attr in lines:
        cell = ws.cell(row=row, column=1, value=label)
        if attr is None:
            cell.font = Font(bold=True)
            cell.fill = _ROW_ALT_FILL
            row += 1
            continue
        cell.font = Font(bold=label.startswith('TOTAL') or label.startswith('Total'))
        col = 3
        for r_row in bs.rows:
            v = getattr(r_row, attr)
            if isinstance(v, bool):
                ws.cell(row=row, column=col, value='Yes' if v else 'No')
            else:
                _num_cell(ws, row, col, v)
            col += 1
        row += 1
    row += 1
    ws.cell(row=row, column=1, value='All years balanced?').font = Font(bold=True)
    ws.cell(row=row, column=3, value='Yes' if bs.all_years_balanced else 'No')
    ws.cell(row=row + 1, column=1, value='Max invariant delta').font = Font(bold=True)
    _num_cell(ws, row + 1, 3, bs.max_invariant_delta)


def _write_ratios_sheet(ws, r: CalculationResult) -> None:
    _set_col_widths(ws, [32, 22])
    _write_section_title(ws, 1, 1, 'Bankability Ratios')
    ratios = r.ratios
    if not ratios:
        ws.cell(row=2, column=1, value='(Ratios not available)')
        return
    row = 2
    def _kv(label, value, fmt='num'):
        nonlocal row
        ws.cell(row=row, column=1, value=label).font = Font(bold=True)
        if value is None:
            ws.cell(row=row, column=2, value='—')
        elif fmt == 'pct':
            _pct_cell(ws, row, 2, value)
        elif fmt == 'int':
            ws.cell(row=row, column=2, value=int(value)).number_format = _INT_FMT
        elif fmt == 'text':
            ws.cell(row=row, column=2, value=str(value))
        else:
            _num_cell(ws, row, 2, value)
        row += 1

    _kv('Discount rate (%)', ratios.discount_rate_pct, 'pct')
    _kv('NPV (₹)', ratios.npv)
    _kv('IRR (%)', ratios.irr_pct, 'pct')
    _kv('IRR bisection converged', 'Yes' if ratios.irr_converged else 'No', 'text')
    _kv('Min DSCR', ratios.dscr_min)
    _kv('Avg DSCR', ratios.dscr_avg)
    _kv('Payback (years)', ratios.payback_period_years)
    _kv('Break-even year', ratios.break_even_year, 'int')


def _write_dscr_sheet(ws, r: CalculationResult) -> None:
    _set_col_widths(ws, [8, 22, 22, 16])
    _write_section_title(ws, 1, 1, 'Debt Service Coverage Ratio — Year by Year')
    ratios = r.ratios
    if not ratios or not ratios.dscr_rows:
        ws.cell(row=2, column=1, value='(No DSCR rows — likely no debt service)')
        return
    _write_header(ws, 2, ['Year', 'Numerator (PAT+Dep+Int)', 'Denominator (Int+Prin)', 'DSCR'])
    row = 3
    for r_row in ratios.dscr_rows:
        ws.cell(row=row, column=1, value=r_row.year)
        _num_cell(ws, row, 2, r_row.numerator)
        _num_cell(ws, row, 3, r_row.denominator)
        if r_row.dscr is None:
            ws.cell(row=row, column=4, value='—')
        else:
            _num_cell(ws, row, 4, r_row.dscr)
        row += 1


# ─────────────────────────────────────────────────────────────────────────────
# Content-parity sheets — KAU 2026-09-26 finalisation ask
# Products / Process Flows / AI Narratives / Key Assumptions
# Import the underlying helpers from pdf.py so the numbers + labels stay in
# lock-step with what the PDF renders — one source of truth.
# ─────────────────────────────────────────────────────────────────────────────

def _write_products_sheet(ws, project) -> None:
    from apps.fpo.services.dpr.pdf import _products_for_pdf
    products, _hero = _products_for_pdf(project)
    ws.title = 'K — Products'
    _set_col_widths(ws, [30, 22, 20, 18, 22, 40])
    _write_section_title(ws, 1, 1, 'Products & Services')
    if not products:
        ws.cell(row=2, column=1, value='(No products defined for this DPR)')
        return
    _write_header(ws, 2, [
        'Product', 'Category', 'Annual quantity', 'Unit',
        'Selling price / unit', 'Description',
    ])
    row = 3
    for p in products:
        ws.cell(row=row, column=1, value=str(p.get('name') or '—'))
        ws.cell(row=row, column=2, value=str(p.get('category') or '—'))
        _num_cell(ws, row, 3, p.get('quantity'))
        ws.cell(row=row, column=4, value=str(p.get('unit') or '—'))
        _num_cell(ws, row, 5, p.get('price'))
        desc = (p.get('description') or '').strip()
        c = ws.cell(row=row, column=6, value=desc)
        c.alignment = Alignment(wrap_text=True, vertical='top')
        row += 1


def _write_process_flows_sheet(ws, project) -> None:
    from apps.fpo.services.dpr.pdf import _technologies_with_flow
    techs = _technologies_with_flow(project)
    ws.title = 'L — Process Flows'
    _set_col_widths(ws, [8, 45, 45])
    _write_section_title(ws, 1, 1, 'Manufacturing Process Flows')
    if not techs:
        ws.cell(row=2, column=1, value='(No process flows defined for this DPR)')
        return
    row = 2
    for tech in techs:
        ws.cell(row=row, column=1, value=tech['name']).font = Font(bold=True)
        row += 1
        if tech.get('description'):
            c = ws.cell(row=row, column=1, value=tech['description'])
            c.alignment = Alignment(wrap_text=True, vertical='top')
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=3)
            row += 1
        _write_header(ws, row, ['Step', 'Action'])
        row += 1
        for i, step in enumerate(tech['steps'], start=1):
            ws.cell(row=row, column=1, value=i)
            c = ws.cell(row=row, column=2, value=step)
            c.alignment = Alignment(wrap_text=True, vertical='top')
            ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=3)
            row += 1
        row += 1  # blank between techs


def _write_narratives_sheet(ws, project) -> None:
    from apps.fpo.services.dpr.pdf import _ai_chapters_for_pdf
    from apps.database.models.dpr.ai_content import CHAPTER_KEYS, CHAPTER_LABELS
    ai = _ai_chapters_for_pdf(project)
    ws.title = 'M — Narratives'
    _set_col_widths(ws, [26, 90])
    _write_section_title(ws, 1, 1, 'AI-Generated Narrative Chapters')
    if not ai:
        ws.cell(row=2, column=1, value='(No AI narratives generated for this DPR yet)')
        return
    _write_header(ws, 2, ['Chapter', 'Text'])
    row = 3
    for key in CHAPTER_KEYS:
        text = (ai.get(key) or '').strip()
        if not text:
            continue
        ws.cell(row=row, column=1, value=CHAPTER_LABELS.get(key, key)).font = Font(bold=True)
        ws.cell(row=row, column=1).alignment = Alignment(vertical='top', wrap_text=True)
        c = ws.cell(row=row, column=2, value=text)
        c.alignment = Alignment(wrap_text=True, vertical='top')
        # Rough height budget — Excel doesn't auto-fit merged wrap-text so
        # 15 pts per ~80 chars of content is a decent approximation.
        est_lines = max(3, min(60, len(text) // 80 + 3))
        ws.row_dimensions[row].height = est_lines * 15
        row += 1


def _write_key_assumptions_sheet(ws) -> None:
    from apps.fpo.services.dpr.pdf import _key_assumptions_rows
    rows = _key_assumptions_rows()
    ws.title = 'N — Key Assumptions'
    _set_col_widths(ws, [40, 22, 40])
    _write_section_title(ws, 1, 1, 'Key Assumptions Used by the Calc Engine')
    if not rows:
        ws.cell(row=2, column=1, value='(No configured assumptions available)')
        return
    _write_header(ws, 2, ['Parameter', 'Value', 'Source'])
    row = 3
    for r in rows:
        ws.cell(row=row, column=1, value=str(r.get('label') or '—'))
        ws.cell(row=row, column=2, value=str(r.get('value') or '—'))
        c = ws.cell(row=row, column=3, value=str(r.get('source') or '—'))
        c.alignment = Alignment(wrap_text=True, vertical='top')
        row += 1


# ─────────────────────────────────────────────────────────────────────────────
# Image / chart helpers — KAU 2026-09-26 finalisation: XLSX must render the
# same charts + hero visual the PDF does so a banker opening either format
# sees the same story.
# ─────────────────────────────────────────────────────────────────────────────

def _embed_chart(ws, data_url: str, anchor: str, width_px: int = 640) -> None:
    """Decode a `data:image/png;base64,...` chart into an XLImage anchored
    on `ws` at cell `anchor`. Silently no-ops when there's no chart data
    (chart helpers return `''` for insufficient inputs — same convention as
    the PDF template)."""
    if not data_url or not data_url.startswith('data:image/'):
        return
    try:
        _prefix, _, b64 = data_url.partition('base64,')
        if not b64:
            return
        raw = base64.b64decode(b64)
    except Exception:  # noqa: BLE001 — chart embed is best-effort
        return
    try:
        img = XLImage(BytesIO(raw))
        # openpyxl uses EMUs (English Metric Units); width in pixels is more
        # intuitive, so we set width and let height scale proportionally.
        img.width = width_px
        img.height = int(width_px * 0.6)   # 5:3 ratio matches matplotlib default
        ws.add_image(img, anchor)
    except Exception:  # noqa: BLE001 — some environments reject certain PNGs
        return


def _embed_image_file(ws, path: str, anchor: str, width_px: int = 480) -> None:
    """Embed a local image file (hero product photo). No-op on bad path."""
    if not path:
        return
    try:
        img = XLImage(path)
        img.width = width_px
        img.height = int(width_px * 0.75)  # 4:3 default
        ws.add_image(img, anchor)
    except Exception:  # noqa: BLE001
        return


def _apply_zebra(ws, start_row: int, end_row: int, cols: int) -> None:
    """Zebra-stripe the data rows so a long P&L sheet is easy to scan.
    Matches the PDF template's alternating grey/white row backgrounds."""
    for r in range(start_row, end_row + 1):
        if (r - start_row) % 2 == 1:
            for c in range(1, cols + 1):
                cell = ws.cell(row=r, column=c)
                if cell.fill.fill_type is None:
                    cell.fill = _ROW_ALT_FILL


# ─────────────────────────────────────────────────────────────────────────────
# Cell helpers
# ─────────────────────────────────────────────────────────────────────────────

def _set_col_widths(ws, widths: Iterable[int]) -> None:
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def _write_section_title(ws, row: int, col: int, title: str) -> None:
    cell = ws.cell(row=row, column=col, value=title)
    cell.font = _SECTION_FONT
    cell.fill = _SECTION_FILL
    cell.alignment = Alignment(vertical='center')


def _write_header(ws, row: int, headers: list[str]) -> None:
    for i, h in enumerate(headers, start=1):
        cell = ws.cell(row=row, column=i, value=h)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)


def _num_cell(ws, row: int, col: int, value: Optional[Decimal]) -> None:
    if value is None:
        ws.cell(row=row, column=col, value='')
        return
    n = float(value) if isinstance(value, Decimal) else value
    cell = ws.cell(row=row, column=col, value=n)
    cell.number_format = _NUM_FMT
    cell.alignment = Alignment(horizontal='right')


def _pct_cell(ws, row: int, col: int, value: Optional[Decimal]) -> None:
    if value is None:
        ws.cell(row=row, column=col, value='—')
        return
    n = float(value) if isinstance(value, Decimal) else value
    cell = ws.cell(row=row, column=col, value=n)
    cell.number_format = _PCT_FMT
    cell.alignment = Alignment(horizontal='right')
