"""
Validation service for §2.3.2 Project Components.

KAU-spec rules:
    - At least one project component shall be selected.
    - If an "Others (Specify)" component is picked in a group, the corresponding
      other_<group> text field must be non-empty.

Returns {'errors': [...], 'warnings': [...], 'is_complete': bool}
"""
from typing import Any


# Map each "_other" component code → the section field that captures its "specify" text
_OTHER_CODE_TO_FIELD = {
    'primary_prod_other':     'other_primary_production',
    'processing_other':       'other_processing',
    'storage_other':          'other_storage',
    'marketing_other':        'other_marketing',
    'service_other':          'other_service',
    'supporting_infra_other': 'other_supporting',
}


def _err(code: str, field: str, message: str) -> dict[str, Any]:
    return {'code': code, 'field': field, 'message': message}


def validate_section(section) -> dict[str, Any]:
    errors: list[dict] = []
    warnings: list[dict] = []

    components = list(section.components.all())

    if not components:
        errors.append(_err(
            'at_least_one_component', 'components',
            'At least one project component shall be selected.',
        ))

    # If any "_other" component is selected, its companion text field must be filled
    for comp in components:
        field_name = _OTHER_CODE_TO_FIELD.get(comp.code)
        if field_name:
            value = getattr(section, field_name, '') or ''
            if not value.strip():
                errors.append(_err(
                    'other_specify_required', field_name,
                    f'Please specify — "{comp.label_en}" was selected but no description provided.',
                ))

    return {
        'errors': errors,
        'warnings': warnings,
        'is_complete': len(errors) == 0,
    }
