"""
DPR Calculation Engine — pure Python financial computations for the DPR module.

Per KAU RCD reply A.3 (2026-09-02):
    "The Balance Sheet shall be projected for 10 years."
    "The system shall construct the opening/project implementation balance
     sheet based on the actual timing of promoter contribution, loan
     disbursement and project expenditure, rather than assuming that the
     entire project cost is incurred on Day 1."

Design principles:
    1. **Pure Python.** No Django ORM inside the compute() call — accepts
       plain data (a project instance is fine; we read attributes but do not
       trigger further queries). Makes it unit-testable without a full DB.
    2. **DPRConfig-driven.** Discount rate, inflation, tax, depreciation, all
       come from DPRConfig at call time (see apps/database/models/dpr/config.py).
       Admin changes take effect on next compute — no code deploy.
    3. **Layered.** Each sub-computation lives in its own function and returns
       a typed dataclass. Assemble at the top. Downstream (PDF, admin views)
       consume the assembled result.
    4. **10-year default projection.** Projection window comes from
       `DPRConfig.get_int('projection_years')` — default 10.

Current state (2026-09-02 — Phase 3a, skeleton + Total Cost / Total MoF):
    - CalculationResult dataclass shape locked
    - Total Project Cost aggregation from finance section
    - Total Means of Finance aggregation
    - Variance % + threshold-check output
    - Everything else returns TODO placeholders — filled in in sub-phases 3b–3h.

The skeleton is intentionally shipped early so downstream code (admin view,
PDF renderer, calc API endpoint) can start integrating against the shape
even as sub-phases fill in the individual calc modules.

Author: Athul Gopan (Kefi Tech Solutions)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from apps.database.models import DPRConfig


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclasses — the shape callers depend on
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ProjectCostBreakdown:
    """Sum of the ~19 cost fields on DPRSectionFinance. Individual field values
    are surfaced so the PDF can render them as a table."""
    total: Decimal
    by_field: dict[str, Decimal]


@dataclass
class MeansOfFinanceBreakdown:
    """Sum of the ~12 MoF fields on DPRSectionFinance."""
    total: Decimal
    by_field: dict[str, Decimal]


@dataclass
class CostMofVariance:
    """Variance between aggregated Finance-section Total Project Cost and
    Total Means of Finance (both computed from the ~19 cost fields + ~12 MoF
    fields on DPRSectionFinance). This is the internal Finance-section
    self-consistency check — NOT the RCD B.4 check against §2.3.4's
    user-entered `estimated_project_cost`. For that, see `UserEstimateVariance`.

    `pct` is (|delta| / cost) * 100 — zero when cost is zero."""
    cost_total: Decimal
    mof_total: Decimal
    delta: Decimal            # mof - cost. Positive = MoF over. Negative = MoF short.
    pct: Decimal
    threshold_pct: Decimal    # from DPRConfig
    exceeds_threshold: bool


@dataclass
class UserEstimateVariance:
    """RCD B.4 — variance between the user's §2.3.4 preliminary estimate
    (`DPRSectionInvestment.estimated_project_cost`) and the auto-computed
    project cost aggregated from §2.3.18 Finance line items.

    KAU RCD reply B.4 requires the system to flag a material mismatch between
    what the FPO expected to spend (early ballpark) and what the detailed
    Finance section actually adds up to. Threshold comes from
    `DPRConfig.project_cost_variance_pct` — admin-editable, default 10%.

    `skipped=True` means the FPO did not fill §2.3.4 at all — per RCD B.4
    the auto-computed cost simply becomes authoritative and no warning fires.
    """
    user_estimate: Decimal | None   # None when §2.3.4 is left blank
    computed_cost: Decimal          # Sum of §2.3.18 cost fields
    delta: Decimal                  # computed - user_estimate (positive = auto is higher)
    pct: Decimal                    # (|delta| / user_estimate) * 100
    threshold_pct: Decimal          # from DPRConfig.project_cost_variance_pct
    exceeds_threshold: bool
    skipped: bool                   # True when user_estimate is None


@dataclass
class CapitalScheduleRow:
    """One month of the implementation-period capital schedule."""
    month: int                      # 1-indexed within the implementation period
    cost_incurred: Decimal          # capex hitting this month
    mof_received: Decimal           # inflows this month (contribution + loan + subsidy)
    cumulative_cost: Decimal        # running cost total to end of this month
    cumulative_mof: Decimal         # running MoF total to end of this month
    unfunded_balance: Decimal       # cumulative_cost - cumulative_mof (positive = short)


@dataclass
class CapitalSchedule:
    """Time-phased capital investment + means-of-finance schedule for the
    implementation period. See build_capital_schedule() for the distribution
    model."""
    implementation_period_months: int
    rows: list[CapitalScheduleRow]
    # Total-check fields — a good schedule ends with cumulative_cost == cost.total
    # and cumulative_mof == mof.total. Callers assert these to catch drift.
    final_cost: Decimal
    final_mof: Decimal
    distribution_note: str          # human-readable description of the source used
    # KAU RCD A.3 compliance flag: True when schedule uses ACTUAL tranche data,
    # False when it falls back to a uniform-monthly assumption. Downstream
    # (PDF, admin views) surfaces this as "estimated" vs "declared timing".
    is_estimated: bool
    # Reconciliation with section-level totals — populated when tranche data
    # is used. Keys are section field names (e.g. 'cost_plant_machinery');
    # values are (tranche_sum, section_field_value, delta). Non-zero delta
    # indicates the user's tranche entries don't match the Finance section
    # total and needs reconciliation.
    reconciliation: dict[str, tuple[Decimal, Decimal, Decimal]] = field(default_factory=dict)


@dataclass
class AssetClassRow:
    """One year's movement for a single asset class."""
    year: int                       # 1-indexed year (Y1, Y2, ...)
    opening_gross: Decimal          # gross block at start of year
    addition: Decimal               # additions this year (from CWIP → fixed)
    opening_accum_dep: Decimal      # accumulated depreciation at start
    depreciation: Decimal           # depreciation charge for this year
    closing_gross: Decimal          # gross block at end
    closing_accum_dep: Decimal      # accumulated depreciation at end
    net_block: Decimal              # closing_gross - closing_accum_dep


@dataclass
class AssetClass:
    """Full N-year schedule for one asset class."""
    key: str                        # 'land' / 'buildings' / 'machinery' / …
    label: str                      # 'Land' / 'Buildings' / …
    rate_pct: Decimal               # SLM annual depreciation rate; 0 for non-depreciable
    initial_cost: Decimal           # total capex mapped into this class
    rows: list[AssetClassRow]       # length == projection_years
    is_depreciable: bool


@dataclass
class DepreciationSchedule:
    """Per-asset-class × per-year depreciation schedule.

    CWIP handling: all capex is treated as CWIP during the implementation
    period and transitions to fixed assets at the START of Year 1 (first
    operational year). Depreciation begins in Y1.

    Note (A.3-refinement, deferred): a stricter reading of A.3 places assets
    into fixed-asset ledgers on a per-tranche basis (as each machine gets
    installed). Current implementation is bulk-transition at Y1 — matches
    common bank-DPR practice and simplifies the P&L / BS builds. If a
    stricter A.3 audit surfaces during UAT, upgrade path is to key
    transitions off individual tranche `expected_month + is_actual`.
    """
    projection_years: int
    classes: list[AssetClass]
    total_depreciation_by_year: dict[int, Decimal]   # {year: sum across classes}


@dataclass
class ProfitLossRow:
    """One year of the P&L projection."""
    year: int
    revenue: Decimal                # from revenue_assumptions × growth
    operating_cost: Decimal         # from opex fields × inflation
    ebitda: Decimal                 # revenue − operating cost
    depreciation: Decimal           # from DepreciationSchedule.total_depreciation_by_year
    ebit: Decimal                   # ebitda − depreciation
    interest: Decimal               # from InterestSchedule (loan amortisation)
    pbt: Decimal                    # ebit − interest (profit before tax)
    tax: Decimal                    # pbt × tax_rate (0 if pbt < 0)
    pat: Decimal                    # pbt − tax (profit after tax)


@dataclass
class ProfitLoss:
    """N-year projected income statement."""
    projection_years: int
    rows: list[ProfitLossRow]
    # Aggregations for downstream (BS retained-earnings, ratios)
    total_pat: Decimal
    cumulative_pat_by_year: dict[int, Decimal]


@dataclass
class InterestScheduleRow:
    year: int
    opening_balance: Decimal
    interest: Decimal
    principal: Decimal
    closing_balance: Decimal


@dataclass
class InterestSchedule:
    """Loan amortisation schedule.

    Populated only when the project has a loan proposed; else all rows zero.

    Convention (per KAU pre-UAT reply §2.2, 2026-09-08):
      * DEFAULT — Reducing balance with equal annual principal instalments
        (NABARD refinance convention). Interest declines year on year as
        the outstanding balance amortises.
      * OPT-IN — EMI (equated monthly instalment, annualised). Selected via
        `DPRSectionFinance.repayment_method='emi'` when a specific bank /
        scheme requires EMI. Total (principal + interest) stays constant
        across repayment years; principal share rises + interest share falls.

    Interest during moratorium is admin-configurable via DPRConfig
    `moratorium_interest_treatment` (default 'serviced'):
      * 'serviced' — interest paid periodically, loan balance stays flat
        during moratorium.
      * 'capitalised' — interest added to loan outstanding, no cash payment
        during moratorium. Post-moratorium principal calculation uses the
        grown balance.
    """
    projection_years: int
    rows: list[InterestScheduleRow]
    loan_amount: Decimal
    interest_rate_pct: Decimal
    tenure_years: int
    moratorium_months: int
    # Which convention was applied ('reducing_balance' or 'emi'). Renders on
    # the DPR PDF so the reviewer knows which method produced the schedule.
    repayment_method: str = 'reducing_balance'
    moratorium_interest_treatment: str = 'serviced'


@dataclass
class CashFlowRow:
    """One year of the cash flow statement (indirect method)."""
    year: int                           # 0 = construction, 1..N = operations
    # ── Operating activities ──
    pat: Decimal
    depreciation_addback: Decimal       # non-cash addback
    working_capital_change: Decimal     # negative = WC absorbed cash
    cash_from_operations: Decimal
    # ── Investing activities ──
    capex: Decimal                      # negative for cash outflow
    cash_from_investing: Decimal
    # ── Financing activities ──
    mof_inflow: Decimal                 # promoter + loan + subsidy
    loan_principal_repayment: Decimal   # negative
    cash_from_financing: Decimal
    # ── Totals ──
    net_cash_flow: Decimal
    opening_cash: Decimal
    closing_cash: Decimal


@dataclass
class CashFlow:
    """N+1 year cash flow (Y0 construction + Y1..YN operations)."""
    projection_years: int
    rows: list[CashFlowRow]
    ending_cash: Decimal


@dataclass
class BalanceSheetRow:
    """One year of the balance sheet. Year 0 = end of construction period
    (opening BS, all MoF received, all capex either committed to CWIP or land),
    Year 1..N = end of each operational year."""
    year: int

    # ── Assets ──
    land: Decimal
    cwip: Decimal                       # capex not yet commissioned. Zero after Y0.
    gross_fixed_assets: Decimal         # commissioned FA at cost
    accumulated_depreciation: Decimal
    net_fixed_assets: Decimal           # gross − accum dep
    working_capital: Decimal            # from cost.margin_for_working_capital (constant here)
    cash_and_bank: Decimal              # from CashFlow.closing_cash
    total_assets: Decimal

    # ── Equity & Liabilities ──
    promoter_equity: Decimal            # promoter contribution + share capital
    capital_reserve: Decimal            # subsidies + grants + CSR (treated as reserve)
    retained_earnings: Decimal          # cumulative PAT
    total_equity: Decimal
    term_loan_outstanding: Decimal      # from InterestSchedule.closing_balance
    other_liabilities: Decimal          # placeholder for WC loan / creditors (Y0 seeded)
    total_liabilities: Decimal
    total_equity_and_liabilities: Decimal

    # ── Invariant check ──
    invariant_delta: Decimal            # total_assets − total_equity_and_liabilities. Should be ~0.
    invariant_ok: bool                  # abs(delta) < 1 rupee


@dataclass
class BalanceSheet:
    """N+1 year balance sheet (Y0 opening + Y1..YN operational year-ends)."""
    projection_years: int
    rows: list[BalanceSheetRow]
    all_years_balanced: bool            # True iff every row's invariant_ok is True
    max_invariant_delta: Decimal        # largest abs(delta) across all years — diagnostic


@dataclass
class DSCRRow:
    """Debt Service Coverage Ratio for one year.
    dscr = (PAT + depreciation + interest) / (interest + principal).
    None when there is no debt service in the year (division by zero)."""
    year: int
    numerator: Decimal          # cash available for debt service
    denominator: Decimal        # interest + principal (aka debt service)
    dscr: Optional[Decimal]     # None when denominator is zero


@dataclass
class FinancialRatios:
    """Bank-DPR appraisal ratios. All computed from upstream sub-phases:
    - NPV / IRR: from CashFlow (Y0 outflow + Y1..YN free cash flows)
    - DSCR: from ProfitLoss + InterestSchedule
    - Payback: from cumulative free cash flow crossing zero
    - Break-even year: from ProfitLoss cumulative PAT crossing zero
    """
    discount_rate_pct: Decimal          # from DPRConfig at compute time

    npv: Decimal                        # ₹ present value of all cash flows discounted at discount_rate
    irr_pct: Optional[Decimal]          # % IRR; None when not solvable (all-negative CF, all-positive CF, etc.)
    irr_converged: bool                 # False if bisection didn't converge (surfaces engine bug in tests)

    dscr_rows: list[DSCRRow]
    dscr_min: Optional[Decimal]         # worst year among years with debt service; None if no debt
    dscr_avg: Optional[Decimal]         # average across years with debt service

    payback_period_years: Optional[Decimal]     # None when cumulative FCF never turns positive
    break_even_year: Optional[int]              # first year cumulative PAT >= 0; None if never


@dataclass
class RiskCategoryScore:
    """Aggregated risk level for one of the 6 risk categories."""
    category: str                        # 'production' / 'market' / 'financial' / ...
    category_label: str
    risk_count: int                      # number of risks the FPO entered in this category
    scored_count: int                    # count with both probability + impact set (matrix-lookable)
    class_counts: dict[str, int]         # {'low': n, 'moderate': n, 'high': n}
    category_class: str                  # 'low' / 'moderate' / 'high' — worst-case across scored risks
    # None when the FPO added risks to this category but never set prob/impact
    unscored_note: Optional[str]


@dataclass
class AutoPulledRisk:
    """A risk captured in another wizard section (Raw Material / Market /
    Technology / ESS climate) that the Risk Assessment section is auto-pulling
    to close the KAU 2026-09-10 gap (risks in 5 different places).

    Not scored via the probability x impact matrix yet — the FPO can promote
    it to a full DPRRiskItem in §2.3.22 to add scoring, or the PDF renders
    it in a dedicated "additional risks from other sections" subsection.
    """
    source: str                       # 'raw_material' / 'market' / 'technology' / 'ess_climate'
    source_label: str                 # 'Raw Material' / 'Market' / 'Technology' / 'ESS (Climate)'
    category: str                     # maps to one of the 6 canonical risk categories
    category_label: str               # 'Production Risk' / 'Market Risk' / 'Environmental Risk'
    risk_code: str                    # section-specific code (e.g. 'supply_variability')
    risk_label: str                   # human-readable name of the risk
    risk_description: str             # verbatim from the source section, if any
    mitigation_strategy: str          # verbatim from the source section


@dataclass
class RiskAssessment:
    """Per-KAU-RCD-B.9 overall risk rating for the project.

    Rule:
      - Any category with class == 'high'                            → overall 'high'
      - Else any category with class == 'moderate'                   → overall 'moderate'
      - All categories 'low' (or no risks at all)                    → overall 'low'
    Configurable via `DPRRiskMatrixCell` (admin edits cells at
    /api/admin/dpr/risk-matrix/).
    """
    categories: list[RiskCategoryScore]
    overall_class: str                    # 'low' / 'moderate' / 'high'
    total_risks_added: int
    total_risks_scored: int               # subset with prob+impact set
    matrix_note: str                      # human-readable "5 cells configured, source: default 3x3"
    # KAU 2026-09-10 gap-close: risks captured in Raw Material / Market /
    # Technology / ESS sections auto-pulled into the risk register.
    auto_pulled: list[AutoPulledRisk] = field(default_factory=list)


@dataclass
class CalculationResult:
    """Top-level result. Sub-phases fill in the currently-empty dicts.

    Attribute order matches the DPR chapter order in the PDF so
    serialisation is straightforward.
    """
    projection_years: int
    cost: ProjectCostBreakdown
    mof: MeansOfFinanceBreakdown
    variance: CostMofVariance
    user_estimate_variance: Optional[UserEstimateVariance] = None    # RCD B.4
    capital_schedule: Optional[CapitalSchedule] = None
    depreciation: Optional[DepreciationSchedule] = None
    interest_schedule: Optional[InterestSchedule] = None
    profit_loss: Optional[ProfitLoss] = None
    cash_flow: Optional[CashFlow] = None
    balance_sheet: Optional[BalanceSheet] = None
    ratios: Optional[FinancialRatios] = None
    risk_assessment: Optional[RiskAssessment] = None

    todo_future_sub_phases: dict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Cost + MoF aggregation (Phase 3a — done)
# ─────────────────────────────────────────────────────────────────────────────

# Kept as module-level constants so the field list is one source of truth,
# mirrored from apps/fpo/services/dpr/finance_validators.py. If either list
# changes, both files must be updated in lock-step.
# TODO(3-later): extract to a shared constants module so drift can't happen.
COST_FIELDS = (
    'cost_land_purchase', 'cost_land_development', 'cost_civil_works',
    'cost_buildings', 'cost_plant_machinery', 'cost_equipment',
    'cost_utilities', 'cost_other_capex',
    'cost_site_development', 'cost_furniture_fixtures', 'cost_office_equipment',
    'cost_vehicles', 'cost_electrification', 'cost_water_supply',
    'cost_pre_operative_expenses', 'cost_preliminary_expenses',
    'cost_technical_consultancy', 'cost_contingencies', 'cost_margin_for_working_capital',
    # Per KAU pre-UAT reply §2.6 (2026-09-08) — IDC is a Cat A capex line
    # (user-entered here); _aggregate_class_capex allocates it pro-rata
    # across depreciable classes (see _allocate_idc).
    'cost_interest_during_construction',
)

MOF_FIELDS = (
    'mof_promoters_contribution', 'mof_bank_term_loan', 'mof_government_grant',
    'mof_government_subsidy', 'mof_other_sources',
    'mof_share_capital', 'mof_internal_accruals', 'mof_working_capital_loan',
    'mof_venture_capital', 'mof_csr_support', 'mof_nabard_assistance',
    'mof_other_financial_assistance',
)


def _decimal(v) -> Decimal:
    """Coerce a possibly-None numeric field to Decimal, returning Decimal(0)
    when the field is unset. Preserves precision for real values."""
    if v is None:
        return Decimal('0')
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


def _sum_fields(section, fields: tuple[str, ...]) -> tuple[Decimal, dict[str, Decimal]]:
    """Sum the given fields on `section`, returning (total, per-field-map).
    Missing fields are treated as zero. `section` may be None if the FPO
    has not saved the Finance section yet."""
    by_field: dict[str, Decimal] = {}
    total = Decimal('0')
    if section is None:
        for f in fields:
            by_field[f] = Decimal('0')
        return total, by_field
    for f in fields:
        v = _decimal(getattr(section, f, None))
        by_field[f] = v
        total += v
    return total, by_field


def compute_cost_and_mof(project) -> tuple[ProjectCostBreakdown, MeansOfFinanceBreakdown, CostMofVariance]:
    """Aggregate the finance section into cost, MoF, and their variance.

    Reads the variance threshold from DPRConfig each call — admin can
    change 10% → 15% via /admin/dpr-config and next compute() picks it up.
    """
    finance_section = getattr(project, 'section_finance', None)

    cost_total, cost_map = _sum_fields(finance_section, COST_FIELDS)
    mof_total, mof_map = _sum_fields(finance_section, MOF_FIELDS)

    delta = mof_total - cost_total
    if cost_total > 0:
        pct = (abs(delta) / cost_total) * Decimal('100')
    else:
        pct = Decimal('0')
    threshold = DPRConfig.get_decimal('project_cost_variance_pct', Decimal('10'))

    return (
        ProjectCostBreakdown(total=cost_total, by_field=cost_map),
        MeansOfFinanceBreakdown(total=mof_total, by_field=mof_map),
        CostMofVariance(
            cost_total=cost_total,
            mof_total=mof_total,
            delta=delta,
            pct=pct,
            threshold_pct=threshold,
            exceeds_threshold=(pct > threshold) if cost_total > 0 and mof_total > 0 else False,
        ),
    )


def compute_user_estimate_variance(project) -> UserEstimateVariance:
    """RCD B.4 — compare §2.3.4 `estimated_project_cost` against the
    auto-computed §2.3.18 Finance cost total.

    Threshold sourced from DPRConfig.project_cost_variance_pct — admin can
    tune it via /api/admin/dpr-config/ and the next validator run picks it up.

    Only fires the variance check when BOTH numbers are meaningful:
        - user_estimate is set and > 0
        - computed_cost is > 0
    Otherwise emits skipped=True (or a zero-variance record) so callers can
    render "auto-computed cost is now authoritative" without a false warning.
    """
    inv_section = getattr(project, 'section_investment', None)
    user_estimate = _decimal(getattr(inv_section, 'estimated_project_cost', None)) if inv_section else Decimal('0')

    finance_section = getattr(project, 'section_finance', None)
    computed_cost, _ = _sum_fields(finance_section, COST_FIELDS)

    threshold = DPRConfig.get_decimal('project_cost_variance_pct', Decimal('10'))

    # Skip case — user left §2.3.4 blank. Per RCD B.4 the auto-computed cost
    # simply becomes authoritative; no warning to raise.
    skipped = inv_section is None or inv_section.estimated_project_cost is None
    if skipped:
        return UserEstimateVariance(
            user_estimate=None,
            computed_cost=computed_cost,
            delta=computed_cost,
            pct=Decimal('0'),
            threshold_pct=threshold,
            exceeds_threshold=False,
            skipped=True,
        )

    delta = computed_cost - user_estimate
    if user_estimate > 0:
        pct = (abs(delta) / user_estimate) * Decimal('100')
    else:
        pct = Decimal('0')

    exceeds = pct > threshold and user_estimate > 0 and computed_cost > 0

    return UserEstimateVariance(
        user_estimate=user_estimate,
        computed_cost=computed_cost,
        delta=delta,
        pct=pct,
        threshold_pct=threshold,
        exceeds_threshold=exceeds,
        skipped=False,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Capital schedule (Phase 3b — assumption-based)
# ─────────────────────────────────────────────────────────────────────────────

def build_capital_schedule(
    project,
    cost: ProjectCostBreakdown,
    mof: MeansOfFinanceBreakdown,
    implementation_months: int,
) -> CapitalSchedule:
    """Time-phased capital schedule for the implementation period.

    Preferred source (KAU RCD A.3 compliance):
        `project.capital_tranches` — user-declared dated inflows and
        outflows. Each tranche has an `expected_month` and an `amount`.
        Inflow types drive MoF; outflow types drive capex.

    Fallback (when the project has no tranches recorded):
        Uniform monthly distribution over `implementation_months`. The
        `is_estimated=True` flag on the returned schedule signals this so
        downstream code / PDF can render "estimated" labels.

    Signature is stable across sources — 3c–3h consume `CapitalSchedule`
    identically regardless of whether it came from tranches or fallback.
    """
    tranches = list(project.capital_tranches.all()) if project.pk else []
    if tranches:
        return _schedule_from_tranches(tranches, cost, mof, implementation_months)
    return _schedule_uniform_fallback(cost, mof, implementation_months)


def _schedule_from_tranches(
    tranches: list,
    cost: ProjectCostBreakdown,
    mof: MeansOfFinanceBreakdown,
    implementation_months: int,
) -> CapitalSchedule:
    """Real A.3-compliant schedule from user-declared tranches."""
    from apps.database.models import DPRCapitalTranche

    # Grow the horizon if any tranche extends past the configured window
    max_month = max(t.expected_month for t in tranches)
    n = max(implementation_months, max_month)

    # Bucket by month
    cost_by_month: dict[int, Decimal] = {m: Decimal('0') for m in range(1, n + 1)}
    mof_by_month: dict[int, Decimal] = {m: Decimal('0') for m in range(1, n + 1)}
    for t in tranches:
        # Defensive clamp — serializer now rejects month<1 on write, but old
        # rows or hand-inserted data may still have month=0. Treat those as
        # month 1 so PDF generation doesn't KeyError.
        month_idx = max(1, int(t.expected_month))
        amt = _decimal(t.amount)
        if t.tranche_type in DPRCapitalTranche.INFLOW_TYPES:
            mof_by_month[month_idx] += amt
        elif t.tranche_type in DPRCapitalTranche.OUTFLOW_TYPES:
            cost_by_month[month_idx] += amt

    rows: list[CapitalScheduleRow] = []
    cum_cost = Decimal('0')
    cum_mof = Decimal('0')
    for month in range(1, n + 1):
        cum_cost += cost_by_month[month]
        cum_mof += mof_by_month[month]
        rows.append(CapitalScheduleRow(
            month=month,
            cost_incurred=cost_by_month[month],
            mof_received=mof_by_month[month],
            cumulative_cost=cum_cost,
            cumulative_mof=cum_mof,
            unfunded_balance=cum_cost - cum_mof,
        ))

    # Reconciliation: tranche sums per finance_field vs section totals
    recon: dict[str, tuple[Decimal, Decimal, Decimal]] = {}
    for t in tranches:
        if not t.finance_field:
            continue
        section_val = (
            cost.by_field.get(t.finance_field)
            if t.finance_field in cost.by_field
            else mof.by_field.get(t.finance_field, Decimal('0'))
        )
        current = recon.get(t.finance_field, (Decimal('0'), section_val or Decimal('0'), Decimal('0')))
        tranche_sum = current[0] + _decimal(t.amount)
        section_amt = current[1]
        recon[t.finance_field] = (tranche_sum, section_amt, tranche_sum - section_amt)

    return CapitalSchedule(
        implementation_period_months=n,
        rows=rows,
        final_cost=cum_cost,
        final_mof=cum_mof,
        distribution_note=(
            f'Actual tranche timing — {len(tranches)} tranche(s) over {n} months '
            '(per KAU RCD A.3).'
        ),
        is_estimated=False,
        reconciliation=recon,
    )


def _schedule_uniform_fallback(
    cost: ProjectCostBreakdown,
    mof: MeansOfFinanceBreakdown,
    implementation_months: int,
) -> CapitalSchedule:
    """Uniform-monthly fallback when no tranches are recorded.

    Emits `is_estimated=True` so consumers (PDF, admin view) can render an
    "estimated timing" caveat. Per KAU RCD A.3 the caller should encourage
    users to enter actual tranche data via DPRCapitalTranche.
    """
    n = max(1, implementation_months)
    total_cost = cost.total
    total_mof = mof.total

    monthly_cost = (total_cost / n).quantize(Decimal('0.01'))
    monthly_mof = (total_mof / n).quantize(Decimal('0.01'))

    rows: list[CapitalScheduleRow] = []
    cum_cost = Decimal('0')
    cum_mof = Decimal('0')
    for month in range(1, n + 1):
        is_last = month == n
        cost_this = (total_cost - cum_cost) if is_last else monthly_cost
        mof_this = (total_mof - cum_mof) if is_last else monthly_mof
        cum_cost += cost_this
        cum_mof += mof_this
        rows.append(CapitalScheduleRow(
            month=month,
            cost_incurred=cost_this,
            mof_received=mof_this,
            cumulative_cost=cum_cost,
            cumulative_mof=cum_mof,
            unfunded_balance=cum_cost - cum_mof,
        ))

    return CapitalSchedule(
        implementation_period_months=n,
        rows=rows,
        final_cost=cum_cost,
        final_mof=cum_mof,
        distribution_note=(
            f'Estimated — uniform monthly distribution across {n} months. '
            'No capital tranche data recorded for this project. Enter actual '
            'tranches via DPRCapitalTranche for KAU RCD A.3-compliant timing.'
        ),
        is_estimated=True,
        reconciliation={},
    )


# ─────────────────────────────────────────────────────────────────────────────
# CWIP → Fixed Assets → Depreciation schedule (Phase 3c)
# ─────────────────────────────────────────────────────────────────────────────

# Map DPRSectionFinance cost fields → asset class.
# Land is non-depreciable. Working-capital margin is not a fixed asset — it
# excluded from depreciation entirely (routed via `WORKING_CAPITAL_FIELDS`).
# Pre-operative expenses are capitalised and amortised over the projection
# window (bank-DPR convention).
COST_FIELD_TO_ASSET_CLASS: dict[str, str] = {
    'cost_land_purchase':         'land',
    'cost_land_development':      'land',
    'cost_civil_works':           'buildings',
    'cost_buildings':             'buildings',
    'cost_site_development':      'buildings',
    'cost_plant_machinery':       'machinery',
    'cost_equipment':             'equipment',
    'cost_furniture_fixtures':    'equipment',
    'cost_office_equipment':      'equipment',
    'cost_vehicles':              'equipment',
    'cost_electrification':       'equipment',
    'cost_water_supply':          'equipment',
    'cost_utilities':             'equipment',
    'cost_pre_operative_expenses':   'pre_operative',
    'cost_preliminary_expenses':     'pre_operative',
    'cost_technical_consultancy':    'pre_operative',
    'cost_contingencies':            'pre_operative',
    'cost_other_capex':              'other',
    # Excluded — not a fixed asset:
    # 'cost_margin_for_working_capital' → routed to Working Capital, not depreciation
    # 'cost_interest_during_construction' → allocated pro-rata across
    #   depreciable classes by _allocate_idc (see below). Per KAU pre-UAT
    #   reply §2.6: IDC is capitalised into the qualifying asset base +
    #   depreciated along with the related asset, NOT amortised as pre-op.
}

# Ordered by preferred allocation weight — used when class totals are all
# zero (very rare — user has entered IDC but no other fixed-asset capex).
_IDC_DEPRECIABLE_CLASSES: tuple[str, ...] = ('buildings', 'machinery', 'equipment')


def _allocate_idc(idc_amount: Decimal, class_totals: dict[str, Decimal]) -> dict[str, Decimal]:
    """Distribute IDC pro-rata across depreciable asset classes.

    Per KAU pre-UAT reply §2.6 (2026-09-08):
      "Where IDC relates to a common facility or cannot be directly
       attributed to a particular asset, it may be allocated to the
       relevant asset class using a reasonable predefined allocation rule."

    Rule chosen: pro-rata by existing class total across the 3 depreciable
    fixed-asset classes (buildings + machinery + equipment). If none of
    those has any capex (edge case — user entered IDC but no capex), IDC
    falls into `machinery` as a safe default (most common asset class for
    processing-project FPOs).

    Rounding residue (if any) is pushed into `machinery` so the allocation
    sum matches the input IDC exactly.
    """
    if idc_amount <= 0:
        return {}
    depreciable_total = sum(class_totals.get(c, Decimal('0')) for c in _IDC_DEPRECIABLE_CLASSES)
    if depreciable_total <= 0:
        return {'machinery': idc_amount}
    allocation: dict[str, Decimal] = {}
    for cls in _IDC_DEPRECIABLE_CLASSES:
        cls_total = class_totals.get(cls, Decimal('0'))
        if cls_total > 0:
            share = cls_total / depreciable_total
            allocation[cls] = (idc_amount * share).quantize(Decimal('0.01'))
    # Rounding correction — dump any residue into machinery so the
    # allocation sum matches idc_amount exactly (avoids silent capex loss).
    residue = idc_amount - sum(allocation.values())
    if residue != 0:
        allocation['machinery'] = allocation.get('machinery', Decimal('0')) + residue
    return allocation

# Asset class configuration:
#   (label, DPRConfig rate key, amortisation-years-if-not-depreciable-rate)
# For 'land' and 'other' the rate is 0 (not depreciated). Pre-operative uses
# straight-line amortisation over projection_years (bank convention).
_ASSET_CLASS_META: dict[str, tuple[str, Optional[str]]] = {
    'land':          ('Land',                 None),  # non-depreciable
    'buildings':     ('Buildings & civil',    'depreciation_rate_building_pct'),
    'machinery':     ('Plant & machinery',    'depreciation_rate_machinery_pct'),
    'equipment':     ('Equipment & vehicles', 'depreciation_rate_equipment_pct'),
    'pre_operative': ('Pre-operative expenses (amortised)',  None),  # amortised, not depreciated
    'other':         ('Other capex',          None),  # non-depreciable
}


def _class_rate_pct(class_key: str) -> Decimal:
    """Return SLM depreciation rate % for the asset class. 0 for non-depreciable."""
    _, cfg_key = _ASSET_CLASS_META[class_key]
    if cfg_key is None:
        return Decimal('0')
    return DPRConfig.get_decimal(cfg_key, Decimal('0'))


def _aggregate_class_capex(cost: ProjectCostBreakdown) -> dict[str, Decimal]:
    """Sum cost fields into their target asset class, then allocate IDC.

    IDC handling — per KAU pre-UAT reply §2.6:
      IDC is CAPITALISED into the depreciable asset base (buildings +
      machinery + equipment) pro-rata by class total. It does NOT go
      through pre-operative amortisation like the other soft costs.
      Any residual rounding is pushed into machinery so nothing is lost.
    """
    totals: dict[str, Decimal] = {k: Decimal('0') for k in _ASSET_CLASS_META}
    idc_amount = Decimal('0')
    for field_name, amount in cost.by_field.items():
        if field_name == 'cost_interest_during_construction':
            # Held aside — allocated across depreciable classes below
            # rather than routed through pre-op / other-capex like the
            # other Cat A soft costs.
            idc_amount = amount
            continue
        target = COST_FIELD_TO_ASSET_CLASS.get(field_name)
        if target is None:
            continue  # e.g. working capital margin — not depreciable
        totals[target] += amount

    if idc_amount > 0:
        allocation = _allocate_idc(idc_amount, totals)
        for cls, amt in allocation.items():
            totals[cls] += amt

    return totals


def build_depreciation_schedule(
    cost: ProjectCostBreakdown,
    projection_years: int,
) -> DepreciationSchedule:
    """Build a N-year straight-line depreciation schedule per asset class.

    CWIP model (simplified for 3c):
        - All capex sits in CWIP during implementation
        - At start of Y1 (first operational year), CWIP transitions to
          fixed assets in one bulk move
        - Depreciation begins in Y1 for the full year's rate
        - Pre-operative expenses amortise straight-line over `projection_years`
        - Land + 'other' capex sit at cost with zero depreciation

    Returns a DepreciationSchedule keyed by asset class + year. The
    `total_depreciation_by_year` sum is what the P&L (3d) consumes.
    """
    class_totals = _aggregate_class_capex(cost)
    classes: list[AssetClass] = []
    year_totals: dict[int, Decimal] = {y: Decimal('0') for y in range(1, projection_years + 1)}

    for class_key, (label, _cfg_key) in _ASSET_CLASS_META.items():
        initial = class_totals[class_key]
        rate = _class_rate_pct(class_key)
        is_depreciable = rate > 0 or class_key == 'pre_operative'

        rows: list[AssetClassRow] = []
        gross = initial
        accum = Decimal('0')

        for year in range(1, projection_years + 1):
            opening_gross = gross
            opening_accum = accum
            addition = initial if year == 1 else Decimal('0')

            # Depreciation for this year
            if class_key == 'pre_operative':
                # Straight-line amortisation over projection window
                dep = (initial / Decimal(projection_years)).quantize(Decimal('0.01'))
            elif rate > 0:
                # SLM on initial cost — no additions after Y1 in this model
                dep = (initial * rate / Decimal('100')).quantize(Decimal('0.01'))
                # Don't depreciate below zero (asset fully depreciated)
                remaining = gross - accum
                if dep > remaining:
                    dep = remaining
            else:
                dep = Decimal('0')

            accum += dep
            year_totals[year] += dep

            # Additions already baked into initial (bulk Y1 transition), so
            # closing_gross == opening_gross for this model.
            rows.append(AssetClassRow(
                year=year,
                opening_gross=opening_gross,
                addition=addition if year == 1 else Decimal('0'),
                opening_accum_dep=opening_accum,
                depreciation=dep,
                closing_gross=gross,
                closing_accum_dep=accum,
                net_block=gross - accum,
            ))

        classes.append(AssetClass(
            key=class_key,
            label=label,
            rate_pct=rate,
            initial_cost=initial,
            rows=rows,
            is_depreciable=is_depreciable,
        ))

    return DepreciationSchedule(
        projection_years=projection_years,
        classes=classes,
        total_depreciation_by_year=year_totals,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Interest schedule (loan amortisation) — used by 3d P&L
# ─────────────────────────────────────────────────────────────────────────────

OPEX_FIELDS = (
    'op_raw_material', 'op_salaries_wages', 'op_electricity', 'op_water', 'op_fuel',
    'op_transportation', 'op_packaging', 'op_repairs_maintenance', 'op_insurance',
    'op_admin_expenses', 'op_marketing_expenses', 'op_communication',
    'op_professional_charges', 'op_miscellaneous',
)


def build_interest_schedule(project, projection_years: int) -> InterestSchedule:
    """Amortise the loan over `tenure_years` after a moratorium.

    Per KAU pre-UAT reply §2.2 (2026-09-08):
      * DEFAULT convention: **Reducing balance with equal annual principal
        instalments** (NABARD-style refinance schedule). Interest computed
        on the outstanding balance each year; declines year-on-year.
      * OPT-IN alternative: **EMI** (equated annual instalment) — total P+I
        stays constant across repayment years. Selected via
        `DPRSectionFinance.repayment_method='emi'` when a specific
        financing scheme / bank requires EMI.

    Interest during moratorium (admin-configurable via DPRConfig
    `moratorium_interest_treatment`, default 'serviced'):
      * 'serviced'   — interest paid periodically; loan balance stays flat.
      * 'capitalised' — interest added to loan outstanding; no cash payment
        during moratorium; post-moratorium principal is calculated on the
        grown balance.

    If no loan is proposed → all rows zero, safe to consume from the P&L.
    """
    fin = getattr(project, 'section_finance', None)
    loan_proposed = getattr(fin, 'loan_proposed', False) if fin else False

    # Loan parameters — user value first, DPRConfig default second
    if loan_proposed and fin:
        loan_amount = _decimal(fin.loan_amount)
        rate = _decimal(fin.rate_of_interest_pct) or DPRConfig.get_decimal('loan_interest_rate_default_pct', Decimal('10.5'))
        tenure = int(fin.repayment_period_years) if fin.repayment_period_years else DPRConfig.get_int('loan_tenure_default_years', 7)
        moratorium = int(fin.moratorium_period_months) if fin.moratorium_period_months is not None else DPRConfig.get_int('loan_moratorium_default_months', 12)
        method = (getattr(fin, 'repayment_method', None) or 'reducing_balance').lower()
    else:
        loan_amount = Decimal('0')
        rate = Decimal('0')
        tenure = 0
        moratorium = 0
        method = 'reducing_balance'

    moratorium_treatment = DPRConfig.get_str('moratorium_interest_treatment', 'serviced').lower()
    # Guard against typos in the config value — anything unrecognised
    # falls back to the safer 'serviced' behaviour so a mis-typed admin
    # setting doesn't silently capitalise interest into the loan balance.
    if moratorium_treatment not in ('serviced', 'capitalised'):
        moratorium_treatment = 'serviced'

    if method == 'emi':
        rows = _amortise_emi(loan_amount, rate, tenure, moratorium, moratorium_treatment, projection_years)
    else:
        method = 'reducing_balance'
        rows = _amortise_reducing_balance(loan_amount, rate, tenure, moratorium, moratorium_treatment, projection_years)

    return InterestSchedule(
        projection_years=projection_years,
        rows=rows,
        loan_amount=loan_amount,
        interest_rate_pct=rate,
        tenure_years=tenure,
        moratorium_months=moratorium,
        repayment_method=method,
        moratorium_interest_treatment=moratorium_treatment,
    )


def _amortise_reducing_balance(
    loan_amount: Decimal,
    rate_pct: Decimal,
    tenure_years: int,
    moratorium_months: int,
    moratorium_treatment: str,
    projection_years: int,
) -> list[InterestScheduleRow]:
    """Equal annual principal + declining interest on the outstanding balance.

    Post-moratorium principal instalment = post-moratorium starting balance
    / remaining repayment years. When `moratorium_treatment='capitalised'`,
    the starting balance is the loan amount grown by accrued moratorium
    interest so the total repayment reflects the capitalised interest.
    """
    rows: list[InterestScheduleRow] = []
    balance = loan_amount
    moratorium_years = moratorium_months // 12
    repayment_years = max(0, tenure_years - moratorium_years) if tenure_years > 0 else 0
    annual_rate = rate_pct / Decimal('100')

    # If moratorium interest is capitalised, project the balance forward
    # through the moratorium first so the post-moratorium equal-principal
    # calculation is based on the grown balance.
    post_moratorium_balance = balance
    if moratorium_treatment == 'capitalised' and moratorium_years > 0 and balance > 0:
        post_moratorium_balance = (
            balance * ((Decimal('1') + annual_rate) ** moratorium_years)
        ).quantize(Decimal('0.01'))
    annual_principal = (
        (post_moratorium_balance / Decimal(repayment_years)).quantize(Decimal('0.01'))
        if repayment_years > 0 else Decimal('0')
    )

    for year in range(1, projection_years + 1):
        opening = balance
        interest = (opening * annual_rate).quantize(Decimal('0.01'))

        if year <= moratorium_years and loan_amount > 0 and moratorium_treatment == 'capitalised':
            # Capitalised — interest added to balance, no cash payment
            principal = Decimal('0')
            balance = (opening + interest).quantize(Decimal('0.01'))
        elif year <= moratorium_years or loan_amount == 0 or year > tenure_years:
            # Serviced (interest paid separately) or no-loan / post-tenure guard
            principal = Decimal('0')
            balance = opening
        else:
            principal = min(annual_principal, opening).quantize(Decimal('0.01'))
            balance = (opening - principal).quantize(Decimal('0.01'))

        if opening == 0:
            interest = Decimal('0')

        rows.append(InterestScheduleRow(
            year=year,
            opening_balance=opening,
            interest=interest,
            principal=principal,
            closing_balance=balance,
        ))
    return rows


def _amortise_emi(
    loan_amount: Decimal,
    rate_pct: Decimal,
    tenure_years: int,
    moratorium_months: int,
    moratorium_treatment: str,
    projection_years: int,
) -> list[InterestScheduleRow]:
    """EMI amortisation (annualised).

    Total annual payment (P + I) stays constant across repayment years.
    Principal share rises + interest share falls year-on-year.

    Standard EMI formula (annualised for DPR granularity):
        EMI = P × r × (1+r)^n / ((1+r)^n − 1)
      where P = principal after moratorium, r = annual rate, n = repayment years.

    Zero-interest edge case: equal-principal fallback so we never divide by zero.
    """
    rows: list[InterestScheduleRow] = []
    balance = loan_amount
    moratorium_years = moratorium_months // 12
    repayment_years = max(0, tenure_years - moratorium_years) if tenure_years > 0 else 0
    annual_rate = rate_pct / Decimal('100')

    # Same capitalisation logic as reducing-balance — grow the EMI base if
    # moratorium interest is capitalised.
    emi_base = balance
    if moratorium_treatment == 'capitalised' and moratorium_years > 0 and balance > 0:
        emi_base = (
            balance * ((Decimal('1') + annual_rate) ** moratorium_years)
        ).quantize(Decimal('0.01'))

    if repayment_years > 0 and loan_amount > 0:
        if annual_rate > 0:
            one_plus_r_n = (Decimal('1') + annual_rate) ** repayment_years
            annual_emi = (
                emi_base * annual_rate * one_plus_r_n / (one_plus_r_n - Decimal('1'))
            ).quantize(Decimal('0.01'))
        else:
            annual_emi = (emi_base / Decimal(repayment_years)).quantize(Decimal('0.01'))
    else:
        annual_emi = Decimal('0')

    for year in range(1, projection_years + 1):
        opening = balance
        interest = (opening * annual_rate).quantize(Decimal('0.01'))

        if year <= moratorium_years and loan_amount > 0 and moratorium_treatment == 'capitalised':
            principal = Decimal('0')
            balance = (opening + interest).quantize(Decimal('0.01'))
        elif year <= moratorium_years or loan_amount == 0 or year > tenure_years:
            principal = Decimal('0')
            balance = opening
        else:
            # Principal share = EMI − interest; guard against final-year rounding.
            principal = (annual_emi - interest).quantize(Decimal('0.01'))
            principal = max(Decimal('0'), min(principal, opening))
            balance = (opening - principal).quantize(Decimal('0.01'))

        if opening == 0:
            interest = Decimal('0')

        rows.append(InterestScheduleRow(
            year=year,
            opening_balance=opening,
            interest=interest,
            principal=principal,
            closing_balance=balance,
        ))
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Profit & Loss projection (Phase 3d)
# ─────────────────────────────────────────────────────────────────────────────

def _sum_year1_revenue(project) -> Decimal:
    """Sum Y1 revenue across all revenue_assumptions on the finance section."""
    fin = getattr(project, 'section_finance', None)
    if fin is None:
        return Decimal('0')
    total = Decimal('0')
    for ra in fin.revenue_assumptions.all():
        # Prefer explicit annual_sales_revenue if the user entered it; else qty * price
        if ra.annual_sales_revenue:
            total += _decimal(ra.annual_sales_revenue)
        else:
            qty = _decimal(ra.year1_sales_quantity)
            price = _decimal(ra.expected_selling_price)
            total += qty * price
    return total


def _weighted_revenue_growth_rate(project) -> Decimal:
    """Weighted-average YoY revenue growth from revenue_assumptions.
    Weight is Y1 revenue. Falls back to `inflation_rate_pct` from DPRConfig
    when no explicit growth rate is set."""
    fin = getattr(project, 'section_finance', None)
    if fin is None:
        return DPRConfig.get_decimal('inflation_rate_pct', Decimal('6'))
    total_rev = Decimal('0')
    weighted_rate = Decimal('0')
    default_rate = DPRConfig.get_decimal('inflation_rate_pct', Decimal('6'))
    for ra in fin.revenue_assumptions.all():
        if ra.annual_sales_revenue:
            rev = _decimal(ra.annual_sales_revenue)
        else:
            rev = _decimal(ra.year1_sales_quantity) * _decimal(ra.expected_selling_price)
        rate = _decimal(ra.expected_annual_growth_rate_pct) if ra.expected_annual_growth_rate_pct else default_rate
        total_rev += rev
        weighted_rate += rev * rate
    return (weighted_rate / total_rev) if total_rev > 0 else default_rate


def _year1_opex(project) -> Decimal:
    """Sum all Y1 opex fields."""
    fin = getattr(project, 'section_finance', None)
    total, _ = _sum_fields(fin, OPEX_FIELDS)
    return total


def build_profit_loss(
    project,
    depreciation: DepreciationSchedule,
    interest: InterestSchedule,
    projection_years: int,
) -> ProfitLoss:
    """N-year P&L projection.

    Revenue: Y1 from revenue_assumptions; each subsequent year escalated by
             weighted-average growth rate (falls back to inflation_rate_pct).
    Opex:    Y1 from opex fields; escalated by inflation_rate_pct each year.
    Depreciation: from 3c DepreciationSchedule.total_depreciation_by_year.
    Interest: from InterestSchedule (loan amortisation).
    Tax: PBT × tax_rate_pct (from DPRConfig). Zero when PBT is negative
         (no MAT / carry-forward modelled at this pass — noted for 3h ratios).
    """
    revenue_y1 = _sum_year1_revenue(project)
    opex_y1 = _year1_opex(project)
    revenue_growth = _weighted_revenue_growth_rate(project)
    inflation = DPRConfig.get_decimal('inflation_rate_pct', Decimal('6'))
    tax_rate = DPRConfig.get_decimal('tax_rate_pct', Decimal('25.17'))

    rev_multiplier = Decimal('1') + (revenue_growth / Decimal('100'))
    opex_multiplier = Decimal('1') + (inflation / Decimal('100'))

    rows: list[ProfitLossRow] = []
    cumulative_pat = Decimal('0')
    cumulative_pat_by_year: dict[int, Decimal] = {}
    current_rev = revenue_y1
    current_opex = opex_y1

    for year in range(1, projection_years + 1):
        if year > 1:
            current_rev = (current_rev * rev_multiplier).quantize(Decimal('0.01'))
            current_opex = (current_opex * opex_multiplier).quantize(Decimal('0.01'))

        dep = depreciation.total_depreciation_by_year.get(year, Decimal('0'))
        int_row = interest.rows[year - 1] if year - 1 < len(interest.rows) else None
        int_charge = int_row.interest if int_row else Decimal('0')

        ebitda = current_rev - current_opex
        ebit = ebitda - dep
        pbt = ebit - int_charge
        tax = (pbt * tax_rate / Decimal('100')).quantize(Decimal('0.01')) if pbt > 0 else Decimal('0')
        pat = pbt - tax

        cumulative_pat += pat
        cumulative_pat_by_year[year] = cumulative_pat

        rows.append(ProfitLossRow(
            year=year,
            revenue=current_rev,
            operating_cost=current_opex,
            ebitda=ebitda,
            depreciation=dep,
            ebit=ebit,
            interest=int_charge,
            pbt=pbt,
            tax=tax,
            pat=pat,
        ))

    return ProfitLoss(
        projection_years=projection_years,
        rows=rows,
        total_pat=cumulative_pat,
        cumulative_pat_by_year=cumulative_pat_by_year,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Cash flow projection (Phase 3e — indirect method)
# ─────────────────────────────────────────────────────────────────────────────

def build_cash_flow(
    cost: ProjectCostBreakdown,
    mof: MeansOfFinanceBreakdown,
    profit_loss: ProfitLoss,
    interest: InterestSchedule,
    projection_years: int,
) -> CashFlow:
    """N+1-year cash flow using the indirect method.

    Y0 (construction period):
        - PAT / depreciation are zero (no operations)
        - Investing: entire capex outflow, capitalised at project start
        - Financing: entire MoF inflow (contributions + loan + subsidy)
        - Working capital margin absorbed into Y0 investing (initial WC)
        - Net Y0 cash flow = MoF − Cost. Zero when balanced (variance = 0).

    Y1..YN (operations):
        - Operating: PAT + depreciation (non-cash addback). WC change assumed
          zero at this pass (constant WC). See note below for the upgrade.
        - Investing: zero (no replacement capex modelled at this pass —
          upgrade path when we add asset-life driven replacement capex).
        - Financing: −principal_repayment. No new borrowings modelled.

    Simplifications flagged for future refinement:
      - Constant working capital across years (real DPRs grow WC with revenue).
        Upgrade: compute WC as X days of raw material + Y days of finished goods
        against escalated revenue → derive year-over-year WC delta.
      - No replacement capex — realistic 10-yr projection would refresh
        equipment mid-way. Depreciation schedule already handles life-out;
        replacement capex fits naturally when we add it.
      - No dividend distribution — retained earnings accumulate; upgrade
        adds admin-configurable dividend policy.
    """
    rows: list[CashFlowRow] = []

    # ── Y0 — construction period ────────────────────────────────────────
    # The full MoF hits the bank in Y0 and the full capex leaves; WC margin
    # sits in the bank until operations begin (already inside cost.total via
    # `cost_margin_for_working_capital`).
    y0_capex = cost.total
    y0_mof_inflow = mof.total
    y0_net = y0_mof_inflow - y0_capex
    rows.append(CashFlowRow(
        year=0,
        pat=Decimal('0'),
        depreciation_addback=Decimal('0'),
        working_capital_change=Decimal('0'),
        cash_from_operations=Decimal('0'),
        capex=-y0_capex,
        cash_from_investing=-y0_capex,
        mof_inflow=y0_mof_inflow,
        loan_principal_repayment=Decimal('0'),
        cash_from_financing=y0_mof_inflow,
        net_cash_flow=y0_net,
        opening_cash=Decimal('0'),
        closing_cash=y0_net,
    ))

    # ── Y1..YN — operations ─────────────────────────────────────────────
    cash_balance = y0_net
    for year in range(1, projection_years + 1):
        pl_row = profit_loss.rows[year - 1]
        int_row = interest.rows[year - 1] if year - 1 < len(interest.rows) else None
        principal = int_row.principal if int_row else Decimal('0')

        cfo = pl_row.pat + pl_row.depreciation  # + WC change (assumed 0)
        cfi = Decimal('0')                       # no replacement capex modelled
        cff = -principal
        net = cfo + cfi + cff

        opening = cash_balance
        cash_balance = opening + net

        rows.append(CashFlowRow(
            year=year,
            pat=pl_row.pat,
            depreciation_addback=pl_row.depreciation,
            working_capital_change=Decimal('0'),
            cash_from_operations=cfo,
            capex=Decimal('0'),
            cash_from_investing=cfi,
            mof_inflow=Decimal('0'),
            loan_principal_repayment=-principal,
            cash_from_financing=cff,
            net_cash_flow=net,
            opening_cash=opening,
            closing_cash=cash_balance,
        ))

    return CashFlow(
        projection_years=projection_years,
        rows=rows,
        ending_cash=cash_balance,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Balance sheet assembly + invariant (Phase 3f — A.3 flagship)
# ─────────────────────────────────────────────────────────────────────────────

# Grouping MoF fields into their BS-side categories.
_EQUITY_FIELDS = frozenset({
    'mof_promoters_contribution',
    'mof_share_capital',
    'mof_internal_accruals',
})
_CAPITAL_RESERVE_FIELDS = frozenset({
    'mof_government_grant',
    'mof_government_subsidy',
    'mof_csr_support',
    'mof_nabard_assistance',
    'mof_other_financial_assistance',
})
_TERM_LOAN_FIELDS = frozenset({
    'mof_bank_term_loan',
    'mof_venture_capital',        # treated as long-term liability at first pass
})
_OTHER_LIABILITY_FIELDS = frozenset({
    'mof_working_capital_loan',
    'mof_other_sources',
})


def _sum_by_group(mof: MeansOfFinanceBreakdown, group: frozenset[str]) -> Decimal:
    return sum((v for k, v in mof.by_field.items() if k in group), start=Decimal('0'))


def build_balance_sheet(
    cost: ProjectCostBreakdown,
    mof: MeansOfFinanceBreakdown,
    depreciation: DepreciationSchedule,
    interest: InterestSchedule,
    profit_loss: ProfitLoss,
    cash_flow: CashFlow,
    projection_years: int,
) -> BalanceSheet:
    """Build the N+1 year balance sheet and enforce A.3's

        Assets = Equity + Liabilities

    invariant for every year. Callers can trust `all_years_balanced` — if
    False the calc engine has a bug we need to fix before shipping the DPR.

    Timing model (matches 3c CWIP treatment):
        Year 0 (end of construction / start of operations):
            - Land is a direct fixed asset (bought outright, no CWIP)
            - Buildings + machinery + equipment + pre-operative expenses
              sit in CWIP awaiting commissioning
            - Cash = MoF − (all cost outflows so far) = closing cash from
              CashFlow row 0
            - Retained earnings = 0 (no operations yet)
        Year 1..N (end of each operational year):
            - CWIP → 0 (bulk-transitioned to fixed assets at Y1 start)
            - Gross fixed assets = sum of initial_cost for depreciable classes
            - Accum dep = running total from depreciation schedule
            - Cash = CashFlow.closing_cash for that year
            - Retained earnings = cumulative PAT to date
            - Term loan outstanding = InterestSchedule.closing_balance
    """
    # ── Static equity + liability inputs (constant over years) ──────────
    promoter_equity = _sum_by_group(mof, _EQUITY_FIELDS)
    capital_reserve = _sum_by_group(mof, _CAPITAL_RESERVE_FIELDS)
    initial_term_loan = _sum_by_group(mof, _TERM_LOAN_FIELDS)
    other_liabilities = _sum_by_group(mof, _OTHER_LIABILITY_FIELDS)

    # ── Asset-side building blocks ──────────────────────────────────────
    # Land: direct fixed asset from Y0 (never in CWIP)
    land_class = next((c for c in depreciation.classes if c.key == 'land'), None)
    land_value = land_class.initial_cost if land_class else Decimal('0')

    # CWIP at Y0 = every depreciable class's initial cost + pre-operative +
    # 'other' capex. Everything except land. (Working capital margin sits on
    # the asset side as WC/cash, not CWIP.)
    cwip_y0 = sum(
        (c.initial_cost for c in depreciation.classes if c.key != 'land'),
        start=Decimal('0'),
    )

    # Post-Y0 gross FA = same set as Y0 CWIP (bulk transition at Y1 start)
    gross_fa_after_y0 = cwip_y0

    # Working capital = the margin the FPO earmarked
    wc_margin = cost.by_field.get('cost_margin_for_working_capital', Decimal('0'))

    rows: list[BalanceSheetRow] = []
    max_delta = Decimal('0')

    for year in range(0, projection_years + 1):
        # ── Assets ──
        if year == 0:
            land = land_value
            cwip = cwip_y0
            gross_fa = Decimal('0')
            accum_dep = Decimal('0')
        else:
            land = land_value
            cwip = Decimal('0')
            gross_fa = gross_fa_after_y0
            # Cumulative depreciation through end of `year`
            accum_dep = sum(
                (depreciation.total_depreciation_by_year.get(y, Decimal('0'))
                 for y in range(1, year + 1)),
                start=Decimal('0'),
            )
        net_fa = gross_fa - accum_dep
        cash = cash_flow.rows[year].closing_cash if year < len(cash_flow.rows) else Decimal('0')
        wc = wc_margin
        total_assets = land + cwip + net_fa + cash + wc

        # ── Equity ──
        retained = profit_loss.cumulative_pat_by_year.get(year, Decimal('0'))
        total_equity = promoter_equity + capital_reserve + retained

        # ── Liabilities ──
        if year == 0:
            loan_out = initial_term_loan
        else:
            int_row = interest.rows[year - 1] if year - 1 < len(interest.rows) else None
            loan_out = int_row.closing_balance if int_row else initial_term_loan
        total_liabilities = loan_out + other_liabilities

        total_eq_and_liab = total_equity + total_liabilities
        delta = total_assets - total_eq_and_liab
        if abs(delta) > max_delta:
            max_delta = abs(delta)

        rows.append(BalanceSheetRow(
            year=year,
            land=land,
            cwip=cwip,
            gross_fixed_assets=gross_fa,
            accumulated_depreciation=accum_dep,
            net_fixed_assets=net_fa,
            working_capital=wc,
            cash_and_bank=cash,
            total_assets=total_assets,
            promoter_equity=promoter_equity,
            capital_reserve=capital_reserve,
            retained_earnings=retained,
            total_equity=total_equity,
            term_loan_outstanding=loan_out,
            other_liabilities=other_liabilities,
            total_liabilities=total_liabilities,
            total_equity_and_liabilities=total_eq_and_liab,
            invariant_delta=delta,
            invariant_ok=abs(delta) < Decimal('1'),
        ))

    all_balanced = all(r.invariant_ok for r in rows)
    return BalanceSheet(
        projection_years=projection_years,
        rows=rows,
        all_years_balanced=all_balanced,
        max_invariant_delta=max_delta,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Financial ratios (Phase 3h — NPV, IRR, DSCR, payback, break-even)
# ─────────────────────────────────────────────────────────────────────────────

def _npv_raw(cash_flows: list[Decimal], discount_rate_pct: Decimal) -> Decimal:
    """Raw NPV (no quantize). Internal — used in IRR bisection hot path where
    quantizing to 0.01 at extreme rates hits Decimal precision limits."""
    r = Decimal('1') + (discount_rate_pct / Decimal('100'))
    total = Decimal('0')
    factor = Decimal('1')
    for cf in cash_flows:
        total += cf / factor
        factor *= r
    return total


def _npv(cash_flows: list[Decimal], discount_rate_pct: Decimal) -> Decimal:
    """Public NPV: Σ CF_t / (1+r)^t where t = 0..N. Quantized to paise.

    `cash_flows[0]` is the Y0 flow (typically the initial outflow).
    Discount rate is a percentage (e.g. 12 for 12%).
    """
    return _npv_raw(cash_flows, discount_rate_pct).quantize(Decimal('0.01'))


def _irr(cash_flows: list[Decimal]) -> tuple[Optional[Decimal], bool]:
    """Bisection IRR — pure Python, avoids numpy dependency.

    Search range constrained to -95% .. 200% — covers essentially every
    realistic project IRR while avoiding Decimal-precision blowout at
    extreme discount factors (e.g. at -99% the factor is 1/0.01 = 100 and
    100^10 exceeds Decimal's default context precision).
    Returns (rate_pct, converged). Rate is None + converged=False when:
      - all cash flows are same sign (no crossover exists)
      - bisection fails to converge within 100 iterations
    """
    has_pos = any(cf > 0 for cf in cash_flows)
    has_neg = any(cf < 0 for cf in cash_flows)
    if not (has_pos and has_neg):
        return None, False

    low = Decimal('-95')
    high = Decimal('200')
    tol = Decimal('0.001')

    npv_low = _npv_raw(cash_flows, low)
    npv_high = _npv_raw(cash_flows, high)
    if (npv_low > 0) == (npv_high > 0):
        return None, False

    for _ in range(100):
        mid = (low + high) / Decimal('2')
        npv_mid = _npv_raw(cash_flows, mid)
        if abs(npv_mid) < Decimal('1'):
            return mid.quantize(Decimal('0.01')), True
        if (npv_mid > 0) == (npv_low > 0):
            low = mid
            npv_low = npv_mid
        else:
            high = mid
            npv_high = npv_mid
        if abs(high - low) < tol:
            return ((low + high) / Decimal('2')).quantize(Decimal('0.01')), True

    return None, False


def _free_cash_flows(cash_flow: CashFlow) -> list[Decimal]:
    """Free cash flows for NPV/IRR — excludes financing activities so we
    measure project economics independent of how it was financed.
    Free CF = CFO + CFI (i.e. operating + investing).
    Y0: full capex outflow. Y1..YN: CFO from operations.
    """
    return [(row.cash_from_operations + row.cash_from_investing) for row in cash_flow.rows]


def _build_dscr(profit_loss: ProfitLoss, interest: InterestSchedule) -> tuple[list[DSCRRow], Optional[Decimal], Optional[Decimal]]:
    """Per-year DSCR + min/avg across years with actual debt service."""
    rows: list[DSCRRow] = []
    dscrs_for_agg: list[Decimal] = []
    for pl_row, int_row in zip(profit_loss.rows, interest.rows):
        interest_charge = int_row.interest
        principal = int_row.principal
        denom = interest_charge + principal
        numer = pl_row.pat + pl_row.depreciation + interest_charge
        dscr = None
        if denom > 0:
            dscr = (numer / denom).quantize(Decimal('0.01'))
            dscrs_for_agg.append(dscr)
        rows.append(DSCRRow(
            year=pl_row.year,
            numerator=numer,
            denominator=denom,
            dscr=dscr,
        ))

    if not dscrs_for_agg:
        return rows, None, None
    min_dscr = min(dscrs_for_agg)
    avg_dscr = (sum(dscrs_for_agg, start=Decimal('0')) / Decimal(len(dscrs_for_agg))).quantize(Decimal('0.01'))
    return rows, min_dscr, avg_dscr


def _payback_period(free_cash_flows: list[Decimal]) -> Optional[Decimal]:
    """Simple payback (undiscounted): year at which cumulative FCF crosses
    zero. Linear interpolation within the crossing year for a fractional
    answer. Returns None when cumulative FCF never turns positive.
    """
    cumulative = Decimal('0')
    for i, cf in enumerate(free_cash_flows):
        prior = cumulative
        cumulative += cf
        if cumulative >= 0 and prior < 0:
            # Crossed zero in year `i` — interpolate within the year
            # fraction = |prior| / cf (portion of this year's inflow needed)
            if cf > 0:
                fraction = -prior / cf
                # i is the year index in free_cash_flows (0-indexed);
                # for FCF list where index 0 = Y0, index k = Yk,
                # the crossing happens somewhere within Yk.
                return (Decimal(i - 1) + fraction).quantize(Decimal('0.01')) if i > 0 else Decimal('0')
            return Decimal(i)
    return None


def _break_even_year(profit_loss: ProfitLoss) -> Optional[int]:
    """First year in which cumulative PAT >= 0. Loss-making projects that
    never turn cumulative-positive return None."""
    for year, cum in sorted(profit_loss.cumulative_pat_by_year.items()):
        if cum >= 0:
            return year
    return None


def build_ratios(
    profit_loss: ProfitLoss,
    interest: InterestSchedule,
    cash_flow: CashFlow,
) -> FinancialRatios:
    """Assemble the appraisal ratios block."""
    discount_rate = DPRConfig.get_decimal('discount_rate_pct', Decimal('12'))
    fcfs = _free_cash_flows(cash_flow)

    npv = _npv(fcfs, discount_rate)
    irr, irr_converged = _irr(fcfs)
    dscr_rows, dscr_min, dscr_avg = _build_dscr(profit_loss, interest)
    payback = _payback_period(fcfs)
    break_even = _break_even_year(profit_loss)

    return FinancialRatios(
        discount_rate_pct=discount_rate,
        npv=npv,
        irr_pct=irr,
        irr_converged=irr_converged,
        dscr_rows=dscr_rows,
        dscr_min=dscr_min,
        dscr_avg=dscr_avg,
        payback_period_years=payback,
        break_even_year=break_even,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Risk assessment (Phase 4 — RCD B.9)
# ─────────────────────────────────────────────────────────────────────────────

# Precedence used to escalate a category to its worst risk.
_RISK_ORDER = {'low': 0, 'moderate': 1, 'high': 2}
_RISK_LABELS = {'low': 'Low', 'moderate': 'Moderate', 'high': 'High'}

# 6 categories from RISK_CATEGORY_CHOICES on DPRRiskItem — mirrored here so
# the risk section can be empty and we still list categories in the assessment.
_RISK_CATEGORIES: list[tuple[str, str]] = [
    ('production',    'Production Risk'),
    ('market',        'Market Risk'),
    ('financial',     'Financial Risk'),
    ('institutional', 'Institutional Risk'),
    ('environmental', 'Environmental Risk'),
    ('regulatory',    'Regulatory Risk'),
]


def _pull_risks_from_other_sections(project) -> list[AutoPulledRisk]:
    """Collect risks captured in Raw Material / Market / Technology / ESS
    sections and shape them as `AutoPulledRisk` records. Called by
    `build_risk_assessment` to close the KAU 2026-09-10 gap (risks in 5
    different places without cross-linking).

    Category mapping:
      - Raw Material risks    -> production category
      - Marketing risks       -> market category
      - Technology risks      -> production category (tech-failure branch)
      - ESS climate risks     -> environmental category

    Returns [] gracefully when the source sections don't exist yet (fresh
    projects) — the calc engine already tolerates missing sections.
    """
    from apps.database.models import (
        DPRRawMaterialRisk, DPRMarketingRisk,
        DPRTechnologyRisk, DPRClimateRiskSelection,
    )
    from apps.database.models.dpr.raw_material import RISK_TYPE_CHOICES as _RM_CHOICES
    from apps.database.models.dpr.market import MARKETING_RISK_CHOICES as _MK_CHOICES
    from apps.database.models.dpr.technology import TECH_RISK_CHOICES as _TECH_CHOICES

    _rm_labels = dict(_RM_CHOICES)
    _mk_labels = dict(_MK_CHOICES)
    _tech_labels = dict(_TECH_CHOICES)

    out: list[AutoPulledRisk] = []

    # Raw Material section — §2.3.10 supply/procurement risks
    rm_section = getattr(project, 'section_raw_material', None)
    if rm_section:
        for r in DPRRawMaterialRisk.objects.filter(section=rm_section):
            code = r.risk_type
            label = _rm_labels.get(code, code) if code != 'other' else (r.risk_type_other or 'Other')
            out.append(AutoPulledRisk(
                source='raw_material',
                source_label='Raw Material',
                category='production',
                category_label='Production Risk',
                risk_code=code,
                risk_label=label,
                risk_description=r.existing_practices or r.previous_experience or '',
                mitigation_strategy=r.mitigation_strategy or '',
            ))

    # Market section — §2.3.11 marketing risks
    mk_section = getattr(project, 'section_market', None)
    if mk_section:
        for r in DPRMarketingRisk.objects.filter(section=mk_section):
            code = r.risk_type
            label = _mk_labels.get(code, code) if code != 'other' else (r.risk_type_other or 'Other')
            out.append(AutoPulledRisk(
                source='market',
                source_label='Market',
                category='market',
                category_label='Market Risk',
                risk_code=code,
                risk_label=label,
                risk_description=r.existing_practices or '',
                mitigation_strategy=r.mitigation_strategy or '',
            ))

    # Technology section — §2.3.12 tech-failure risks. Different shape:
    # each risk is attached to a specific `DPRTechnology` (not directly to
    # the section), so we walk the M2M.
    tech_section = getattr(project, 'section_technology', None)
    if tech_section:
        for tech in tech_section.technologies.all():
            for r in DPRTechnologyRisk.objects.filter(technology=tech):
                code = r.risk_type
                label = _tech_labels.get(code, code) if code != 'other' else (r.risk_type_other or 'Other')
                out.append(AutoPulledRisk(
                    source='technology',
                    source_label='Technology',
                    category='production',
                    category_label='Production Risk',
                    risk_code=code,
                    risk_label=label,
                    risk_description=r.existing_practice or '',
                    mitigation_strategy=r.mitigation_measure or '',
                ))

    # ESS section — §2.3.20 Cat C climate risks. Different shape: FK to
    # `DPRClimateRisk` master lookup (not a text choice).
    ess_section = getattr(project, 'section_ess', None)
    if ess_section:
        for r in DPRClimateRiskSelection.objects.filter(section=ess_section).select_related('risk'):
            label = getattr(r.risk, 'name', None) or getattr(r.risk, 'code', 'Climate risk')
            if r.risk_other:
                label = r.risk_other
            out.append(AutoPulledRisk(
                source='ess_climate',
                source_label='ESS (Climate)',
                category='environmental',
                category_label='Environmental Risk',
                risk_code=getattr(r.risk, 'code', 'other'),
                risk_label=label,
                risk_description=r.expected_impact or '',
                mitigation_strategy=r.proposed_mitigation_strategy or '',
            ))

    return out


def build_risk_assessment(project) -> RiskAssessment:
    """Read the project's risk items, look each up in the matrix, aggregate
    per category (worst-case), and derive overall project rating.

    Categories without any user-entered risk are treated as `low` (per RCD:
    'All assessed categories are Low' → overall Low). Categories with risks
    but no probability/impact assessment carry an `unscored_note` so the PDF
    can flag them for user attention.

    KAU 2026-09-10 gap-close: also pulls risks captured in Raw Material,
    Market, Technology, and ESS (climate) sections. Auto-pulled risks are
    counted in the per-category `risk_count` (not scored — no probability x
    impact until the FPO promotes them to §2.3.22 items). Full list surfaces
    on the FE as a read-only "risks from other sections" card and in the PDF
    risk chapter as an additional subsection.
    """
    from apps.database.models import DPRRiskMatrixCell

    fin_section = getattr(project, 'section_risk', None)
    items = list(fin_section.items.all()) if fin_section else []

    # Pull risks from Raw Material / Market / Technology / ESS. Kept as a
    # list ordered by source so the FE can group + display consistently.
    auto_pulled = _pull_risks_from_other_sections(project)

    # Bucket by category → list of (probability, impact)
    buckets: dict[str, list] = {code: [] for code, _ in _RISK_CATEGORIES}
    for it in items:
        if it.risk_category in buckets:
            buckets[it.risk_category].append(it)

    # Auto-pulled risks count towards per-category `risk_count` even though
    # they don't have probability x impact scoring yet — the FPO still needs
    # to know these risks exist against the category.
    auto_bucket_counts: dict[str, int] = {code: 0 for code, _ in _RISK_CATEGORIES}
    for ap in auto_pulled:
        if ap.category in auto_bucket_counts:
            auto_bucket_counts[ap.category] += 1

    total_added = len(items) + len(auto_pulled)
    total_scored = 0
    categories: list[RiskCategoryScore] = []
    overall_rank = 0  # 0 = low, 1 = moderate, 2 = high

    for code, label in _RISK_CATEGORIES:
        rows = buckets[code]
        class_counts = {'low': 0, 'moderate': 0, 'high': 0}
        cat_rank = 0
        scored_count = 0
        for it in rows:
            cls = DPRRiskMatrixCell.get_risk_class(it.probability, it.impact)
            if cls is None:
                continue
            scored_count += 1
            class_counts[cls] += 1
            cat_rank = max(cat_rank, _RISK_ORDER.get(cls, 0))

        cat_class = _rank_to_class(cat_rank)
        total_scored += scored_count
        overall_rank = max(overall_rank, cat_rank)

        unscored_note: Optional[str] = None
        if rows and scored_count == 0:
            unscored_note = (
                f'{len(rows)} risk(s) added to this category but probability + '
                'impact were left blank. Enter both to score.'
            )

        # Include auto-pulled risks in the count for this category — the FPO
        # gets an accurate picture of the total risk exposure without having
        # to manually re-enter them in §2.3.22.
        categories.append(RiskCategoryScore(
            category=code,
            category_label=label,
            risk_count=len(rows) + auto_bucket_counts[code],
            scored_count=scored_count,
            class_counts=class_counts,
            category_class=cat_class,
            unscored_note=unscored_note,
        ))

    cell_count = DPRRiskMatrixCell.objects.count() if project.pk else 0
    matrix_note = (
        f'{cell_count} matrix cells configured. Admin edits at /api/admin/dpr/risk-matrix/.'
    )

    return RiskAssessment(
        categories=categories,
        overall_class=_rank_to_class(overall_rank),
        total_risks_added=total_added,
        total_risks_scored=total_scored,
        matrix_note=matrix_note,
        auto_pulled=auto_pulled,
    )


def _rank_to_class(rank: int) -> str:
    for cls, r in _RISK_ORDER.items():
        if r == rank:
            return cls
    return 'low'


# ─────────────────────────────────────────────────────────────────────────────
# Top-level compute — the one caller downstream code should use
# ─────────────────────────────────────────────────────────────────────────────

def compute(project) -> CalculationResult:
    """Run the full DPR calculation for one project.

    Currently returns cost + MoF + variance + capital schedule (Phases 3a+3b).
    Sub-phases 3c–3h populate the rest of CalculationResult over subsequent
    sessions.

    Callers should treat this as the single entry point — do not call
    `compute_cost_and_mof` or `build_capital_schedule` directly from views /
    PDF renderers.
    """
    projection_years = DPRConfig.get_int('projection_years', 10)
    implementation_months = DPRConfig.get_int('implementation_period_months', 12)

    cost, mof, variance = compute_cost_and_mof(project)
    user_estimate_variance = compute_user_estimate_variance(project)
    capital_schedule = build_capital_schedule(project, cost, mof, implementation_months)
    depreciation = build_depreciation_schedule(cost, projection_years)
    interest = build_interest_schedule(project, projection_years)
    profit_loss = build_profit_loss(project, depreciation, interest, projection_years)
    cash_flow = build_cash_flow(cost, mof, profit_loss, interest, projection_years)
    balance_sheet = build_balance_sheet(
        cost, mof, depreciation, interest, profit_loss, cash_flow, projection_years,
    )
    ratios = build_ratios(profit_loss, interest, cash_flow)
    risk_assessment = build_risk_assessment(project)

    return CalculationResult(
        projection_years=projection_years,
        cost=cost,
        mof=mof,
        variance=variance,
        user_estimate_variance=user_estimate_variance,
        capital_schedule=capital_schedule,
        depreciation=depreciation,
        interest_schedule=interest,
        profit_loss=profit_loss,
        cash_flow=cash_flow,
        balance_sheet=balance_sheet,
        ratios=ratios,
        risk_assessment=risk_assessment,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Debug helper — one-line summary of a result for logs / shell inspection
# ─────────────────────────────────────────────────────────────────────────────

def summary(result: CalculationResult) -> str:
    v = result.variance
    variance_line = (
        f'balanced' if v.delta == 0
        else f'{v.pct:.2f}% ({"OK" if not v.exceeds_threshold else f"exceeds {v.threshold_pct}%"})'
    )
    sched = result.capital_schedule
    if sched:
        source = 'estimated' if sched.is_estimated else 'from tranches'
        sched_line = (
            f' | Schedule={sched.implementation_period_months}mo ({source}, '
            f'final={sched.final_cost:,.0f}/{sched.final_mof:,.0f})'
        )
    else:
        sched_line = ''
    dep = result.depreciation
    dep_line = (
        f' | Dep Y1=₹{dep.total_depreciation_by_year.get(1, Decimal(0)):,.0f}'
        if dep else ''
    )
    pl = result.profit_loss
    pl_line = (
        f' | PAT Y1=₹{pl.rows[0].pat:,.0f} Y{pl.projection_years}=₹{pl.rows[-1].pat:,.0f}'
        if pl and pl.rows else ''
    )
    cf = result.cash_flow
    cf_line = (
        f' | End cash=₹{cf.ending_cash:,.0f}' if cf else ''
    )
    bs = result.balance_sheet
    if bs:
        bs_ok = 'balanced ✓' if bs.all_years_balanced else f'⚠ max delta=₹{bs.max_invariant_delta:.2f}'
        bs_line = f' | BS={bs_ok}'
    else:
        bs_line = ''
    ratios = result.ratios
    if ratios:
        irr_str = f'{ratios.irr_pct}%' if ratios.irr_pct is not None else 'n/a'
        payback_str = f'{ratios.payback_period_years}y' if ratios.payback_period_years is not None else 'n/a'
        dscr_str = f'{ratios.dscr_min}' if ratios.dscr_min is not None else 'n/a'
        ratios_line = f' | NPV=₹{ratios.npv:,.0f} IRR={irr_str} DSCR-min={dscr_str} Payback={payback_str}'
    else:
        ratios_line = ''
    ra = result.risk_assessment
    risk_line = (
        f' | Risk={_RISK_LABELS.get(ra.overall_class, "?")} ({ra.total_risks_scored}/{ra.total_risks_added} scored)'
        if ra else ''
    )
    return (
        f'Cost=₹{result.cost.total:,.0f} | '
        f'MoF=₹{result.mof.total:,.0f} | '
        f'Variance={variance_line} | '
        f'Projection={result.projection_years}y'
        f'{sched_line}'
        f'{dep_line}'
        f'{pl_line}'
        f'{cf_line}'
        f'{bs_line}'
        f'{ratios_line}'
        f'{risk_line}'
    )
