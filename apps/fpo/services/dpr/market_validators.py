"""
Validation service for §2.3.11 Market Assessment and Business Model.

Enforces KAU-spec validation rules from Categories A-I and returns:
    {'errors': [...], 'warnings': [...], 'is_complete': bool}

Called by:
    - GET .../sections/market/readiness/ (dry-run report)
    - PDF generation pre-check
    - AI content-generation gating

Follows the same contract as raw_material_validators.py.
"""
from typing import Any
from decimal import Decimal


def _err(code: str, field: str, message: str) -> dict[str, Any]:
    return {'code': code, 'field': field, 'message': message}


def _warn(code: str, field: str, message: str) -> dict[str, Any]:
    return {'code': code, 'field': field, 'message': message}


def _sum_decimals(*vals):
    total = Decimal('0')
    for v in vals:
        if v is not None:
            total += Decimal(str(v))
    return total


def validate_section(section) -> dict[str, Any]:
    errors: list[dict] = []
    warnings: list[dict] = []

    products = list(section.products.all().prefetch_related('customer_categories'))
    buyers = list(section.buyers.all())
    channel_selections = list(section.channel_selections.select_related('channel'))
    competitors = list(section.competitors.all())
    risks = list(section.risks.all())

    # ── Category A — Products and Market Identification ────────────────────
    if not products:
        errors.append(_err(
            'at_least_one_product', 'products',
            'At least one product/service shall be specified.',
        ))

    for i, p in enumerate(products):
        prefix = f'products[{i}]'
        if not (p.name or '').strip():
            errors.append(_err('name_required', f'{prefix}.name', 'Product Name is required.'))
        if not p.product_category_id:
            errors.append(_err('category_required', f'{prefix}.product_category', 'Product Category is required.'))
        if not p.product_type_id:
            errors.append(_err('type_required', f'{prefix}.product_type', 'Product Type is required.'))
        if not p.intended_market_id:
            errors.append(_err('intended_market_required', f'{prefix}.intended_market', 'Intended Market is required.'))
        if not (p.geographic_market or '').strip():
            errors.append(_err(
                'geographic_market_required', f'{prefix}.geographic_market',
                'Geographic Market shall be specified.',
            ))
        if p.customer_categories.count() == 0:
            errors.append(_err(
                'customer_category_required', f'{prefix}.customer_categories',
                'At least one customer category shall be selected per product.',
            ))

        # ── Category E + H — Price ──
        if p.proposed_selling_price is None or p.proposed_selling_price <= 0:
            errors.append(_err(
                'price_positive', f'{prefix}.proposed_selling_price',
                'Proposed Selling Price shall be greater than zero.',
            ))
        if not p.unit_of_sale_id:
            errors.append(_err('unit_of_sale_required', f'{prefix}.unit_of_sale', 'Unit of Sale shall be specified.'))

        # ── Category H — Sales Projection ──
        if p.year1_qty is None or p.year1_qty <= 0:
            errors.append(_err(
                'year1_qty_positive', f'{prefix}.year1_qty',
                'Expected Sales Quantity - Year 1 shall be greater than zero.',
            ))

        # Channel mix percentages should sum to ≤ 100
        channel_mix_sum = _sum_decimals(
            p.domestic_sales_pct, p.export_sales_pct, p.institutional_sales_pct,
            p.retail_sales_pct, p.wholesale_sales_pct, p.online_sales_pct,
        )
        if channel_mix_sum > Decimal('100'):
            errors.append(_err(
                'channel_mix_over_100', f'{prefix}.channel_mix',
                f'Sales channel mix (domestic + export + institutional + retail + wholesale + online) totals {channel_mix_sum}% — cannot exceed 100%.',
            ))

    # ── Category B — Market Demand ─────────────────────────────────────────
    if not section.demand_basis:
        errors.append(_err(
            'demand_basis_required', 'demand_basis',
            'Basis of Demand Estimation shall be specified.',
        ))
    if section.demand_basis == 'other' and not (section.demand_basis_other or '').strip():
        errors.append(_err(
            'demand_basis_other_required', 'demand_basis_other',
            'Please specify the demand basis when "Others" is selected.',
        ))

    # ── Category C — Existing Buyers ───────────────────────────────────────
    if section.has_existing_buyers:
        if not buyers:
            errors.append(_err(
                'buyer_required_when_yes', 'buyers',
                'At least one buyer shall be specified when "Existing Buyers" is Yes.',
            ))
        for i, b in enumerate(buyers):
            if not b.buyer_category_id:
                errors.append(_err(
                    'buyer_category_required', f'buyers[{i}].buyer_category',
                    'Buyer Category is required for each buyer.',
                ))

    # ── Category D — Marketing Channels ────────────────────────────────────
    if not channel_selections:
        errors.append(_err(
            'channel_required', 'channel_selections',
            'At least one marketing channel shall be selected.',
        ))
    channel_share_sum = _sum_decimals(*(cs.expected_share_pct for cs in channel_selections))
    if channel_share_sum > Decimal('100'):
        errors.append(_err(
            'channel_share_over_100', 'channel_selections',
            f'Expected share across channels totals {channel_share_sum}% — cannot exceed 100%.',
        ))
    elif channel_share_sum > 0 and channel_share_sum < Decimal('100'):
        warnings.append(_warn(
            'channel_share_under_100', 'channel_selections',
            f'Expected share across channels totals {channel_share_sum}% — should ideally sum to 100%.',
        ))

    # ── Category E — Pricing Strategy ──────────────────────────────────────
    if not section.pricing_basis:
        errors.append(_err('pricing_basis_required', 'pricing_basis', 'Basis of Pricing shall be specified.'))
    if section.pricing_basis == 'other' and not (section.pricing_basis_other or '').strip():
        errors.append(_err(
            'pricing_basis_other_required', 'pricing_basis_other',
            'Please specify the pricing basis when "Others" is selected.',
        ))
    credit_cash_sum = _sum_decimals(section.credit_sales_pct, section.cash_sales_pct)
    if credit_cash_sum > Decimal('100'):
        errors.append(_err(
            'credit_cash_over_100', 'credit_sales_pct',
            f'Credit + Cash sales totals {credit_cash_sum}% — cannot exceed 100%.',
        ))

    # ── Category F — Competition ───────────────────────────────────────────
    if section.has_competitors == 'yes':
        if not competitors:
            errors.append(_err(
                'competitor_required_when_yes', 'competitors',
                'At least one competitor shall be specified when "Competitors Exist" is Yes.',
            ))
        for i, c in enumerate(competitors):
            if not (c.competitive_advantage or '').strip():
                errors.append(_err(
                    'advantage_required', f'competitors[{i}].competitive_advantage',
                    'Competitive Advantage is required for each listed competitor.',
                ))

    # ── Category G — Branding (advisory only per spec) ────────────────────
    if section.is_branded and not (section.brand_name or '').strip():
        warnings.append(_warn(
            'brand_name_missing', 'brand_name',
            'Brand Name is recommended when "Marketed under a brand" is Yes.',
        ))

    # ── Category I — Marketing Risks (advisory) ────────────────────────────
    if not risks:
        warnings.append(_warn(
            'no_risks', 'risks',
            'No marketing risks specified. Consider identifying at least one for a complete DPR.',
        ))
    for i, r in enumerate(risks):
        if not (r.mitigation_strategy or '').strip():
            errors.append(_err(
                'mitigation_required', f'risks[{i}].mitigation_strategy',
                'Mitigation Strategy is required for each marketing risk.',
            ))

    return {
        'errors': errors,
        'warnings': warnings,
        'is_complete': len(errors) == 0,
    }
