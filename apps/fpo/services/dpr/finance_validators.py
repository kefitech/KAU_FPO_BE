"""
Validation service for §2.3.18 Financial Information and Means of Finance.

KAU-spec rules:
    - All cost / MoF / WC / opex fields shall be non-negative (nulls allowed = "not entered")
    - Cat B: Total Means of Finance shall equal Total Project Cost (warning if mismatched)
    - Cat E: at least one product/service revenue assumption
    - Cat F: if loan_proposed → loan_amount required; loan_amount ≤ total project cost
    - Cat G: if subsidy_proposed → scheme_name required
    - Cat H: if is_operational → latest_annual_turnover required
"""
from typing import Any
from decimal import Decimal


COST_FIELDS = [
    'cost_land_purchase', 'cost_land_development', 'cost_civil_works',
    'cost_buildings', 'cost_plant_machinery', 'cost_equipment',
    'cost_utilities', 'cost_other_capex',
    'cost_site_development', 'cost_furniture_fixtures', 'cost_office_equipment',
    'cost_vehicles', 'cost_electrification', 'cost_water_supply',
    'cost_pre_operative_expenses', 'cost_preliminary_expenses',
    'cost_technical_consultancy', 'cost_contingencies', 'cost_margin_for_working_capital',
]

MOF_FIELDS = [
    'mof_promoters_contribution', 'mof_bank_term_loan', 'mof_government_grant',
    'mof_government_subsidy', 'mof_other_sources',
    'mof_share_capital', 'mof_internal_accruals', 'mof_working_capital_loan',
    'mof_venture_capital', 'mof_csr_support', 'mof_nabard_assistance',
    'mof_other_financial_assistance',
]

WC_FIELDS = [
    'wc_raw_materials', 'wc_labour_salaries', 'wc_utilities', 'wc_transportation',
    'wc_admin_expenses', 'wc_marketing_expenses', 'wc_packaging_materials',
    'wc_consumables', 'wc_repairs_maintenance', 'wc_miscellaneous',
]

OPEX_FIELDS = [
    'op_raw_material', 'op_salaries_wages', 'op_electricity', 'op_water', 'op_fuel',
    'op_transportation', 'op_packaging', 'op_repairs_maintenance', 'op_insurance',
    'op_admin_expenses', 'op_marketing_expenses', 'op_communication',
    'op_professional_charges', 'op_miscellaneous',
]


def _err(code: str, field: str, message: str) -> dict[str, Any]:
    return {'code': code, 'field': field, 'message': message}


def _warn(code: str, field: str, message: str) -> dict[str, Any]:
    return {'code': code, 'field': field, 'message': message}


def _sum(section, fields):
    total = Decimal('0')
    for f in fields:
        v = getattr(section, f, None)
        if v is not None:
            total += Decimal(str(v))
    return total


def validate_section(section) -> dict[str, Any]:
    errors: list[dict] = []
    warnings: list[dict] = []

    # Non-negative checks (nulls allowed)
    for f in COST_FIELDS + MOF_FIELDS + WC_FIELDS + OPEX_FIELDS:
        v = getattr(section, f, None)
        if v is not None and v < 0:
            errors.append(_err('negative_value', f, f'{f} shall be non-negative.'))

    # Total project cost vs total means of finance (warning if not aligned when both entered)
    total_cost = _sum(section, COST_FIELDS)
    total_mof = _sum(section, MOF_FIELDS)
    if total_cost > 0 and total_mof > 0 and abs(total_cost - total_mof) > Decimal('1'):
        warnings.append(_warn(
            'mof_cost_mismatch', 'mof_total',
            f'Total Means of Finance (₹{total_mof}) does not equal Total Project Cost (₹{total_cost}). '
            'System will verify at DPR generation.',
        ))

    # Cat E — at least one revenue assumption
    revenue_assumptions = list(section.revenue_assumptions.all())
    if not revenue_assumptions:
        errors.append(_err(
            'at_least_one_revenue', 'revenue_assumptions',
            'At least one revenue assumption (product/service) shall be entered.',
        ))
    for i, r in enumerate(revenue_assumptions):
        p = f'revenue_assumptions[{i}]'
        if not (r.product_name or '').strip():
            errors.append(_err('product_name_required', f'{p}.product_name', 'Product name is required.'))
        if r.year1_sales_quantity is None or r.year1_sales_quantity <= 0:
            errors.append(_err(
                'year1_qty_positive', f'{p}.year1_sales_quantity',
                'Year 1 Sales Quantity shall be greater than zero.',
            ))
        if r.expected_selling_price is None or r.expected_selling_price <= 0:
            errors.append(_err(
                'price_positive', f'{p}.expected_selling_price',
                'Expected Selling Price shall be greater than zero.',
            ))

    # Cat F — loan
    if section.loan_proposed:
        if section.loan_amount is None or section.loan_amount <= 0:
            errors.append(_err('loan_amount_required', 'loan_amount', 'Loan Amount is required when loan is proposed.'))
        elif total_cost > 0 and section.loan_amount > total_cost:
            errors.append(_err(
                'loan_exceeds_cost', 'loan_amount',
                f'Loan Amount (₹{section.loan_amount}) shall not exceed Total Project Cost (₹{total_cost}).',
            ))
        if not section.loan_type:
            warnings.append(_warn('loan_type_recommended', 'loan_type', 'Loan Type is recommended.'))

    # Cat G — subsidy
    if section.subsidy_proposed and not (section.subsidy_scheme_name or '').strip():
        errors.append(_err(
            'scheme_name_required', 'subsidy_scheme_name',
            'Name of Scheme is required when subsidy is proposed.',
        ))

    # Cat H — operational
    if section.is_operational and section.latest_annual_turnover is None:
        errors.append(_err(
            'turnover_required', 'latest_annual_turnover',
            'Latest Annual Turnover is required when FPO is already operational.',
        ))

    return {
        'errors': errors,
        'warnings': warnings,
        'is_complete': len(errors) == 0,
    }
