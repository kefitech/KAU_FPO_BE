"""
Validation service for §2.3.5 Proposed Products and Services.

KAU-spec rules per item:
    - At least one product or service shall be entered.
    - Product name shall not be blank.
    - Unit of measurement shall be specified.
    - Selling price shall be greater than zero.
    - Annual production quantity shall be greater than zero.
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

    if not items:
        errors.append(_err(
            'at_least_one_product', 'items',
            'At least one product or service shall be entered.',
        ))

    for i, it in enumerate(items):
        prefix = f'items[{i}]'
        if not (it.name or '').strip():
            errors.append(_err('name_required', f'{prefix}.name', 'Product name shall not be blank.'))
        if not it.unit_of_measurement_id:
            errors.append(_err('unit_required', f'{prefix}.unit_of_measurement', 'Unit of measurement shall be specified.'))
        if it.selling_price_per_unit is None or it.selling_price_per_unit <= 0:
            errors.append(_err(
                'price_positive', f'{prefix}.selling_price_per_unit',
                'Selling price shall be greater than zero.',
            ))
        if it.annual_quantity is None or it.annual_quantity <= 0:
            errors.append(_err(
                'quantity_positive', f'{prefix}.annual_quantity',
                'Annual production quantity shall be greater than zero.',
            ))
        # Advisory
        if not it.category_id:
            warnings.append(_warn(
                'category_recommended', f'{prefix}.category',
                'Product category is recommended for better AI content generation.',
            ))
        if not it.product_type_id:
            warnings.append(_warn(
                'type_recommended', f'{prefix}.product_type',
                'Product type is recommended.',
            ))

    return {
        'errors': errors,
        'warnings': warnings,
        'is_complete': len(errors) == 0,
    }
