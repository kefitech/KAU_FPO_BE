"""
DPR cross-chain operational consistency checks (Kefitech 2026-09-19 P6.6).

Kefitech's review §3 asked us to cross-check
    production ↔ capacity ↔ raw material ↔ machinery ↔ utilities ↔
    manpower ↔ operating cost ↔ revenue
so a materially incomplete or self-contradictory project plan is caught
before final DPR generation. This module implements the lightweight
heuristic layer of that check.

Numeric consistency (numbers-in-narrative-vs-calc-engine) is a separate
concern handled by `consistency_check.py`. This module is about the
structural / operational chain — e.g. "the FPO claims ₹5 Cr revenue but
has zero machinery entered".

Design intent: catch the OBVIOUS holes without pretending to validate
the FPO's engineering judgment. Every check has a plainly-worded reason
so the FPO knows exactly what section to revisit. Errors block a final
PDF render (via `apps.fpo.services.dpr.pdf._pre_final_validation`);
warnings are advisory.

Author: Athul Gopan (Kefi Tech Solutions)
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


# Below this threshold we don't run the heuristic checks — an early-stage
# draft with a small planned turnover is expected to have gaps. Above,
# the FPO's plan is meaningful enough that structural holes are real
# problems for the reviewing banker.
_TURNOVER_MEANINGFUL_THRESHOLD = Decimal('1000000')  # ₹ 10 Lakh Y1 revenue


@dataclass
class ChainWarning:
    """One cross-chain consistency finding.
    `severity` ∈ {'error', 'warning'} — error blocks a final PDF render;
                warning is advisory and shows on the admin AI health
                surface but does not gate rendering.
    `section` — human-readable section name where the FPO should look.
    `message` — plain-language description of the gap."""
    section: str
    check: str
    severity: str
    message: str


def _decimal_or_zero(v) -> Decimal:
    if v is None:
        return Decimal('0')
    if isinstance(v, Decimal):
        return v
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal('0')


def _y1_revenue(project) -> Decimal:
    """Y1 revenue from the calc engine (already validated). Falls back to
    zero if the project doesn't have revenue assumptions yet."""
    fin = getattr(project, 'section_finance', None)
    if fin is None:
        return Decimal('0')
    total = Decimal('0')
    for ra in fin.revenue_assumptions.all():
        if ra.annual_sales_revenue:
            total += _decimal_or_zero(ra.annual_sales_revenue)
        else:
            total += _decimal_or_zero(ra.year1_sales_quantity) * _decimal_or_zero(ra.expected_selling_price)
    return total


def _section_has_rows(project, related_manager_name: str) -> bool:
    """True if `project.<section>.<related_manager>` has at least one row.
    Handles missing section rows (returns False without raising)."""
    for section_attr in (
        'section_products', 'section_raw_material', 'section_machinery',
        'section_hr', 'section_utilities', 'section_market',
    ):
        section = getattr(project, section_attr, None)
        if section is None:
            continue
        mgr = getattr(section, related_manager_name, None)
        if mgr is not None:
            try:
                if mgr.exists():
                    return True
            except Exception:
                pass
    return False


def _sum_opex_bucket(project, fields: tuple[str, ...]) -> Decimal:
    fin = getattr(project, 'section_finance', None)
    if fin is None:
        return Decimal('0')
    total = Decimal('0')
    for f in fields:
        total += _decimal_or_zero(getattr(fin, f, None))
    return total


def check_operational_chain(project) -> list[ChainWarning]:
    """Run the heuristic chain checks against `project`.

    Returns a list of ChainWarning entries. Empty list = project chain
    looks internally consistent (given our heuristics). NEVER raises —
    callers safe to iterate the result unconditionally.
    """
    warnings: list[ChainWarning] = []
    revenue = _y1_revenue(project)

    # Skip the whole battery for early-stage drafts — most fields aren't
    # filled yet, and reporting 10 warnings on a draft is noise not signal.
    if revenue < _TURNOVER_MEANINGFUL_THRESHOLD:
        return warnings

    # ── Products & Services ↔ Revenue ──────────────────────────────────
    products_present = _section_has_rows(project, 'products')
    if not products_present:
        warnings.append(ChainWarning(
            section='Products & Services (§2.3.5)',
            check='products_vs_revenue',
            severity='error',
            message=(
                f'Y1 revenue is ₹{revenue:.0f} but no products have been '
                'added. The DPR needs at least one product/service row so '
                'the revenue projection has a source.'
            ),
        ))

    # ── Raw Material ↔ Production ──────────────────────────────────────
    raw_material_present = _section_has_rows(project, 'raw_materials')
    op_raw_material = _sum_opex_bucket(project, ('op_raw_material',))
    if not raw_material_present:
        warnings.append(ChainWarning(
            section='Raw Material Assessment (§2.3.10)',
            check='raw_material_vs_production',
            severity='error',
            message=(
                f'Y1 revenue is ₹{revenue:.0f} but no raw material items '
                'have been entered. Add the primary raw material(s) with '
                'annual requirement + procurement source so the operating '
                'cost has a basis.'
            ),
        ))
    elif op_raw_material == 0:
        warnings.append(ChainWarning(
            section='Finance §Cat J (Operating Costs)',
            check='raw_material_opex_missing',
            severity='error',
            message=(
                'Raw material line items exist but Y1 raw-material operating '
                'cost (op_raw_material) is ₹0. Bankers will flag this — '
                'enter the Y1 raw-material spend on the Finance section.'
            ),
        ))

    # ── Machinery ↔ Capacity ────────────────────────────────────────────
    machinery_present = _section_has_rows(project, 'items')  # section_machinery.items
    if not machinery_present:
        warnings.append(ChainWarning(
            section='Plant & Machinery (§2.3.15)',
            check='machinery_vs_production',
            severity='error',
            message=(
                f'Y1 revenue is ₹{revenue:.0f} but no plant & machinery '
                'items have been entered. Add at least the primary '
                'processing / storage machines with their rated capacity.'
            ),
        ))

    # ── Manpower ↔ Production ──────────────────────────────────────────
    hr_present = _section_has_rows(project, 'employee_categories')
    if not hr_present:
        warnings.append(ChainWarning(
            section='Human Resources (§2.3.17)',
            check='manpower_vs_production',
            severity='warning',
            message=(
                'No employee categories have been added. At the planned '
                f'Y1 revenue of ₹{revenue:.0f} the DPR should show at '
                'minimum the CEO / operations lead / operators. Bankers '
                'expect a manpower plan.'
            ),
        ))

    # ── Utilities ↔ Production ──────────────────────────────────────────
    utilities_opex = _sum_opex_bucket(
        project, ('op_electricity', 'op_water', 'op_fuel')
    )
    if utilities_opex == 0:
        warnings.append(ChainWarning(
            section='Finance §Cat J (Utilities Opex)',
            check='utilities_vs_production',
            severity='warning',
            message=(
                f'At Y1 revenue ₹{revenue:.0f} utilities (electricity + '
                'water + fuel) opex is ₹0. Almost every processing / '
                'storage project incurs at least some utility cost — '
                'confirm this is intentional.'
            ),
        ))

    # ── Salaries ↔ Manpower ────────────────────────────────────────────
    salaries_opex = _sum_opex_bucket(project, ('op_salaries_wages',))
    if hr_present and salaries_opex == 0:
        warnings.append(ChainWarning(
            section='Finance §Cat J (Salaries)',
            check='salaries_vs_manpower',
            severity='warning',
            message=(
                'Employee categories have been added but the Y1 salaries '
                '& wages opex is ₹0. Enter the Y1 payroll cost on the '
                'Finance section so it flows into the P&L.'
            ),
        ))

    return warnings
