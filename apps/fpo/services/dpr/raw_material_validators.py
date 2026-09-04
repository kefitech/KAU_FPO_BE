"""
Validation service for §2.3.10 Raw Material Assessment and Supply System.

Runs the KAU-spec validation rules from Categories A–H and returns a structured
result: errors block submission, warnings surface as advisory, is_complete
signals section-ready-for-generation.

Kept separate from the serializer so it can also be called from:
  - `GET .../sections/raw-material/readiness/` (dry-run report)
  - PDF generation pre-check
  - AI-content generation gating
"""

from typing import Any


def _err(code: str, field: str, message: str) -> dict[str, Any]:
    return {'code': code, 'field': field, 'message': message}


def _warn(code: str, field: str, message: str) -> dict[str, Any]:
    return {'code': code, 'field': field, 'message': message}


def validate_section(section) -> dict[str, Any]:
    """
    Run KAU spec validation over a DPRSectionRawMaterial instance and its children.
    Returns {'errors': [...], 'warnings': [...], 'is_complete': bool}.
    """
    errors: list[dict] = []
    warnings: list[dict] = []

    # Prefetch to avoid N+1
    materials = list(section.materials.all().prefetch_related('quality_parameters'))

    # ── Category A — Primary Raw Material ─────────────────────────────────
    if not materials:
        errors.append(_err(
            'at_least_one_material', 'materials',
            'At least one primary raw material shall be specified.',
        ))

    for i, m in enumerate(materials):
        prefix = f'materials[{i}]'

        if not (m.name or '').strip():
            errors.append(_err('name_required', f'{prefix}.name', 'Raw Material Name shall not be blank.'))
        if not m.unit_of_purchase_id:
            errors.append(_err('unit_required', f'{prefix}.unit_of_purchase', 'Unit of Purchase shall be specified.'))
        if m.estimated_annual_requirement is None or m.estimated_annual_requirement <= 0:
            errors.append(_err(
                'annual_req_positive', f'{prefix}.estimated_annual_requirement',
                'Estimated Annual Requirement shall be greater than zero.',
            ))
        if not m.primary_source_id:
            errors.append(_err('source_required', f'{prefix}.primary_source', 'Primary Source of Supply shall be specified.'))
        if not m.procurement_method_id:
            errors.append(_err('method_required', f'{prefix}.procurement_method', 'Procurement Method shall be specified.'))
        if not m.commodity_id:
            warnings.append(_warn(
                'commodity_missing', f'{prefix}.commodity',
                'Commodity Category is recommended for better AI content generation.',
            ))

        # ── Category B — Availability ─────────────────────────────────────
        if m.estimated_qty_available_annual is None or m.estimated_qty_available_annual <= 0:
            errors.append(_err(
                'qty_available_positive', f'{prefix}.estimated_qty_available_annual',
                'Estimated Quantity Available shall be greater than zero.',
            ))
        if m.num_supplying_farmers is None or m.num_supplying_farmers <= 0:
            errors.append(_err(
                'farmers_positive', f'{prefix}.num_supplying_farmers',
                'Number of Supplying Farmers shall be greater than zero.',
            ))
        if not m.available_months:
            errors.append(_err(
                'months_required', f'{prefix}.available_months',
                'At least one month of availability shall be specified.',
            ))
        if not m.available_throughout_year:
            if not (m.peak_harvest_season or '').strip():
                errors.append(_err(
                    'peak_season_required', f'{prefix}.peak_harvest_season',
                    'Peak Harvest Season is required when material is not available year-round.',
                ))
            if not (m.off_season_strategy or '').strip():
                errors.append(_err(
                    'off_season_strategy_required', f'{prefix}.off_season_strategy',
                    'Off-season Procurement Strategy is required when material is not available year-round.',
                ))

        # ── Category D — Quality ──────────────────────────────────────────
        if m.quality_standards_applicable and not m.quality_standard_id:
            errors.append(_err(
                'quality_standard_required', f'{prefix}.quality_standard',
                'Quality Standard is required when quality standards are applicable.',
            ))

        # ── Category E — Price ────────────────────────────────────────────
        if m.current_purchase_price is None or m.current_purchase_price <= 0:
            errors.append(_err(
                'price_positive', f'{prefix}.current_purchase_price',
                'Purchase Price shall be greater than zero.',
            ))
        if m.price_varies_seasonally and not m.price_variation_range:
            warnings.append(_warn(
                'price_variation_missing', f'{prefix}.price_variation_range',
                'Price variation range should be specified when price varies seasonally.',
            ))

    # ── Category C — Procurement System (section-level) ───────────────────
    if not section.procurement_model_id:
        errors.append(_err('procurement_model_required', 'procurement_model', 'Procurement Model shall be specified.'))
    if not section.procurement_frequency:
        errors.append(_err('procurement_frequency_required', 'procurement_frequency', 'Procurement Frequency shall be specified.'))

    # ── Category G — Packaging (only mandatory if finished goods are marketed) ─
    # Advisory only — we don't know from this section alone whether the project markets finished goods
    packaging_count = section.packaging_materials.count()
    if packaging_count == 0:
        warnings.append(_warn(
            'no_packaging', 'packaging_materials',
            'No packaging materials defined. Mandatory if finished products are marketed.',
        ))

    # ── Category F — Risks are optional at KAU spec level, but we advise ──
    if section.risks.count() == 0:
        warnings.append(_warn('no_risks', 'risks', 'No supply risks specified. Consider identifying at least one for a complete DPR.'))

    return {
        'errors': errors,
        'warnings': warnings,
        'is_complete': len(errors) == 0,
    }
