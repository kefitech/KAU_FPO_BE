"""
DPR §2.3.18 — Financial Information and Means of Finance.

Three tables:
    DPRSectionFinance          — 1:1 (Cat A cost + Cat B finance + Cat C WC + Cat D opex + Cat F loan + Cat G subsidy + Cat H toggle + Cat I assumptions)
    DPRRevenueAssumption       — N per section (Cat E — per-product revenue)
    DPRFinancialYearHistory    — N per section (Cat H additional — last 3 years for operational FPOs)

Feeds the future calculation engine (Ch 4 of KAU spec). Per KAU remarks,
values collected in previous sections (machinery cost, civil cost, manpower cost)
will be auto-populated here by the calc engine at DPR generation time.
"""

from django.db import models

from apps.core.models.base import TimeStampedModel, AuditModel


LOAN_TYPE_CHOICES = [
    ('term_loan',        'Term Loan'),
    ('working_capital',  'Working Capital Loan'),
    ('composite',        'Composite Loan'),
    ('cash_credit',      'Cash Credit'),
    ('other',            'Others'),
]

REPAYMENT_FREQUENCY_CHOICES = [
    ('monthly',     'Monthly'),
    ('quarterly',   'Quarterly'),
    ('half_yearly', 'Half-yearly'),
    ('yearly',      'Yearly'),
]

SUBSIDY_STATUS_CHOICES = [
    ('not_applied', 'Not Yet Applied'),
    ('applied',     'Applied'),
    ('under_review', 'Under Review'),
    ('approved',    'Approved'),
    ('rejected',    'Rejected'),
    ('disbursed',   'Disbursed'),
]


class DPRSectionFinance(TimeStampedModel, AuditModel):
    """§2.3.18 section — one row per project."""

    project = models.OneToOneField(
        'database.DPRProject',
        on_delete=models.CASCADE,
        related_name='section_finance',
    )

    # ── Cat A: Estimated Project Cost ──
    cost_land_purchase = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    cost_land_development = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    cost_civil_works = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    cost_buildings = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    cost_plant_machinery = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    cost_equipment = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    cost_utilities = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    cost_other_capex = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    cost_site_development = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    cost_furniture_fixtures = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    cost_office_equipment = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    cost_vehicles = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    cost_electrification = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    cost_water_supply = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    cost_pre_operative_expenses = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    cost_preliminary_expenses = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    cost_technical_consultancy = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    cost_contingencies = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    cost_margin_for_working_capital = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)

    # ── Cat B: Means of Finance ──
    mof_promoters_contribution = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    mof_bank_term_loan = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    mof_government_grant = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    mof_government_subsidy = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    mof_other_sources = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    mof_share_capital = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    mof_internal_accruals = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    mof_working_capital_loan = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    mof_venture_capital = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    mof_csr_support = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    mof_nabard_assistance = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    mof_other_financial_assistance = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)

    # ── Cat C: Working Capital Requirement (annual) ──
    wc_raw_materials = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    wc_labour_salaries = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    wc_utilities = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    wc_transportation = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    wc_admin_expenses = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    wc_marketing_expenses = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    wc_packaging_materials = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    wc_consumables = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    wc_repairs_maintenance = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    wc_miscellaneous = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    credit_period_from_suppliers_days = models.IntegerField(null=True, blank=True)
    credit_period_to_customers_days = models.IntegerField(null=True, blank=True)
    inventory_holding_period_days = models.IntegerField(null=True, blank=True)
    cash_requirement = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    working_capital_cycle_days = models.IntegerField(null=True, blank=True)

    # ── Cat D: Operating Expenses (annual) ──
    op_raw_material = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    op_salaries_wages = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    op_electricity = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    op_water = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    op_fuel = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    op_transportation = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    op_packaging = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    op_repairs_maintenance = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    op_insurance = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    op_admin_expenses = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    op_marketing_expenses = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    op_communication = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    op_professional_charges = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    op_miscellaneous = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)

    # ── Cat F: Loan Details ──
    loan_proposed = models.BooleanField(default=False)
    loan_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    loan_type = models.CharField(max_length=20, choices=LOAN_TYPE_CHOICES, blank=True)
    lending_institution = models.CharField(max_length=300, blank=True)
    rate_of_interest_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    moratorium_period_months = models.IntegerField(null=True, blank=True)
    repayment_period_years = models.IntegerField(null=True, blank=True)
    repayment_frequency = models.CharField(max_length=20, choices=REPAYMENT_FREQUENCY_CHOICES, blank=True)

    # ── Cat G: Subsidy / Financial Assistance ──
    subsidy_proposed = models.BooleanField(default=False)
    subsidy_scheme_name = models.CharField(max_length=300, blank=True)
    subsidy_implementing_agency = models.CharField(max_length=300, blank=True)
    expected_subsidy_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    basis_of_eligibility = models.TextField(blank=True)
    subsidy_application_status = models.CharField(max_length=20, choices=SUBSIDY_STATUS_CHOICES, blank=True)

    # ── Cat H: Existing Financial Position ──
    is_operational = models.BooleanField(default=False)
    latest_annual_turnover = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    latest_net_profit_loss = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)

    # ── Cat I: Financial Assumptions ──
    inflation_rate_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    raw_material_price_increase_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    selling_price_increase_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    salary_escalation_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    electricity_tariff_increase_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    fuel_price_increase_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    is_complete = models.BooleanField(default=False)

    class Meta:
        db_table = 'dpr_section_finance'
        verbose_name = 'DPR — Finance Section'
        verbose_name_plural = 'DPR — Finance Sections'

    def __str__(self):
        return f'Finance section for project {self.project_id}'


class DPRRevenueAssumption(TimeStampedModel, AuditModel):
    """§2.3.18 Cat E — per-product revenue assumption."""

    section = models.ForeignKey(
        DPRSectionFinance,
        on_delete=models.CASCADE,
        related_name='revenue_assumptions',
    )
    order = models.IntegerField(default=0)
    product_name = models.CharField(max_length=200)
    year1_sales_quantity = models.DecimalField(max_digits=18, decimal_places=3, null=True, blank=True)
    expected_selling_price = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    annual_sales_revenue = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    expected_annual_growth_rate_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    class Meta:
        db_table = 'dpr_revenue_assumption'
        verbose_name = 'DPR — Revenue Assumption'
        verbose_name_plural = 'DPR — Revenue Assumptions'
        ordering = ['order', 'id']

    def __str__(self):
        return self.product_name or f'Revenue #{self.pk}'


class DPRFinancialYearHistory(TimeStampedModel, AuditModel):
    """§2.3.18 Cat H additional — one row per financial year (last 3 years for operational FPOs)."""

    section = models.ForeignKey(
        DPRSectionFinance,
        on_delete=models.CASCADE,
        related_name='year_history',
    )
    financial_year = models.CharField(max_length=10, help_text='e.g. "2024-25"')
    annual_turnover = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    net_profit = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    total_assets = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    total_liabilities = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    net_worth = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    existing_loans = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    existing_repayment_obligations = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)

    class Meta:
        db_table = 'dpr_financial_year_history'
        verbose_name = 'DPR — Financial Year History'
        verbose_name_plural = 'DPR — Financial Year History Rows'
        unique_together = [('section', 'financial_year')]
        ordering = ['financial_year']

    def __str__(self):
        return f'{self.financial_year} — section {self.section_id}'
