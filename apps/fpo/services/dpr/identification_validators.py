"""
Validation service for §2.2 Information Category 1 – Project Identification.

KAU-spec rules:
    1. Proposed Project Title      — Mandatory (non-blank)
    2. Project Type                — At least one required
    3. Brief Description           — Mandatory, min 50 characters
    4. Primary Commodity           — Mandatory
    5. Secondary Commodities       — Optional
    6. Project Objectives          — At least one required (M2M OR "_other" text)
    7. Expected Outcomes           — At least one required (M2M OR "_other" text)

Author: Athul Gopan (Kefi Tech Solutions)
"""
from typing import Any


def _err(code: str, field: str, message: str) -> dict[str, Any]:
    return {'code': code, 'field': field, 'message': message}


def validate_project(project) -> dict[str, Any]:
    """Dry-run validation — returns errors/warnings without touching state."""
    errors: list[dict] = []
    warnings: list[dict] = []

    # 1. Project title
    if not (project.title or '').strip():
        errors.append(_err('title_required', 'title', 'Proposed Project Title is required.'))

    # 2. Project types (M2M — need at least one)
    if project.pk and not project.project_types.exists():
        errors.append(_err('project_type_required', 'project_types', 'At least one project type shall be selected.'))

    # 3. Brief description ≥ 50 chars
    desc = (project.brief_description or '').strip()
    if not desc:
        errors.append(_err('description_required', 'brief_description', 'Brief Description of the Project is required.'))
    elif len(desc) < 50:
        errors.append(_err(
            'description_min_length', 'brief_description',
            f'Brief Description shall be at least 50 characters (currently {len(desc)}).',
        ))

    # 4. Primary commodity
    if project.primary_commodity_id is None:
        errors.append(_err('primary_commodity_required', 'primary_commodity', 'Primary Commodity is required.'))

    # 6. Project objectives — at least one M2M row OR non-blank "other".
    # If the "Other" master option is selected, the companion text is required.
    if project.pk:
        objectives = list(project.project_objectives.all())
        other_obj_text = (project.project_objectives_other or '').strip()
        has_obj = bool(objectives) or bool(other_obj_text)
        if not has_obj:
            errors.append(_err(
                'objective_required', 'project_objectives',
                'At least one Project Objective shall be specified.',
            ))
        if any(o.code == 'other' for o in objectives) and not other_obj_text:
            errors.append(_err(
                'objective_other_required', 'project_objectives_other',
                '"Other" objective selected — please specify.',
            ))

    # 7. Expected outcomes — same rules as objectives.
    if project.pk:
        outcomes = list(project.expected_outcomes.all())
        other_out_text = (project.expected_outcomes_other or '').strip()
        has_out = bool(outcomes) or bool(other_out_text)
        if not has_out:
            errors.append(_err(
                'outcome_required', 'expected_outcomes',
                'At least one Expected Outcome shall be specified.',
            ))
        if any(o.code == 'other' for o in outcomes) and not other_out_text:
            errors.append(_err(
                'outcome_other_required', 'expected_outcomes_other',
                '"Other" outcome selected — please specify.',
            ))

    is_complete = len(errors) == 0

    return {
        'errors':      errors,
        'warnings':    warnings,
        'is_complete': is_complete,
    }
