"""
Validation service for §2.3.4 Proposed Project Investment.

KAU-spec rules:
    - This section is CONDITIONAL — the whole section may be left blank.
    - If `estimated_project_cost` is provided, it shall be > 0.
    - If `estimated_project_cost` is provided, `basis_of_estimate` is recommended
      (warning, not error).
"""
from typing import Any


def _err(code: str, field: str, message: str) -> dict[str, Any]:
    return {'code': code, 'field': field, 'message': message}


def _warn(code: str, field: str, message: str) -> dict[str, Any]:
    return {'code': code, 'field': field, 'message': message}


def validate_section(section) -> dict[str, Any]:
    errors: list[dict] = []
    warnings: list[dict] = []

    if section.estimated_project_cost is not None:
        if section.estimated_project_cost <= 0:
            errors.append(_err(
                'cost_positive', 'estimated_project_cost',
                'Estimated Project Cost shall be greater than zero.',
            ))
        if not section.basis_of_estimate:
            warnings.append(_warn(
                'basis_recommended', 'basis_of_estimate',
                'Basis of Estimate is recommended when a project cost is provided.',
            ))

    return {
        'errors': errors,
        'warnings': warnings,
        'is_complete': len(errors) == 0,
    }
