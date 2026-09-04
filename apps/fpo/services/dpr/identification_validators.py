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

    # 6. Project objectives — at least one M2M row OR non-blank "other"
    if project.pk:
        has_obj = project.project_objectives.exists() or bool((project.project_objectives_other or '').strip())
        if not has_obj:
            errors.append(_err(
                'objective_required', 'project_objectives',
                'At least one Project Objective shall be specified.',
            ))

    # 7. Expected outcomes — at least one M2M row OR non-blank "other"
    if project.pk:
        has_out = project.expected_outcomes.exists() or bool((project.expected_outcomes_other or '').strip())
        if not has_out:
            errors.append(_err(
                'outcome_required', 'expected_outcomes',
                'At least one Expected Outcome shall be specified.',
            ))

    is_complete = len(errors) == 0

    return {
        'errors':      errors,
        'warnings':    warnings,
        'is_complete': is_complete,
    }
