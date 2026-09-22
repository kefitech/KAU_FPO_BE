"""
Validation service for §2.3.15 Plant, Machinery and Equipment.

KAU-spec rules:
    Cat A: name required, quantity > 0, must link to project_component
    Cat B: if rated_capacity provided → capacity_unit required
    Cat D: unit_cost > 0 where provided
    Cat F: useful_life_years > 0 if entered
"""
from typing import Any


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

    return {
        'errors': errors,
        'warnings': warnings,
        'is_complete': len(errors) == 0,
    }
