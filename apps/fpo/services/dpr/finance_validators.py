"""
Validation service for §2.3.18 Financial Information and Means of Finance.

KAU-spec rules:
    - All cost / MoF / WC / opex fields shall be non-negative (nulls allowed = "not entered")
    - Cat B: Total Means of Finance shall equal Total Project Cost (warning if mismatched
             beyond the admin-configurable threshold — KAU RCD B.4, default 10%)
    - Cat E: at least one product/service revenue assumption
    - Cat F: if loan_proposed → loan_amount required; loan_amount ≤ total project cost
    - Cat G: if subsidy_proposed → scheme_name required
    - Cat H: if is_operational → latest_annual_turnover required
"""
from typing import Any
from decimal import Decimal

from apps.database.models import DPRConfig


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

    # Total project cost vs total means of finance — per KAU RCD B.4, warn when
    # variance exceeds the admin-configurable threshold (default 10%). Below
    # threshold is treated as rounding / assumption noise and doesn't warrant a
    # warning. Above threshold shows a percentage-based message so the user
    # understands the magnitude, not just the rupee gap.
    total_cost = _sum(section, COST_FIELDS)
    total_mof = _sum(section, MOF_FIELDS)
    if total_cost > 0 and total_mof > 0:
        variance_pct = (abs(total_cost - total_mof) / total_cost) * Decimal('100')
        threshold_pct = DPRConfig.get_decimal('project_cost_variance_pct', Decimal('10'))
        if variance_pct > threshold_pct:
            warnings.append(_warn(
                'mof_cost_mismatch', 'mof_total',
                f'Total Means of Finance (₹{total_mof:,.0f}) differs from Total Project Cost '
                f'(₹{total_cost:,.0f}) by {variance_pct:.2f}% — above the {threshold_pct}% threshold. '
                'Please reconcile before DPR generation.',
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
        # Loan terms feed EMI + interest expense + DSCR + IRR. A blank rate
        # or tenure silently makes the whole loan schedule fall over
        # (ChatGPT calc audit 2026-09-22 — same silent-blank pattern).
        if section.rate_of_interest_pct is None or section.rate_of_interest_pct <= 0:
            errors.append(_err(
                'interest_rate_required', 'rate_of_interest_pct',
                'Rate of Interest is required when loan is proposed and shall be greater than zero.',
            ))
        if section.repayment_period_years is None or section.repayment_period_years <= 0:
            errors.append(_err(
                'tenure_required', 'repayment_period_years',
                'Repayment Period (years) is required when loan is proposed and shall be greater than zero.',
            ))

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

    # BUG-16 (KAU §6) — land ownership vs cost / lease rent consistency.
    # Reads the Location section to see how the FPO declared land ownership,
    # then checks that the Finance section carries the matching costs:
    #   - Owned by FPO / Owned by Members / Proposed to Purchase
    #     → cost_land_purchase + cost_land_development should be > 0
    #   - Leased / Rented
    #     → warn that lease rent must appear in operating cost (op_admin_
    #       expenses or op_miscellaneous — there is no dedicated op_rent
    #       field in Finance section).
    try:
        location_section = getattr(section.project, 'section_location', None)
    except Exception:  # noqa: BLE001 — section_location may not exist yet on fresh projects
        location_section = None
    if location_section is not None:
        ownership_codes = set()
        try:
            ownership_codes = set(
                location_section.land_ownership_types.values_list('code', flat=True)
            )
        except Exception:  # noqa: BLE001
            pass
        owns_or_proposes_to_buy = ownership_codes & {
            'owned_fpo', 'owned_members', 'proposed_purchase',
        }
        is_leased_or_rented = ownership_codes & {'leased', 'rented'}
        land_capex = (
            (Decimal(str(section.cost_land_purchase or 0)))
            + (Decimal(str(section.cost_land_development or 0)))
        )

        if owns_or_proposes_to_buy and land_capex == 0:
            codes_display = ', '.join(sorted(owns_or_proposes_to_buy))
            warnings.append(_warn(
                'land_owned_no_capex', 'cost_land_purchase',
                f'Land ownership declared as {codes_display} but no land cost '
                f'in capex (land purchase + development both ₹0). Either enter '
                f'the land acquisition / development cost on the Finance section, '
                f'or add a note in the Promoter Profile that the land is held on '
                f'the FPO/members\' books at nil incremental cost.',
            ))

        if is_leased_or_rented:
            # There's no dedicated op_rent field; lease rent typically lives
            # under op_admin_expenses or op_miscellaneous. Can only check that
            # at least one of those two is non-zero to catch the "forgot to
            # enter the rent" case.
            op_admin = Decimal(str(getattr(section, 'op_admin_expenses', 0) or 0))
            op_misc = Decimal(str(getattr(section, 'op_miscellaneous', 0) or 0))
            codes_display = ', '.join(sorted(is_leased_or_rented))
            if op_admin + op_misc == 0:
                warnings.append(_warn(
                    'land_leased_no_rent', 'op_admin_expenses',
                    f'Land ownership declared as {codes_display} but neither '
                    f'op_admin_expenses nor op_miscellaneous carry a value — '
                    f'this suggests lease / rent has not been captured in '
                    f'operating cost. There is no dedicated rent field; '
                    f'enter the annual lease/rent under op_admin_expenses or '
                    f'op_miscellaneous (whichever is cleaner for your DPR), '
                    f'or document the arrangement if rent is zero.',
                ))

    # BUG-18 (KAU §6) — contingency below configured tolerance. Hard cost is
    # the sum of fixed-asset lines (land, civil, machinery, equipment,
    # utilities, electrification, vehicles, water supply, site + office +
    # furniture) — excludes soft costs (pre-op, preliminary, technical
    # consultancy), contingency itself, WC margin, and IDC. Contingency
    # below `project_cost_variance_pct` of hard cost is flagged so the FPO
    # can decide to bump it or defend the lower number in prose.
    _HARD_COST_FIELDS = [
        'cost_land_purchase', 'cost_land_development',
        'cost_civil_works', 'cost_buildings', 'cost_site_development',
        'cost_plant_machinery',
        'cost_equipment', 'cost_furniture_fixtures', 'cost_office_equipment',
        'cost_vehicles',
        'cost_electrification', 'cost_water_supply', 'cost_utilities',
    ]
    hard_cost = _sum(section, _HARD_COST_FIELDS)
    contingency = Decimal(str(section.cost_contingencies or 0))
    if hard_cost > 0:
        threshold_pct = DPRConfig.get_decimal('project_cost_variance_pct', Decimal('10'))
        expected_contingency = (hard_cost * threshold_pct / Decimal('100')).quantize(Decimal('0.01'))
        if contingency < expected_contingency:
            actual_pct = (contingency * Decimal('100') / hard_cost).quantize(Decimal('0.01'))
            warnings.append(_warn(
                'contingency_below_tolerance', 'cost_contingencies',
                f'Contingency (₹{contingency:,.0f} = {actual_pct}% of hard cost) is below '
                f'the configured {threshold_pct}% tolerance (expected ≥ ₹{expected_contingency:,.0f}). '
                f'Consider raising the contingency line or add a note in the Financial Analysis '
                f'narrative explaining why a smaller buffer is adequate.',
            ))

    return {
        'errors': errors,
        'warnings': warnings,
        'is_complete': len(errors) == 0,
    }
