"""
Validation service for §2.3.12 Technology Selection and Technical Feasibility.

KAU-spec rules:
    - At least one technology shall be specified.
    - Per technology:
        Cat A: name required, source required, description ≤ 150 words
        Cat B: at least one reason; if "other" reason → reasons_other required;
               selection_justification ≤ 100 words
        Cat C: process_description required, process_type required, automation_level required
        Cat E: if quality_standards_applicable → product_quality_standard required
        Cat F: requires_skilled_operators + requires_training must be set (Yes/No, non-null)
        Cat G: if upgradation_planned → upgradation_year required + must be future
        Cat H: each risk requires non-empty mitigation_measure; "_other" needs risk_type_other text
"""
from typing import Any
from datetime import date


MAX_DESC_WORDS = 150
MAX_JUSTIFICATION_WORDS = 100


def _err(code: str, field: str, message: str) -> dict[str, Any]:
    return {'code': code, 'field': field, 'message': message}


def _wc(text: str) -> int:
    return len((text or '').split())


def validate_section(section) -> dict[str, Any]:
    errors: list[dict] = []
    warnings: list[dict] = []

    techs = list(section.technologies.all().prefetch_related('reasons', 'certifications', 'risks'))

    if not techs:
        errors.append(_err(
            'at_least_one_technology', 'technologies',
            'At least one technology shall be specified.',
        ))

    current_year = date.today().year

    for i, t in enumerate(techs):
        p = f'technologies[{i}]'

        # Cat A
        if not (t.name or '').strip():
            errors.append(_err('name_required', f'{p}.name', 'Technology Name shall be specified.'))
        if not (t.source or '').strip():
            errors.append(_err('source_required', f'{p}.source', 'Source of Technology shall be specified.'))
        if _wc(t.description) > MAX_DESC_WORDS:
            errors.append(_err(
                'description_too_long', f'{p}.description',
                f'Description exceeds {MAX_DESC_WORDS} words ({_wc(t.description)} words).',
            ))
        if t.technology_status == 'other' and not (t.technology_status_other or '').strip():
            errors.append(_err(
                'status_other_required', f'{p}.technology_status_other',
                'Please specify — "Others" was selected for technology status.',
            ))

        # Cat B
        reasons = list(t.reasons.all())
        if not reasons:
            errors.append(_err(
                'reason_required', f'{p}.reasons',
                'At least one reason for selecting the technology shall be selected.',
            ))
        if any(r.code == 'other' for r in reasons) and not (t.reasons_other or '').strip():
            errors.append(_err(
                'reasons_other_required', f'{p}.reasons_other',
                'Please specify — "Others" was selected in reasons.',
            ))
        if _wc(t.selection_justification) > MAX_JUSTIFICATION_WORDS:
            errors.append(_err(
                'justification_too_long', f'{p}.selection_justification',
                f'Justification exceeds {MAX_JUSTIFICATION_WORDS} words ({_wc(t.selection_justification)} words).',
            ))

        # Cat C
        if not (t.process_description or '').strip():
            errors.append(_err('process_description_required', f'{p}.process_description', 'Brief Process Description shall be mandatory.'))
        if not t.process_type:
            errors.append(_err('process_type_required', f'{p}.process_type', 'Process Type shall be selected.'))
        if not t.automation_level:
            errors.append(_err('automation_required', f'{p}.automation_level', 'Level of Automation shall be selected.'))

        # Cat E
        if t.quality_standards_applicable and not (t.product_quality_standard or '').strip():
            errors.append(_err(
                'quality_standard_required', f'{p}.product_quality_standard',
                'Product Quality Standard is required when quality standards are applicable.',
            ))

        # Cat F — Yes/No (non-null) required
        if t.requires_skilled_operators is None:
            errors.append(_err('skilled_operators_required', f'{p}.requires_skilled_operators', 'Requirement of Skilled Operators (Yes/No) is required.'))
        if t.requires_training is None:
            errors.append(_err('training_required', f'{p}.requires_training', 'Requirement of Training (Yes/No) is required.'))

        # Cat G
        if t.upgradation_planned:
            if t.upgradation_year is None:
                errors.append(_err('upgradation_year_required', f'{p}.upgradation_year', 'Upgradation Year is required when upgradation is planned.'))
            elif t.upgradation_year <= current_year:
                errors.append(_err(
                    'upgradation_year_future', f'{p}.upgradation_year',
                    f'Upgradation Year shall be later than {current_year}.',
                ))

        # Cat H — risks
        for j, risk in enumerate(t.risks.all()):
            rp = f'{p}.risks[{j}]'
            if not (risk.mitigation_measure or '').strip():
                errors.append(_err(
                    'mitigation_required', f'{rp}.mitigation_measure',
                    'Mitigation Measure is required for each selected risk.',
                ))
            if risk.risk_type == 'other' and not (risk.risk_type_other or '').strip():
                errors.append(_err(
                    'risk_other_required', f'{rp}.risk_type_other',
                    'Please specify — "Others" was selected in risk type.',
                ))

    return {
        'errors': errors,
        'warnings': warnings,
        'is_complete': len(errors) == 0,
    }
