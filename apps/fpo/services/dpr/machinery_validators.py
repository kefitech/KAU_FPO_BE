"""
Validation service for §2.3.15 Plant, Machinery and Equipment.

KAU-spec rules:
    Cat A: name required, quantity > 0, must link to project_component
    Cat B: if rated_capacity provided → capacity_unit required
    Cat D: unit_cost > 0 where provided
    Cat F: useful_life_years > 0 if entered
"""
import re
from decimal import Decimal
from typing import Any

# KAU contradiction review 2026-10-08 (Pattern 5): machinery NAMES often
# embed a capacity ("2 TPH husk-fired boiler") that contradicts the
# rated_capacity field (500 kg/h). Extract any <number><unit> token from
# the name and compare, converting between mass-per-hour units.
_NAME_CAPACITY_RE = re.compile(
    r'(\d+(?:\.\d+)?)\s*(tph|t/h|tonnes?\s*(?:/|per)\s*h(?:ou)?r|'
    r'kg\s*(?:/|per)\s*h(?:ou)?r|kg/h|kgph|lph|l/h|litres?\s*(?:/|per)\s*h(?:ou)?r)',
    re.IGNORECASE,
)
# Normalise to kg/h (mass) or l/h (volume) so cross-unit names compare.
_UNIT_TO_KG_H = {'tph': 1000, 't/h': 1000, 'kg/h': 1, 'kgph': 1}
_UNIT_CODE_TO_KG_H = {'kg': 1, 'quintal': 100, 'mt': 1000, 'tonnes': 1000}


def _err(code: str, field: str, message: str) -> dict[str, Any]:
    return {'code': code, 'field': field, 'message': message}


def _warn(code: str, field: str, message: str) -> dict[str, Any]:
    return {'code': code, 'field': field, 'message': message}


def validate_section(section) -> dict[str, Any]:
    errors: list[dict] = []
    warnings: list[dict] = []

    items = list(section.items.all())

    for i, it in enumerate(items):
        p = f'items[{i}]'
        if not (it.name or '').strip():
            errors.append(_err('name_required', f'{p}.name', 'Machinery name is required.'))
        if it.quantity_required is None or it.quantity_required <= 0:
            errors.append(_err(
                'quantity_positive', f'{p}.quantity_required',
                'Quantity shall be greater than zero.',
            ))
        if not it.project_component_id:
            errors.append(_err(
                'component_required', f'{p}.project_component',
                'Every machinery item shall be linked to a project component.',
            ))
        if it.rated_capacity is not None and it.rated_capacity > 0 and not it.capacity_unit_id:
            errors.append(_err(
                'capacity_unit_required', f'{p}.capacity_unit',
                'Capacity Unit shall be specified when machinery capacity is entered.',
            ))
        # Unit cost + useful life MUST be present for every machinery row —
        # depreciation, Fixed Capital Investment, Means of Finance, DSCR and
        # payback all pull from these two numbers. Silently allowing blanks
        # produced under-costed project totals + inflated ratios (root of the
        # ChatGPT-flagged calculation issues, 2026-09-22).
        if it.unit_cost is None or it.unit_cost <= 0:
            errors.append(_err(
                'cost_required', f'{p}.unit_cost',
                'Unit Cost is required and shall be greater than zero.',
            ))
        if it.useful_life_years is None or it.useful_life_years <= 0:
            errors.append(_err(
                'life_required', f'{p}.useful_life_years',
                'Useful Life is required and shall be greater than zero.',
            ))
        if it.machine_category_id is None:
            warnings.append(_warn(
                'category_recommended', f'{p}.machine_category',
                'Machine Category is recommended for depreciation defaults and better AI output.',
            ))

    # Cat G: if "other" statutory approval, need remarks
    if 'other' in (section.statutory_approvals or []) and not (section.statutory_approvals_other or '').strip():
        errors.append(_err(
            'statutory_other_required', 'statutory_approvals_other',
            'Please specify — "Others" was selected in statutory approvals.',
        ))

    for i, s in enumerate(section.supporting_assets.all()):
        p = f'supporting_assets[{i}]'
        if s.quantity is None or s.quantity <= 0:
            errors.append(_err('sa_quantity_positive', f'{p}.quantity', 'Supporting asset quantity shall be greater than zero.'))
        # Same silent-blank pattern as machinery unit_cost — supporting
        # asset costs also feed Fixed Capital Investment. A missing value
        # silently drops the asset from project cost totals.
        if s.estimated_cost is None or s.estimated_cost <= 0:
            errors.append(_err(
                'sa_cost_required', f'{p}.estimated_cost',
                'Estimated Cost is required and shall be greater than zero.',
            ))

    # KAU review 2026-10-08 Pattern 5 — name-embedded capacity vs the
    # rated_capacity field ("2 TPH boiler" rated 500 kg/h appeared in four
    # sample DPRs). Both sides normalised to kg/h; warn on >25% divergence.
    for i, it in enumerate(items):
        name = (it.name or '')
        m = _NAME_CAPACITY_RE.search(name)
        if not m or it.rated_capacity is None or it.rated_capacity <= 0:
            continue
        unit_raw = re.sub(r'\s+', '', m.group(2).lower())
        unit_raw = (unit_raw
                    .replace('tonnesperhour', 'tph').replace('tonneperhour', 'tph')
                    .replace('tonnes/hour', 'tph').replace('tonne/hour', 'tph')
                    .replace('tonnes/hr', 'tph').replace('tonne/hr', 'tph')
                    .replace('kgperhour', 'kg/h').replace('kg/hour', 'kg/h').replace('kg/hr', 'kg/h'))
        factor = _UNIT_TO_KG_H.get(unit_raw)
        if factor is None:
            continue  # volume/unknown unit — skip rather than guess
        name_kg_h = Decimal(m.group(1)) * factor
        unit_code = getattr(it.capacity_unit, 'code', '') if it.capacity_unit_id else ''
        rated_factor = _UNIT_CODE_TO_KG_H.get(unit_code)
        if rated_factor is None:
            continue
        rated_kg_h = Decimal(str(it.rated_capacity)) * rated_factor
        if rated_kg_h <= 0:
            continue
        divergence = abs(name_kg_h - rated_kg_h) / rated_kg_h
        if divergence > Decimal('0.25'):
            warnings.append(_warn(
                'name_capacity_mismatch', f'items[{i}].rated_capacity',
                f'The machine name says "{m.group(0)}" (≈{name_kg_h:,.0f} kg/h) '
                f'but the Rated Capacity field says {it.rated_capacity:,.0f} '
                f'{unit_code or "?"} (≈{rated_kg_h:,.0f} kg/h). A bank reviewer '
                f'will flag the contradiction — correct the name or the rating '
                f'(e.g. "husk-fired steam boiler, 500 kg/h").',
            ))

    return {
        'errors': errors,
        'warnings': warnings,
        'is_complete': len(errors) == 0,
    }
