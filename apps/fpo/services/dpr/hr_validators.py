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
        # Wages feed the Salaries line of Operating Cost → EBITDA → DSCR.
        # Silent-blank pattern (ChatGPT calc audit 2026-09-22) — at least
        # one of monthly_salary or annual_salary must be > 0 per role, or
        # the salary line silently drops.
        ms = e.monthly_salary
        yr = e.annual_salary
        has_ms = ms is not None and ms > 0
        has_yr = yr is not None and yr > 0
        if not has_ms and not has_yr:
            errors.append(_err(
                'salary_required', f'{p}.monthly_salary',
                'Monthly salary (or Annual salary) is required and shall be greater than zero.',
            ))

    # Cat C — "other" specify text
    for i, d in enumerate(section.departments.all()):
        if d.department == 'other' and not (d.department_other or '').strip():
            errors.append(_err(
                'department_other_required', f'departments[{i}].department_other',
                'Please specify — "Others" was selected for department.',
            ))

    # Cat D — existing employees: each subgroup (technical / admin / marketing
    # / skilled operators) must be ≤ the reported total, AND the SUM of all
    # four subgroups must be ≤ the reported total.
    if section.has_existing_employees:
        total = section.existing_employees_total
        if total is not None:
            subs = (
                ('existing_technical_staff', 'Technical Staff'),
                ('existing_administrative_staff', 'Admin Staff'),
                ('existing_marketing_staff', 'Marketing Staff'),
                ('existing_skilled_operators', 'Skilled Operators'),
            )
            for key, label in subs:
                val = getattr(section, key, None)
                if val is not None and val > total:
                    errors.append(_err(
                        'subgroup_exceeds_total', key,
                        f'{label} cannot be greater than Existing Employees ({total}).',
                    ))
            sub_sum = sum((getattr(section, k, None) or 0) for k, _ in subs)
            if sub_sum > total:
                errors.append(_err(
                    'subgroup_sum_exceeds_total', 'existing_employees_total',
                    (
                        f'The total number of employees in all sub-categories '
                        f'({sub_sum:,}) cannot exceed Existing Employees ({total:,}).'
                    ),
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
