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

    return {
        'errors': errors,
        'warnings': warnings,
        'is_complete': len(errors) == 0,
    }
