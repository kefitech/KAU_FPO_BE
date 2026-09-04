"""
Validation service for §2.3.17 Human Resources and Organisational Structure.

KAU-spec rules:
    Cat A: operational_management_model required
    Cat B: number_required > 0 per employee category (spec: "shall be greater than zero")
    Cat A/G/H "Others" specify text
"""
from typing import Any


def _err(code: str, field: str, message: str) -> dict[str, Any]:
    return {'code': code, 'field': field, 'message': message}


def validate_section(section) -> dict[str, Any]:
    errors: list[dict] = []
    warnings: list[dict] = []

    # Cat A
    if not section.operational_management_model:
        errors.append(_err(
            'management_model_required', 'operational_management_model',
            'Operational Management Model shall be specified.',
        ))
    if section.operational_management_model == 'other' and not (section.operational_management_other or '').strip():
        errors.append(_err(
            'management_other_required', 'operational_management_other',
            'Please specify — "Others" was selected for management model.',
        ))

    # Cat B
    for i, e in enumerate(section.employee_categories.all()):
        p = f'employee_categories[{i}]'
        if not (e.designation or '').strip():
            errors.append(_err('designation_required', f'{p}.designation', 'Designation is required.'))
        if e.number_required is None or e.number_required <= 0:
            errors.append(_err(
                'number_positive', f'{p}.number_required',
                'Number of employees shall be greater than zero.',
            ))

    # Cat C — "other" specify text
    for i, d in enumerate(section.departments.all()):
        if d.department == 'other' and not (d.department_other or '').strip():
            errors.append(_err(
                'department_other_required', f'departments[{i}].department_other',
                'Please specify — "Others" was selected for department.',
            ))

    # Cat G/H "Others" specify text
    if 'other' in (section.welfare_items or []) and not (section.welfare_other or '').strip():
        errors.append(_err('welfare_other_required', 'welfare_other', 'Please specify — "Others" in employee welfare.'))
    if 'other' in (section.statutory_compliance or []) and not (section.statutory_compliance_other or '').strip():
        errors.append(_err('statutory_other_required', 'statutory_compliance_other', 'Please specify — "Others" in statutory compliance.'))

    return {
        'errors': errors,
        'warnings': warnings,
        'is_complete': len(errors) == 0,
    }
