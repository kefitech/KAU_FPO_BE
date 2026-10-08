"""
Validation service for §2.3.9 Project Capacity and Production System.

KAU-spec rules across 5 categories:
    A. Production Capacity: installed_capacity > 0, unit + basis required, utilization 0-100%
    B. Operating Schedule: 1-365 days, 1-3 shifts, 0<hours≤24, 1-12 months
    C. Production Process: description required (≤150 words), type + automation required
    D. Losses: 0-100% for loss and recovery
    E. Expansion: expected_year > current year (if has_future_expansion=True)
"""
from typing import Any
from datetime import date


MAX_PROCESS_DESC_WORDS = 150


def _err(code: str, field: str, message: str) -> dict[str, Any]:
    return {'code': code, 'field': field, 'message': message}


def _wc(text: str) -> int:
    return len((text or '').split())


def _in_range(v, low, high) -> bool:
    return v is not None and low <= v <= high


def validate_section(section) -> dict[str, Any]:
    errors: list[dict] = []
    warnings: list[dict] = []

    # ── A. Production Capacity ──
    if section.installed_capacity is None or section.installed_capacity <= 0:
        errors.append(_err('installed_capacity_positive', 'installed_capacity', 'Installed Capacity shall be greater than zero.'))
    if not section.capacity_unit_id:
        errors.append(_err('capacity_unit_required', 'capacity_unit', 'Capacity Unit shall be specified.'))
    if not section.capacity_basis_id:
        errors.append(_err('capacity_basis_required', 'capacity_basis', 'Capacity Basis shall be specified.'))
    if section.first_year_capacity_utilisation_pct is not None:
        if not _in_range(section.first_year_capacity_utilisation_pct, 0, 100):
            errors.append(_err(
                'utilisation_range', 'first_year_capacity_utilisation_pct',
                'Capacity Utilisation shall be between 0% and 100%.',
            ))

    # ── B. Operating Schedule ──
    if section.working_days_per_year is not None:
        if not _in_range(section.working_days_per_year, 1, 365):
            errors.append(_err('working_days_range', 'working_days_per_year', 'Working Days per Year shall be between 1 and 365.'))
    if section.shifts_per_day is not None:
        if not _in_range(section.shifts_per_day, 1, 3):
            errors.append(_err('shifts_range', 'shifts_per_day', 'Number of Shifts per Day shall be between 1 and 3.'))
    if section.operating_hours_per_shift is not None:
        if not (0 < section.operating_hours_per_shift <= 24):
            errors.append(_err('hours_range', 'operating_hours_per_shift', 'Operating Hours per Shift shall be greater than 0 and not exceed 24.'))
    if section.operating_months_per_year is not None:
        if not _in_range(section.operating_months_per_year, 1, 12):
            errors.append(_err('months_range', 'operating_months_per_year', 'Operating Months per Year shall be between 1 and 12.'))

    # Peak vs Lean overlap — a month is normally either high-production
    # (peak) or low-production (lean), not both. Not spec-mandated, so we
    # emit a WARNING (not error): the FE mutex already prevents accidental
    # overlap, but API tampering / bulk import / legacy rows could still
    # produce this shape. Doesn't block submission — surfaces in the
    # readiness panel's suggestions list.
    peak_set = set(section.peak_production_seasons or [])
    lean_set = set(section.lean_production_seasons or [])
    overlap = peak_set & lean_set
    if overlap:
        # Preserve calendar order for the user-facing message.
        month_order = ('jan', 'feb', 'mar', 'apr', 'may', 'jun',
                       'jul', 'aug', 'sep', 'oct', 'nov', 'dec')
        ordered_overlap = [m.title() for m in month_order if m in overlap]
        warnings.append({
            'code': 'peak_lean_overlap',
            'field': 'peak_production_seasons',
            'message': (
                f'The following month(s) are marked as both peak and lean: '
                f'{", ".join(ordered_overlap)}. '
                'A month is normally either peak (high production) or lean '
                '(low production), not both — review the seasonal breakdown.'
            ),
        })

    # ── C. Production Process ──
    desc = (section.process_description or '').strip()
    if not desc:
        errors.append(_err('process_description_required', 'process_description', 'Production Process Description shall be mandatory.'))
    elif _wc(desc) > MAX_PROCESS_DESC_WORDS:
        errors.append(_err(
            'process_description_too_long', 'process_description',
            f'Production Process Description exceeds {MAX_PROCESS_DESC_WORDS} words ({_wc(desc)} words).',
        ))
    if not section.process_type:
        errors.append(_err('process_type_required', 'process_type', 'Production Process Type shall be selected.'))
    if not section.automation_level:
        errors.append(_err('automation_required', 'automation_level', 'Level of Automation shall be selected.'))

    # ── D. Losses (only when has_production_loss=True) ──
    if section.has_production_loss:
        if section.production_loss_pct is None:
            errors.append(_err('loss_pct_required', 'production_loss_pct', 'Estimated Production Loss (%) is required when losses are expected.'))
        elif not _in_range(section.production_loss_pct, 0, 100):
            errors.append(_err('loss_pct_range', 'production_loss_pct', 'Production Loss shall be between 0% and 100%.'))
        if section.product_recovery_pct is not None and not _in_range(section.product_recovery_pct, 0, 100):
            errors.append(_err('recovery_pct_range', 'product_recovery_pct', 'Product Recovery shall be between 0% and 100%.'))
        if 'other' in (section.loss_sources or []) and not (section.loss_source_other or '').strip():
            errors.append(_err(
                'loss_source_other_required', 'loss_source_other',
                'Please specify — "Others" was selected in loss sources but no description provided.',
            ))

        # Loss + Recovery > 100 is physically impossible — you can't
        # recover more than you put in. Sum < 100 is fine (the rest is
        # by-products / co-outputs which aren't captured on this field).
        # Warning, not error — same tone as the peak/lean overlap check.
        if (section.production_loss_pct is not None
                and section.product_recovery_pct is not None):
            total = section.production_loss_pct + section.product_recovery_pct
            if total > 100:
                warnings.append({
                    'code': 'loss_recovery_over_100',
                    'field': 'product_recovery_pct',
                    'message': (
                        f'Production Loss ({section.production_loss_pct}%) + '
                        f'Product Recovery ({section.product_recovery_pct}%) = '
                        f'{total}%, which exceeds 100%. You cannot recover more '
                        'than the raw material input. Review both values.'
                    ),
                })

    # ── E. Future Expansion (only when has_future_expansion=True) ──
    if section.has_future_expansion:
        if section.expected_year_of_expansion is None:
            errors.append(_err('expansion_year_required', 'expected_year_of_expansion', 'Expected Year of Expansion is required.'))
        else:
            current_year = date.today().year
            if section.expected_year_of_expansion <= current_year:
                errors.append(_err(
                    'expansion_year_future', 'expected_year_of_expansion',
                    f'Expected Year of Expansion shall be later than {current_year}.',
                ))
        if not section.expansion_nature:
            errors.append(_err('expansion_nature_required', 'expansion_nature', 'Nature of Expansion is required.'))
        if section.expansion_nature == 'other' and not (section.expansion_nature_other or '').strip():
            errors.append(_err(
                'expansion_nature_other_required', 'expansion_nature_other',
                'Please specify — "Others" was selected but no description provided.',
            ))

    # KAU contradiction review 2026-10-08 Pattern 4: five of six sample
    # DPRs printed "operating at 80% of rated capacity" while the P&L sold
    # 100% of the listed product capacities from Year 1. Cross-check the
    # declared Y1 utilisation against the Products section quantities
    # (same-unit assumption — skipped when installed capacity is missing).
    try:
        util = section.first_year_capacity_utilisation_pct
        installed = section.installed_capacity
        products = getattr(section.project, 'section_products', None)
        if (util is not None and util < 100 and installed and installed > 0
                and products is not None):
            from decimal import Decimal
            total_qty = Decimal('0')
            for item in products.items.all():
                if item.annual_quantity:
                    total_qty += Decimal(str(item.annual_quantity))
            allowed = Decimal(str(installed)) * Decimal(str(util)) / Decimal('100')
            if total_qty > 0 and total_qty > allowed * Decimal('1.05'):
                implied_pct = (total_qty * Decimal('100') / Decimal(str(installed))).quantize(Decimal('1'))
                warnings.append(_warn(
                    'utilisation_vs_products_mismatch',
                    'first_year_capacity_utilisation_pct',
                    f'Year-1 capacity utilisation is declared as {util}%, but '
                    f'the Products section quantities total {total_qty:,.0f} '
                    f'— {implied_pct}% of the installed capacity '
                    f'({installed:,.0f}). The P&L sells the product '
                    f'quantities, so the narrative\'s "{util}% of rated '
                    f'capacity" will contradict the financials. Align the '
                    f'product quantities with the utilisation (or vice versa).',
                ))
    except Exception:  # noqa: BLE001 — cross-section shape must never break this validator
        pass

    return {
        'errors': errors,
        'warnings': warnings,
        'is_complete': len(errors) == 0,
    }
