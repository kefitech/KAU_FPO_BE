"""
Validation service for §2.3.7 Project Rationale.

KAU-spec rules:
    - At least one reason shall be selected.
    - A brief justification shall be provided for each selected reason.
    - Justification shall not exceed 100 words.
    - If the "other" master rationale is selected, `rationale_other` text required.
"""
from typing import Any


MAX_WORDS_PER_JUSTIFICATION = 100


def _err(code: str, field: str, message: str) -> dict[str, Any]:
    return {'code': code, 'field': field, 'message': message}


def _wc(text: str) -> int:
    return len((text or '').split())


def validate_section(section) -> dict[str, Any]:
    errors: list[dict] = []
    warnings: list[dict] = []

    selections = list(section.selections.select_related('rationale'))

    if not selections:
        errors.append(_err(
            'at_least_one_rationale', 'selections',
            'At least one reason shall be selected.',
        ))

    for i, sel in enumerate(selections):
        prefix = f'selections[{i}]'
        just = (sel.justification or '').strip()
        if not just:
            errors.append(_err(
                'justification_required', f'{prefix}.justification',
                f'Justification is required for "{sel.rationale.label_en}".',
            ))
        elif _wc(just) > MAX_WORDS_PER_JUSTIFICATION:
            errors.append(_err(
                'justification_too_long', f'{prefix}.justification',
                f'Justification for "{sel.rationale.label_en}" exceeds {MAX_WORDS_PER_JUSTIFICATION} words ({_wc(just)} words).',
            ))

    # "Others (Specify)" text
    has_other = any(sel.rationale.code == 'other' for sel in selections)
    if has_other and not (section.rationale_other or '').strip():
        errors.append(_err(
            'rationale_other_required', 'rationale_other',
            'Please specify — "Others" was selected but no description provided.',
        ))

    return {
        'errors': errors,
        'warnings': warnings,
        'is_complete': len(errors) == 0,
    }
