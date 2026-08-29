"""
Validation service for §2.3.3 Nature of Business.

KAU-spec rules:
    - At least one Nature of Business shall be selected.
    - If the master row with code='other' is selected, `nature_other` must be non-empty.
"""
from typing import Any


def _err(code: str, field: str, message: str) -> dict[str, Any]:
    return {'code': code, 'field': field, 'message': message}


def validate_section(section) -> dict[str, Any]:
    errors: list[dict] = []
    warnings: list[dict] = []

    natures = list(section.natures.all())

    if not natures:
        errors.append(_err(
            'at_least_one_nature', 'natures',
            'At least one Nature of Business shall be selected.',
        ))

    # If master row code='other' is picked, nature_other text is required
    has_other = any(n.code == 'other' for n in natures)
    if has_other and not (section.nature_other or '').strip():
        errors.append(_err(
            'nature_other_required', 'nature_other',
            'Please specify — "Others" was selected but no description provided.',
        ))

    return {
        'errors': errors,
        'warnings': warnings,
        'is_complete': len(errors) == 0,
    }
