"""
Template filters for the DPR PDF report.

Registered as {% load dpr_filters %} in `apps/fpo/templates/dpr/report.html`.

Author: Athul Gopan (Kefi Tech Solutions)
"""
from decimal import Decimal

from django import template

register = template.Library()


@register.filter
def money(value) -> str:
    """Format a Decimal / number / None as an Indian-style money string.

    Examples:
        None       → '—'
        Decimal(0) → '0'
        1234567    → '12,34,567'
        -50000.5   → '(50,000.50)'  (accounting convention for negatives)
    """
    if value is None or value == '':
        return '—'
    try:
        d = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception:
        return str(value)
    neg = d < 0
    d = abs(d)
    # Split integer + fractional. Show 2 decimals only when non-zero.
    int_part = int(d)
    frac = d - int_part
    int_str = _indian_grouping(int_part)
    if frac > 0:
        frac_str = f'{frac:.2f}'.split('.')[1].rstrip('0')
        out = f'{int_str}.{frac_str}' if frac_str else int_str
    else:
        out = int_str
    return f'({out})' if neg else out


def _indian_grouping(n: int) -> str:
    """Indian comma grouping — 12,34,567 not 1,234,567."""
    s = str(n)
    if len(s) <= 3:
        return s
    last3 = s[-3:]
    rest = s[:-3]
    # Group `rest` in twos from the right
    grouped = []
    while len(rest) > 2:
        grouped.append(rest[-2:])
        rest = rest[:-2]
    if rest:
        grouped.append(rest)
    return ','.join(reversed(grouped)) + ',' + last3


@register.filter
def humanise_field(field_name: str) -> str:
    """`cost_plant_machinery` → `Plant machinery`.
    Prefix stripped (`cost_`, `mof_`, `op_`, `wc_`) so tables stay compact."""
    if not field_name:
        return ''
    s = field_name
    for prefix in ('cost_', 'mof_', 'op_', 'wc_'):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    return s.replace('_', ' ').capitalize()


@register.filter
def compact(value) -> str:
    """Compact Indian money format for wide 10-column tables.

    Trades precision for column width — one cell becomes ~5-8 chars wide
    instead of the 12-16 chars a full `|money` output takes. Used only on
    the wide 10-year projection tables (P&L, cash flow, balance sheet,
    depreciation) so they fit on A4 portrait without truncating columns.

    Rules:
        None or ''       → '—'
        0                → '0'
        |x| < 1e5        → Indian-grouped whole (e.g. 45,000)
        1e5 ≤ |x| < 1e7  → '{n:.2f} L' (lakhs)
        |x| ≥ 1e7        → '{n:.2f} Cr' (crores)
        negatives        → parentheses (accounting convention)
    """
    if value is None or value == '':
        return '—'
    try:
        d = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception:
        return str(value)
    if d == 0:
        return '0'
    neg = d < 0
    d = abs(d)
    if d >= Decimal('10000000'):
        n = d / Decimal('10000000')
        out = f'{n:.2f} Cr'
    elif d >= Decimal('100000'):
        n = d / Decimal('100000')
        out = f'{n:.2f} L'
    else:
        int_part = int(d)
        frac = d - int_part
        int_str = _indian_grouping(int_part)
        if frac > 0:
            frac_str = f'{frac:.2f}'.split('.')[1].rstrip('0')
            out = f'{int_str}.{frac_str}' if frac_str else int_str
        else:
            out = int_str
    return f'({out})' if neg else out


_RISK_LABEL_MAP = {
    'low': 'Low',
    'moderate': 'Moderate',
    'high': 'High',
    'not_assessed': 'Not assessed',
    'no_risks': 'No risks entered',
}
_RISK_BADGE_MAP = {
    'low': 'badge-ok',
    'moderate': 'badge-warn',
    'high': 'badge-err',
    'not_assessed': 'badge-neutral',
    'no_risks': 'badge-neutral',
}


@register.filter
def risk_label(cls: str) -> str:
    """Render a risk class ('low' / 'moderate' / 'high' / 'not_assessed')
    as a human-readable label. 'not_assessed' → 'Not assessed' (DPR-05
    UAT) because `|capfirst` would otherwise render 'Not_assessed'.
    """
    return _RISK_LABEL_MAP.get(cls or '', (cls or '').capitalize())


@register.filter
def risk_badge(cls: str) -> str:
    """Return the CSS badge class for a risk class string. 'not_assessed'
    maps to a neutral grey badge so the reader sees "the risk hasn't been
    scored yet" rather than the implicit green of a bogus Low rating
    (DPR-05 UAT).
    """
    return _RISK_BADGE_MAP.get(cls or '', 'badge-ok')


@register.filter
def last_net_block(rows) -> Decimal:
    """Net block of the final year for an AssetClass. Used in the depreciation
    table to show YN closing net."""
    if not rows:
        return Decimal('0')
    return rows[-1].net_block


@register.filter
def year_total(depreciation, year: int) -> Decimal:
    """Total depreciation across all classes for a given year."""
    return depreciation.total_depreciation_by_year.get(int(year), Decimal('0'))


@register.filter
def enum_display(code, category: str) -> str:
    """Map a raw code value to its human label via the Translation table.

    Usage in the DPR template:
        {{ project.fpo.legal_structure|enum_display:'legal_structure' }}
        → 'Producer Companies Act'  (not 'producer_companies')

    BUG-20 (KAU Section 6): FPO stores several fields as plain CharField
    codes (`producer_companies`, `nabard`, `ceo`) that leaked to the PDF
    and the AI prompt as-is. Resolves via `<category>.<code>` translation
    key, falling back to a title-cased code if the translation is missing.
    """
    from apps.fpo.services.dpr.enum_display import enum_display as _resolve
    return _resolve(category, code)
