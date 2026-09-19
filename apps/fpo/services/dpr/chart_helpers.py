"""
DPR PDF charts — matplotlib → PNG → base64.

Returned as `data:image/png;base64,...` strings so the template can drop them
straight into `<img src="{{ chart }}">` — no filesystem writes, no path
issues with WeasyPrint, works identically local / dev / prod.

Public helpers:
    * `cost_breakdown_pie(cost_by_field)`  — donut of cost heads
    * `pnl_trend_bar(profit_loss_rows)`    — revenue vs opex vs PAT per year
    * `repayment_schedule_bar(interest_rows)` — principal vs interest per year

All helpers return `''` (empty string) when there's no data to plot — the
template guards with `{% if chart_url %}` and omits the section entirely.
Never raises; a chart failure never blocks PDF generation.
"""
from __future__ import annotations

import base64
import io
import logging
from decimal import Decimal
from typing import Iterable

import matplotlib
# 'Agg' backend — headless, no display server. Must be set BEFORE importing pyplot.
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402


log = logging.getLogger(__name__)


# KAU-brand palette — kept close to the PDF template's blues/oranges so
# charts don't clash with the surrounding table + heading colours.
KAU_NAVY   = '#1F3864'
KAU_ORANGE = '#E86C1A'
_PIE_COLOURS = [
    '#1F3864', '#E86C1A', '#2E7D32', '#8E24AA', '#00838F',
    '#5D4037', '#455A64', '#C62828', '#6A1B9A', '#33691E',
    '#B08D57', '#37474F',
]


def _fig_to_data_url(fig, dpi: int = 130) -> str:
    """Serialise a Matplotlib figure to a base64 data URL, close it, return.

    Closing the figure is mandatory — matplotlib leaks memory across many
    render calls otherwise (each PDF regeneration would grow the process).
    """
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    b64 = base64.b64encode(buf.getvalue()).decode('ascii')
    return f'data:image/png;base64,{b64}'


# Human-readable labels for cost head keys — mirrors COST_LABELS in pdf.py.
# Kept as a small local copy so this module can be imported without pulling
# in pdf.py (avoids circular imports).
_COST_LABEL_SHORT = {
    'cost_land_purchase':               'Land',
    'cost_land_development':            'Land dev.',
    'cost_civil_works':                 'Civil works',
    'cost_buildings':                   'Buildings',
    'cost_plant_machinery':             'Plant & machinery',
    'cost_equipment':                   'Equipment',
    'cost_utilities':                   'Utilities',
    'cost_other_capex':                 'Other capex',
    'cost_site_development':            'Site dev.',
    'cost_furniture_fixtures':          'Furniture',
    'cost_office_equipment':            'Office equip.',
    'cost_vehicles':                    'Vehicles',
    'cost_electrification':             'Electrification',
    'cost_water_supply':                'Water supply',
    'cost_pre_operative_expenses':      'Pre-operative',
    'cost_preliminary_expenses':        'Preliminary',
    'cost_technical_consultancy':       'Consultancy',
    'cost_contingencies':               'Contingencies',
    'cost_margin_for_working_capital':  'WC margin',
    'cost_interest_during_construction':'IDC',
}


def cost_breakdown_pie(cost_by_field: dict) -> str:
    """Donut chart of non-zero cost heads. Returns '' when nothing to plot.

    KAU 2026-09-19 P4.2 revision — the previous version put labels
    directly beside the wedges, which crowded and overlapped once a
    project had 6+ cost heads. New layout:

      * Larger canvas (7.5 x 4.5in) so wedges are readable at PDF zoom.
      * Percentages sit inside each wedge; wedge-side labels removed.
      * A dedicated legend on the right lists each slice with its label,
        ₹ amount (Indian-comma), and % share.
      * Tiny slices < 3% still fold into 'Other' so the donut stays clean.

    Matches the IIFPT reference DPR (Figure 5) legibility bar.
    """
    try:
        # Convert Decimals → floats; drop zero / negative / null rows.
        items = [
            (_COST_LABEL_SHORT.get(k, k), float(v))
            for k, v in (cost_by_field or {}).items()
            if v and float(v) > 0
        ]
        if not items:
            return ''
        total = sum(v for _, v in items)
        if total <= 0:
            return ''

        # Merge tiny slices into 'Other' so labels don't overlap.
        big = [(l, v) for l, v in items if (v / total) >= 0.03]
        small_sum = sum(v for l, v in items if (v / total) < 0.03)
        if small_sum > 0:
            big.append(('Other', small_sum))
        big.sort(key=lambda x: x[1], reverse=True)

        labels = [l for l, _ in big]
        values = [v for _, v in big]
        colours = _PIE_COLOURS[:len(values)]

        # Two-panel layout: donut on the left, legend on the right.
        # gridspec_kw width ratios give the donut most of the canvas.
        fig, (ax, ax_legend) = plt.subplots(
            1, 2, figsize=(7.5, 4.5),
            gridspec_kw={'width_ratios': [3.0, 2.0]},
        )
        wedges, _texts, autotexts = ax.pie(
            values,
            labels=None,  # KAU 2026-09-19: labels moved to side legend
            colors=colours,
            autopct=lambda pct: f'{pct:.1f}%' if pct >= 4 else '',
            startangle=90,
            pctdistance=0.78,
            wedgeprops={'edgecolor': 'white', 'linewidth': 1.5, 'width': 0.42},
            textprops={'fontsize': 10, 'color': '#222'},
        )
        for t in autotexts:
            t.set_color('white')
            t.set_fontweight('bold')
            t.set_fontsize(9)
        ax.set_title(
            'Project Cost Breakdown',
            fontsize=13, color=KAU_NAVY, pad=14, fontweight='bold',
        )

        # Side legend — one entry per slice with label + ₹ value + % share.
        # Rendered via a dummy axis so we can control alignment + fonts
        # independently from the pie's default legend positioning.
        ax_legend.axis('off')
        legend_labels = [
            f'{lbl}  —  ₹ {_fmt_indian(val)}  ({val / total * 100:.1f}%)'
            for lbl, val in big
        ]
        ax_legend.legend(
            handles=wedges,
            labels=legend_labels,
            loc='center left',
            frameon=False,
            fontsize=9,
            labelspacing=1.1,
            handlelength=1.6,
            handleheight=1.1,
            borderaxespad=0,
        )
        fig.tight_layout()
        return _fig_to_data_url(fig)
    except Exception:  # noqa: BLE001 — chart failure must never block PDF
        log.exception('cost_breakdown_pie: chart render failed')
        return ''


def _fmt_indian(v: float) -> str:
    """Indian comma formatting for the pie legend — e.g. 9500000 → 95,00,000.
    Matches the money filter used in report.html so legend + tables agree."""
    s = f'{v:,.0f}'                     # 9,500,000 (US grouping)
    # Convert US grouping to Indian: last 3 digits, then groups of 2.
    negative = s.startswith('-')
    if negative:
        s = s[1:]
    parts = s.split(',')
    if len(parts) <= 1:
        joined = s
    else:
        head = ''.join(parts[:-1])      # drop US commas
        tail = parts[-1]
        pieces = []
        while len(head) > 2:
            pieces.insert(0, head[-2:])
            head = head[:-2]
        if head:
            pieces.insert(0, head)
        joined = ','.join(pieces) + ',' + tail
    return f'-{joined}' if negative else joined


def pnl_trend_bar(profit_loss_rows: Iterable) -> str:
    """Grouped bar chart: revenue vs operating cost vs PAT per year.

    Reads ProfitLossRow dataclass instances (year, revenue, operating_cost,
    pat). Returns '' when no rows or all-zero.
    """
    try:
        rows = list(profit_loss_rows or [])
        if not rows:
            return ''
        years = [f'Y{r.year}' for r in rows]
        revenue = [float(r.revenue) for r in rows]
        opex    = [float(r.operating_cost) for r in rows]
        pat     = [float(r.pat) for r in rows]
        if not any(revenue + opex + pat):
            return ''

        import numpy as np
        x = np.arange(len(years))
        w = 0.28

        fig, ax = plt.subplots(figsize=(8.5, 3.6))
        ax.bar(x - w, revenue, w, label='Revenue',        color=KAU_NAVY)
        ax.bar(x,     opex,    w, label='Operating cost', color='#B0BEC5')
        ax.bar(x + w, pat,     w, label='PAT',            color=KAU_ORANGE)

        ax.set_xticks(x)
        ax.set_xticklabels(years, fontsize=9)
        ax.set_ylabel('₹', fontsize=9)
        ax.set_title('Revenue · Operating Cost · PAT by Year',
                     fontsize=12, color=KAU_NAVY, pad=10, fontweight='bold')
        ax.axhline(0, color='#999', linewidth=0.6)
        ax.legend(loc='upper left', fontsize=8, frameon=False)
        ax.grid(True, axis='y', linestyle='--', alpha=0.35)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        # Format y-axis ticks with comma separators for readability.
        ax.yaxis.set_major_formatter(
            plt.FuncFormatter(lambda v, _: f'{v/1e5:.1f}L' if abs(v) >= 1e5 else f'{int(v):,}')
        )
        return _fig_to_data_url(fig)
    except Exception:  # noqa: BLE001
        log.exception('pnl_trend_bar: chart render failed')
        return ''


def repayment_schedule_bar(interest_rows: Iterable) -> str:
    """Stacked bar: interest + principal per year of loan repayment.

    Reads InterestScheduleRow dataclass instances (year, interest, principal).
    Returns '' when no loan / no rows.
    """
    try:
        rows = list(interest_rows or [])
        if not rows:
            return ''
        years     = [f'Y{r.year}' for r in rows]
        interest  = [float(getattr(r, 'interest', 0) or 0) for r in rows]
        principal = [float(getattr(r, 'principal', 0) or 0) for r in rows]
        if not any(interest + principal):
            return ''

        import numpy as np
        x = np.arange(len(years))

        fig, ax = plt.subplots(figsize=(8.5, 3.6))
        ax.bar(x, interest,  color=KAU_ORANGE, label='Interest')
        ax.bar(x, principal, color=KAU_NAVY,   label='Principal', bottom=interest)

        ax.set_xticks(x)
        ax.set_xticklabels(years, fontsize=9)
        ax.set_ylabel('₹', fontsize=9)
        ax.set_title('Loan Repayment Schedule (Principal + Interest per Year)',
                     fontsize=12, color=KAU_NAVY, pad=10, fontweight='bold')
        ax.legend(loc='upper right', fontsize=8, frameon=False)
        ax.grid(True, axis='y', linestyle='--', alpha=0.35)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.yaxis.set_major_formatter(
            plt.FuncFormatter(lambda v, _: f'{v/1e5:.1f}L' if abs(v) >= 1e5 else f'{int(v):,}')
        )
        return _fig_to_data_url(fig)
    except Exception:  # noqa: BLE001
        log.exception('repayment_schedule_bar: chart render failed')
        return ''
