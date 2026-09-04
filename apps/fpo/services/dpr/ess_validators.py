"""
Validation service for §2.3.20 Environmental, Social and Sustainability Assessment.

Most fields advisory; enforce "Others (Specify)" text when picked and per-item mitigation for climate risks.
"""
from typing import Any


def _err(code: str, field: str, message: str) -> dict[str, Any]:
    return {'code': code, 'field': field, 'message': message}


def _warn(code: str, field: str, message: str) -> dict[str, Any]:
    return {'code': code, 'field': field, 'message': message}


def validate_section(section) -> dict[str, Any]:
    errors: list[dict] = []
    warnings: list[dict] = []

    # "Others" specify text
    if 'other' in (section.conservation_measures or []) and not (section.conservation_other or '').strip():
        errors.append(_err('conservation_other_required', 'conservation_other', 'Please specify — "Others" in conservation measures.'))
    if 'other' in (section.safety_measures or []) and not (section.safety_other or '').strip():
        errors.append(_err('safety_other_required', 'safety_other', 'Please specify — "Others" in safety measures.'))
    if 'other' in (section.sustainability_initiatives or []) and not (section.sustainability_other or '').strip():
        errors.append(_err('sustainability_other_required', 'sustainability_other', 'Please specify — "Others" in sustainability initiatives.'))

    # Environmental impact "other" text per row
    for i, imp in enumerate(section.environmental_impacts.select_related('impact')):
        if imp.impact.code == 'other' and not (imp.impact_other or '').strip():
            errors.append(_err(
                'impact_other_required', f'environmental_impacts[{i}].impact_other',
                'Please specify — "Others" was selected for environmental impact.',
            ))

    # Climate risk "other" text per row + mitigation strongly recommended
    for i, risk in enumerate(section.climate_risks.select_related('risk')):
        p = f'climate_risks[{i}]'
        if risk.risk.code == 'other' and not (risk.risk_other or '').strip():
            errors.append(_err(
                'risk_other_required', f'{p}.risk_other',
                'Please specify — "Others" was selected for climate risk.',
            ))
        if not (risk.proposed_mitigation_strategy or '').strip():
            warnings.append(_warn(
                'mitigation_recommended', f'{p}.proposed_mitigation_strategy',
                'Proposed Mitigation Strategy is recommended for each selected climate risk.',
            ))

    return {
        'errors': errors,
        'warnings': warnings,
        'is_complete': len(errors) == 0,
    }
