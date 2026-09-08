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
