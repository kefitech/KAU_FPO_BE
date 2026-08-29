"""
Validation service for §2.3.8 Current Status (Baseline).

KAU-spec rules:
    - Current status shall be specified (currently_engaged must be set).
    - If Yes → existing_products AND existing_installed_capacity are mandatory.
    - If No → reason_for_proposing is mandatory.
"""
from typing import Any


def _err(code: str, field: str, message: str) -> dict[str, Any]:
    return {'code': code, 'field': field, 'message': message}


def validate_section(section) -> dict[str, Any]:
    errors: list[dict] = []
    warnings: list[dict] = []

    if section.currently_engaged is None:
        errors.append(_err(
            'status_required', 'currently_engaged',
            'Current status shall be specified (Yes/No).',
        ))
        return {'errors': errors, 'warnings': warnings, 'is_complete': False}

    if section.currently_engaged is True:
        if not (section.existing_products or '').strip():
            errors.append(_err(
                'existing_products_required', 'existing_products',
                'Existing Product(s) is required when currently engaged.',
            ))
        if not (section.existing_installed_capacity or '').strip():
            errors.append(_err(
                'existing_capacity_required', 'existing_installed_capacity',
                'Existing Installed Capacity is required when currently engaged.',
            ))
    else:
        if not (section.reason_for_proposing or '').strip():
            errors.append(_err(
                'reason_required', 'reason_for_proposing',
                'Reason for proposing the activity is required when not currently engaged.',
            ))

    return {
        'errors': errors,
        'warnings': warnings,
        'is_complete': len(errors) == 0,
    }
