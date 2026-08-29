"""
Validation service for §2.3.13 Land, Site Suitability and Infrastructure Readiness.

KAU-spec rules:
    Cat A: land area > 0, ownership specified — enforced per parcel
    Cat B: terrain required
    Cat H: mitigation required per constraint; "_other" needs specify text
"""
from typing import Any


def _err(code: str, field: str, message: str) -> dict[str, Any]:
    return {'code': code, 'field': field, 'message': message}


def _warn(code: str, field: str, message: str) -> dict[str, Any]:
    return {'code': code, 'field': field, 'message': message}


def validate_section(section) -> dict[str, Any]:
    errors: list[dict] = []
    warnings: list[dict] = []

    parcels = list(section.parcels.all())
    constraints = list(section.constraints.all())

    # Cat A — at least one parcel
    if not parcels:
        errors.append(_err(
            'at_least_one_parcel', 'parcels',
            'At least one land parcel shall be specified.',
        ))
    for i, p in enumerate(parcels):
        prefix = f'parcels[{i}]'
        if p.total_land_available is None or p.total_land_available <= 0:
            errors.append(_err(
                'land_area_positive', f'{prefix}.total_land_available',
                'Land area shall be greater than zero.',
            ))
        if not p.ownership_id:
            errors.append(_err(
                'ownership_required', f'{prefix}.ownership',
                'Land ownership status shall be specified.',
            ))
        if p.ownership_id and (p.ownership.code == 'other' or p.ownership.code.endswith('_other')):
            if not (p.ownership_other or '').strip():
                errors.append(_err(
                    'ownership_other_required', f'{prefix}.ownership_other',
                    'Please specify — "Others" was selected for ownership.',
                ))

    # Cat B — terrain
    if not section.terrain:
        errors.append(_err('terrain_required', 'terrain', 'Terrain shall be specified.'))
    if section.terrain == 'other' and not (section.terrain_other or '').strip():
        errors.append(_err(
            'terrain_other_required', 'terrain_other',
            'Please specify — "Others" was selected for terrain.',
        ))

    # Cat H — constraints with mitigation
    for i, c in enumerate(constraints):
        prefix = f'constraints[{i}]'
        if not (c.mitigation_measure or '').strip():
            errors.append(_err(
                'mitigation_required', f'{prefix}.mitigation_measure',
                'Mitigation Measure is required for each site constraint.',
            ))
        if c.constraint_type == 'other' and not (c.constraint_type_other or '').strip():
            errors.append(_err(
                'constraint_other_required', f'{prefix}.constraint_type_other',
                'Please specify — "Others" was selected in constraint type.',
            ))

    return {
        'errors': errors,
        'warnings': warnings,
        'is_complete': len(errors) == 0,
    }
