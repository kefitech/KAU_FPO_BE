"""
Validation service for §2.3.19 Statutory Approvals, Licences and Regulatory Compliance.

KAU-spec rules:
    - FPO / Producer Company Registration shall be specified (Cat A mandatory).
    - Each compliance item must have EITHER registration FK OR custom_name (not both blank).
    - Each item must have status.
    - Cat G: if has_pending_legal_issues=True → nature_of_case + possible_impact required.
"""
from typing import Any


def _err(code: str, field: str, message: str) -> dict[str, Any]:
    return {'code': code, 'field': field, 'message': message}


def validate_section(section) -> dict[str, Any]:
    errors: list[dict] = []
    warnings: list[dict] = []

    items = list(section.items.select_related('registration'))

    # FPO registration mandatory (Cat A rule)
    has_fpo_reg = any(
        i.registration and i.registration.code == 'fpo_registration'
        for i in items
    )
    if not has_fpo_reg:
        errors.append(_err(
            'fpo_registration_required', 'items',
            'FPO / Producer Company Registration shall be specified.',
        ))

    for i, item in enumerate(items):
        p = f'items[{i}]'
        # Must have either FK or custom name
        if not item.registration_id and not (item.custom_name or '').strip():
            errors.append(_err(
                'name_required', f'{p}.registration',
                'Each compliance item must have either a registration or a custom name.',
            ))
        if not item.status:
            errors.append(_err('status_required', f'{p}.status', 'Status is required.'))

    # Cat G
    if section.has_pending_legal_issues:
        if not (section.nature_of_case or '').strip():
            errors.append(_err(
                'nature_required', 'nature_of_case',
                'Nature of Case is required when pending legal issues are declared.',
            ))
        if not (section.possible_impact or '').strip():
            errors.append(_err(
                'impact_required', 'possible_impact',
                'Possible Impact on Project is required when pending legal issues are declared.',
            ))

    return {
        'errors': errors,
        'warnings': warnings,
        'is_complete': len(errors) == 0,
    }
