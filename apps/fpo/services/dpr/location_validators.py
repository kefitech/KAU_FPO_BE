"""
Validation service for §2.3.6 Proposed Project Location.

KAU-spec rules:
    - State, District, Local Body shall be mandatory.
    - Land ownership status shall be specified (≥1 selection).
    - Site status shall be specified (≥1 selection).
    - Project location shall be identified via address OR map coordinates.
    - If an "_other" master row is picked in ownership/site, the companion
      text field must be non-empty.
"""
from typing import Any


def _err(code: str, field: str, message: str) -> dict[str, Any]:
    return {'code': code, 'field': field, 'message': message}


def _warn(code: str, field: str, message: str) -> dict[str, Any]:
    return {'code': code, 'field': field, 'message': message}


def validate_section(section) -> dict[str, Any]:
    errors: list[dict] = []
    warnings: list[dict] = []

    # A. Administrative — mandatory fields
    if not (section.state or '').strip():
        errors.append(_err('state_required', 'state', 'State is required.'))
    if not (section.district or '').strip():
        errors.append(_err('district_required', 'district', 'District is required.'))
    if not (section.local_body_type or '').strip() or not (section.local_body_name or '').strip():
        errors.append(_err(
            'local_body_required', 'local_body_name',
            'Local Body (Grama Panchayat / Municipality / Corporation) is required.',
        ))

    # B. Location — address OR GPS coords
    has_address = bool((section.project_address or '').strip())
    has_coords = section.latitude is not None and section.longitude is not None
    if not has_address and not has_coords:
        errors.append(_err(
            'address_or_gps_required', 'project_address',
            'Project location shall be identified either through address or map selection (lat/long).',
        ))

    # C. Land Ownership
    ownership = list(section.land_ownership_types.all())
    if not ownership:
        errors.append(_err(
            'land_ownership_required', 'land_ownership_types',
            'At least one land ownership type shall be specified.',
        ))
    if any(o.code == 'other' or o.code.endswith('_other') for o in ownership):
        if not (section.land_ownership_other or '').strip():
            errors.append(_err(
                'land_ownership_other_required', 'land_ownership_other',
                'Please specify — "Others" was selected but no description provided.',
            ))

    # D. Site Status
    sites = list(section.site_statuses.all())
    if not sites:
        errors.append(_err(
            'site_status_required', 'site_statuses',
            'At least one site status shall be specified.',
        ))
    if any(s.code == 'other' or s.code.endswith('_other') for s in sites):
        if not (section.site_status_other or '').strip():
            errors.append(_err(
                'site_status_other_required', 'site_status_other',
                'Please specify — "Others" was selected but no description provided.',
            ))

    # E. Accessibility (advisory — mandatory 3 per spec table)
    if section.dist_nearest_main_road_km is None:
        warnings.append(_warn(
            'main_road_dist_missing', 'dist_nearest_main_road_km',
            'Distance to nearest main road is recommended.',
        ))
    if section.dist_nearest_market_km is None:
        warnings.append(_warn(
            'market_dist_missing', 'dist_nearest_market_km',
            'Distance to nearest market is recommended.',
        ))

    # F. Connectivity — road quality
    if not section.road_connectivity:
        warnings.append(_warn(
            'road_connectivity_missing', 'road_connectivity',
            'Road connectivity assessment is recommended.',
        ))

    return {
        'errors': errors,
        'warnings': warnings,
        'is_complete': len(errors) == 0,
    }
