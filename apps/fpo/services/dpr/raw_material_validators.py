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

from decimal import Decimal
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
    # Per-row cost enforcement for packaging + consumables — same silent-blank
    # pattern (ChatGPT calc audit 2026-09-22). Their unit_cost * annual_requirement
    # rolls into Operating Cost; a blank silently drops the line.
    for i, pkg in enumerate(section.packaging_materials.all()):
        p = f'packaging_materials[{i}]'
        if pkg.unit_cost is None or pkg.unit_cost <= 0:
            errors.append(_err(
                'pkg_cost_required', f'{p}.unit_cost',
                'Unit Cost is required and shall be greater than zero.',
            ))
        if pkg.estimated_annual_requirement is None or pkg.estimated_annual_requirement <= 0:
            errors.append(_err(
                'pkg_qty_required', f'{p}.estimated_annual_requirement',
                'Estimated Annual Requirement is required and shall be greater than zero.',
            ))
    for i, c in enumerate(section.consumables.all()):
        p = f'consumables[{i}]'
        if c.unit_cost is None or c.unit_cost <= 0:
            errors.append(_err(
                'consumable_cost_required', f'{p}.unit_cost',
                'Unit Cost is required and shall be greater than zero.',
            ))
        if c.estimated_annual_requirement is None or c.estimated_annual_requirement <= 0:
            errors.append(_err(
                'consumable_qty_required', f'{p}.estimated_annual_requirement',
                'Estimated Annual Requirement is required and shall be greater than zero.',
            ))

    # ── Category F — Risks are optional at KAU spec level, but we advise ──
    if section.risks.count() == 0:
        warnings.append(_warn('no_risks', 'risks', 'No supply risks specified. Consider identifying at least one for a complete DPR.'))

    # KAU contradiction review 2026-10-08, Pattern 3: in all six sample
    # DPRs the plant's raw-material requirement far exceeded what the
    # members could supply (rice mills needing 4,070 t against 450 acres)
    # with no sourcing statement. Compare each material's requirement
    # (Cat A) against the FPO's OWN declared annual availability (Cat B)
    # — same material, same unit, no external yield table needed — and
    # ask for a non-member sourcing plan when demand exceeds supply.
    for i, m in enumerate(materials):
        req = m.estimated_annual_requirement
        avail = m.estimated_qty_available_annual
        if req and avail and req > avail:
            has_sourcing_plan = bool(
                (m.off_season_strategy or '').strip()
                or (m.primary_source_other or '').strip()
                or (m.primary_source_id and getattr(m.primary_source, 'code', '')
                    not in ('', 'member_farmers', 'own_members'))
            )
            if not has_sourcing_plan:
                pct = (req * Decimal('100') / avail).quantize(Decimal('1'))
                warnings.append(_warn(
                    'requirement_exceeds_declared_availability',
                    f'materials[{i}].estimated_annual_requirement',
                    f'Annual requirement ({req:,.0f}) is {pct}% of the '
                    f'declared annual availability ({avail:,.0f}) for this '
                    f'material. A bank reviewer will ask where the balance '
                    f'comes from — either raise the declared availability '
                    f'(if more supply is genuinely reachable), or state a '
                    f'non-member sourcing plan (primary source / off-season '
                    f'strategy) covering the shortfall.',
                ))

    # KAU review 2026-10-08 Priority-1 cross-checks (tester list):
    # (a) requirement vs what the baseline turnover implies the FPO
    #     currently handles (turnover ÷ purchase price ≈ current volume)
    # (b) requirement vs members' acreage × indicative commodity yield
    #     (admin-editable MasterLookup category 'commodity_yield',
    #      kg per acre per year — see seed_commodity_yields.py)
    try:
        _UNIT_TO_KG = {'kg': Decimal('1'), 'quintal': Decimal('100'),
                       'mt': Decimal('1000'), 'tonnes': Decimal('1000')}
        baseline = getattr(section.project, 'section_baseline', None)
        base_turnover = Decimal(str(
            getattr(baseline, 'current_annual_turnover', 0) or 0)) if baseline else Decimal('0')
        acreage = Decimal(str(getattr(section.project, 'total_area_acreage', 0) or 0))
        from apps.core.models.generic import MasterLookup

        for i, m in enumerate(materials):
            req = m.estimated_annual_requirement
            price = m.approx_purchase_price
            unit_code = getattr(m.unit_of_purchase, 'code', '') if m.unit_of_purchase_id else ''
            kg_factor = _UNIT_TO_KG.get(unit_code)

            # (a) scale-up vs baseline — only when both inputs exist.
            if req and price and price > 0 and base_turnover > 0:
                implied_current = base_turnover / Decimal(str(price))
                if implied_current > 0 and req > implied_current * Decimal('8'):
                    ratio = (req / implied_current).quantize(Decimal('1'))
                    warnings.append(_warn(
                        'requirement_vs_baseline_scaleup',
                        f'materials[{i}].estimated_annual_requirement',
                        f'The requirement ({req:,.0f} {unit_code or "units"}) is '
                        f'~{ratio}x what the baseline turnover implies the FPO '
                        f'currently handles (₹{base_turnover:,.0f} ÷ '
                        f'₹{price:,.0f}/unit ≈ {implied_current:,.0f}). A scale-up '
                        f'beyond ~8x needs an explicit aggregation plan in the '
                        f'narrative — or revisit the baseline turnover.',
                    ))

            # (b) member-supply ceiling from acreage × indicative yield.
            if req and kg_factor and acreage > 0:
                commodity_code = getattr(m.commodity, 'code', '') if getattr(m, 'commodity_id', None) else ''
                yield_row = MasterLookup.objects.filter(
                    category='commodity_yield', code=commodity_code,
                ).first() if commodity_code else None
                yield_kg_acre = None
                if yield_row and isinstance(yield_row.metadata, dict):
                    try:
                        yield_kg_acre = Decimal(str(yield_row.metadata.get('kg_per_acre_per_year')))
                    except Exception:  # noqa: BLE001
                        yield_kg_acre = None
                if yield_kg_acre and yield_kg_acre > 0:
                    req_kg = req * kg_factor
                    member_ceiling_kg = acreage * yield_kg_acre
                    if req_kg > member_ceiling_kg:
                        pct = (req_kg * Decimal('100') / member_ceiling_kg).quantize(Decimal('1'))
                        warnings.append(_warn(
                            'requirement_vs_member_acreage',
                            f'materials[{i}].estimated_annual_requirement',
                            f'The requirement (≈{req_kg:,.0f} kg/yr) is {pct}% of '
                            f'what the members\' {acreage:,.0f} acres can grow at '
                            f'an indicative yield of {yield_kg_acre:,.0f} kg/acre/yr '
                            f'(≈{member_ceiling_kg:,.0f} kg). State the share '
                            f'sourced from non-member farmers in the sourcing '
                            f'plan, or adjust the acreage / requirement.',
                        ))
    except Exception:  # noqa: BLE001 — cross-section lookups must never break this validator
        pass

    return {
        'errors': errors,
        'warnings': warnings,
        'is_complete': len(errors) == 0,
    }
