"""
Validation service for §2.3.16 Utilities and Support Services.

KAU-spec rules:
    Cat A: if electricity_required → supply_type required
    Cat B: if water_required → water_source required
    Cat F: per-waste disposal_method required
"""
from typing import Any


def _err(code: str, field: str, message: str) -> dict[str, Any]:
    return {'code': code, 'field': field, 'message': message}


def validate_section(section) -> dict[str, Any]:
    errors: list[dict] = []
    warnings: list[dict] = []

    # Cat A
    if section.electricity_required and not section.electricity_supply_type:
        errors.append(_err(
            'supply_type_required', 'electricity_supply_type',
            'Type of Supply shall be specified if electricity is required.',
        ))

    # Cat B
    if section.water_required and not section.water_source:
        errors.append(_err(
            'water_source_required', 'water_source',
            'Source of Water shall be specified.',
        ))
    if section.water_source == 'other' and not (section.water_source_other or '').strip():
        errors.append(_err(
            'water_source_other_required', 'water_source_other',
            'Please specify — "Others" was selected for water source.',
        ))

    # Cat F — per-waste disposal method required
    for i, w in enumerate(section.wastes.all()):
        p = f'wastes[{i}]'
        if not (w.disposal_method or '').strip():
            errors.append(_err(
                'disposal_method_required', f'{p}.disposal_method',
                'Disposal method shall be specified for each waste type.',
            ))

    # H/I "other" text
    if 'other' in (section.communication_items or []) and not (section.communication_other or '').strip():
        errors.append(_err('comm_other_required', 'communication_other', 'Please specify — "Others" in communication items.'))
    if 'other' in (section.fire_safety_items or []) and not (section.fire_safety_other or '').strip():
        errors.append(_err('safety_other_required', 'fire_safety_other', 'Please specify — "Others" in fire & safety.'))

    return {
        'errors': errors,
        'warnings': warnings,
        'is_complete': len(errors) == 0,
    }
