"""
Validation service for §2.3.22 Risk Assessment and Mitigation Plan.

KAU-spec rules:
    - Every identified risk shall have at least one proposed mitigation measure.
    - "Others" risk_code requires risk_code_other text.
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

    for i, r in enumerate(items):
        p = f'items[{i}]'
        if not (r.mitigation_strategy or '').strip():
            errors.append(_err(
                'mitigation_required', f'{p}.mitigation_strategy',
                'Every identified risk shall have at least one proposed mitigation measure.',
            ))
        if r.risk_code == 'other' and not (r.risk_code_other or '').strip():
            errors.append(_err(
                'risk_other_required', f'{p}.risk_code_other',
                'Please specify — "Others" was selected for risk code.',
            ))

    # Advisory: recommend at least one risk per category (spec suggests categories are exhaustive)
    if not items:
        warnings.append(_warn(
            'no_risks_identified', 'items',
            'No risks identified. Spec expects risks across production, market, financial, institutional, environmental, and regulatory categories.',
        ))

    return {
        'errors': errors,
        'warnings': warnings,
        'is_complete': len(errors) == 0,
    }
