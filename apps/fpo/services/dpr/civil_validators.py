"""
Validation service for §2.3.14 Building, Civil Works and Physical Infrastructure.

KAU-spec rules:
    Cat A (existing buildings): name required, floor area > 0
    Cat B (proposed buildings): building type required, floor area > 0
    Cat C, D, E: mostly optional / advisory
"""
from typing import Any


def _err(code: str, field: str, message: str) -> dict[str, Any]:
    return {'code': code, 'field': field, 'message': message}


def validate_section(section) -> dict[str, Any]:
    errors: list[dict] = []
    warnings: list[dict] = []

    for i, b in enumerate(section.existing_buildings.all()):
        p = f'existing_buildings[{i}]'
        if not (b.building_name or '').strip():
            errors.append(_err('name_required', f'{p}.building_name', 'Building Name shall be specified.'))
        if b.floor_area is None or b.floor_area <= 0:
            errors.append(_err('floor_area_positive', f'{p}.floor_area', 'Floor Area shall be greater than zero.'))

    for i, b in enumerate(section.proposed_buildings.all()):
        p = f'proposed_buildings[{i}]'
        if not b.building_type_id:
            errors.append(_err('type_required', f'{p}.building_type', 'Building Type shall be specified.'))
        if b.floor_area is None or b.floor_area <= 0:
            errors.append(_err('floor_area_positive', f'{p}.floor_area', 'Floor Area shall be greater than zero.'))

    # Cat D — if basis is "other", basis_of_estimate_other must be filled
    if section.basis_of_estimate == 'other' and not (section.basis_of_estimate_other or '').strip():
        errors.append(_err(
            'basis_other_required', 'basis_of_estimate_other',
            'Please specify — "Others" was selected for cost estimation basis.',
        ))

    return {
        'errors': errors,
        'warnings': warnings,
        'is_complete': len(errors) == 0,
    }
