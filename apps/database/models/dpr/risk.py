"""
DPR §2.3.22 — Risk Assessment and Mitigation Plan (final section).

Two tables (unified through-table pattern like §2.3.19 Compliance):
    DPRSectionRisk   — 1:1 container
    DPRRiskItem      — N per section, unified across all 6 risk categories A-F + Cat G plan fields

All 6 spec categories (production/market/financial/institutional/environmental/regulatory)
share the same shape, so we collapse into one child table with a `risk_category` field.
Frontend groups by category for the KAU spec's per-category UI.

Cat G "Risk Mitigation Plan" fields (risk_description / responsible / timeline / expected_outcome)
merge onto every risk row rather than being a separate list.
"""

from django.db import models

from apps.core.models.base import TimeStampedModel, AuditModel


RISK_CATEGORY_CHOICES = [
    ('production',     'Production Risk'),
    ('market',         'Market Risk'),
    ('financial',      'Financial Risk'),
    ('institutional',  'Institutional Risk'),
    ('environmental',  'Environmental Risk'),
    ('regulatory',     'Regulatory Risk'),
]

# Consolidated set of risk codes across all 6 categories from KAU spec.
# Frontend filters by category to show the applicable subset.
RISK_CODE_CHOICES = [
    # Production (Cat A)
    ('raw_material_unavailable',   'Non-availability of Raw Materials'),
    ('seasonal_supply',            'Seasonal Raw Material Supply'),
    ('poor_quality_material',      'Poor Quality Raw Materials'),
    ('pest_disease',               'Pest and Disease Incidence'),
    ('production_losses',          'Production Losses'),
    ('machinery_breakdown',        'Machinery Breakdown'),
    ('power_failure',              'Power Failure'),
    ('water_scarcity',             'Water Scarcity'),
    ('labour_shortage',            'Labour Shortage'),
    ('technology_failure',         'Technology Failure'),
    # Market (Cat B)
    ('price_fluctuation',          'Price Fluctuation'),
    ('low_market_demand',          'Low Market Demand'),
    ('competition',                'Competition'),
    ('delayed_payments',           'Delayed Payments'),
    ('customer_concentration',     'Customer Concentration'),
    ('product_rejection',          'Product Rejection'),
    ('export_restrictions',        'Export Restrictions'),
    ('logistics_issues',           'Logistics Issues'),
    # Financial (Cat C)
    ('cost_escalation',            'Cost Escalation'),
    ('interest_rate_increase',     'Interest Rate Increase'),
    ('wc_shortage',                'Working Capital Shortage'),
    ('loan_delay',                 'Loan Delay'),
    ('cash_flow_problems',         'Cash Flow Problems'),
    ('credit_recovery',            'Credit Recovery Issues'),
    ('inflation',                  'Inflation'),
    # Institutional (Cat D)
    ('weak_governance',            'Weak Governance'),
    ('low_member_participation',   'Low Member Participation'),
    ('management_issues',          'Management Issues'),
    ('skilled_manpower_shortage',  'Skilled Manpower Shortage'),
    ('staff_turnover',             'Staff Turnover'),
    ('decision_delays',            'Decision-making Delays'),
    # Environmental (Cat E)
    ('flood',                      'Flood'),
    ('drought',                    'Drought'),
    ('cyclone',                    'Cyclone'),
    ('landslide',                  'Landslide'),
    ('water_pollution',            'Water Pollution'),
    ('fire',                       'Fire'),
    ('climate_change',             'Climate Change'),
    # Regulatory (Cat F)
    ('delay_licences',             'Delay in Licences'),
    ('delay_subsidy',              'Delay in Subsidy'),
    ('policy_changes',             'Policy Changes'),
    ('tax_changes',                'Tax Changes'),
    ('env_regulations',            'Environmental Regulations'),
    ('labour_regulations',         'Labour Regulations'),
    # Universal fallback
    ('other',                      'Others (Specify)'),
]

LEVEL_CHOICES = [
    ('low',     'Low'),
    ('medium',  'Medium'),
    ('high',    'High'),
]

OVERALL_RISK_CHOICES = [
    ('low',       'Low Risk'),
    ('moderate',  'Moderate Risk'),
    ('high',      'High Risk'),
]


class DPRSectionRisk(TimeStampedModel, AuditModel):
    """§2.3.22 section — one row per project."""

    project = models.OneToOneField(
        'database.DPRProject',
        on_delete=models.CASCADE,
        related_name='section_risk',
    )

    # Auto-computed by system at DPR generation (per KAU spec's "Overall Project Risk Rating")
    overall_risk_rating = models.CharField(
        max_length=20, choices=OVERALL_RISK_CHOICES, blank=True,
        help_text='Auto-classified low/moderate/high at DPR generation based on cumulative assessment.',
    )

    is_complete = models.BooleanField(default=False)

    class Meta:
        db_table = 'dpr_section_risk'
        verbose_name = 'DPR — Risk Section'
        verbose_name_plural = 'DPR — Risk Sections'

    def __str__(self):
        return f'Risk section for project {self.project_id}'


class DPRRiskItem(TimeStampedModel, AuditModel):
    """One risk per row — unified across all 6 KAU categories (Cat A-F) + Cat G plan fields."""

    section = models.ForeignKey(
        DPRSectionRisk,
        on_delete=models.CASCADE,
        related_name='items',
    )
    order = models.IntegerField(default=0)

    risk_category = models.CharField(max_length=20, choices=RISK_CATEGORY_CHOICES)
    risk_code = models.CharField(max_length=40, choices=RISK_CODE_CHOICES)
    risk_code_other = models.CharField(max_length=200, blank=True, help_text='Only when risk_code == "other"')

    # Cat G: Risk Mitigation Plan (fields merged onto every risk)
    risk_description = models.TextField(blank=True)
    mitigation_strategy = models.TextField(
        blank=True,
        help_text='Required per KAU spec — enforced by validator',
    )
    responsible_person_or_agency = models.CharField(max_length=300, blank=True)
    implementation_timeline = models.CharField(max_length=200, blank=True)
    expected_outcome = models.TextField(blank=True)

    # Cat A-F additional info
    probability = models.CharField(max_length=10, choices=LEVEL_CHOICES, blank=True)
    impact = models.CharField(max_length=10, choices=LEVEL_CHOICES, blank=True)
    existing_measures = models.TextField(blank=True)

    class Meta:
        db_table = 'dpr_risk_item'
        verbose_name = 'DPR — Risk Item'
        verbose_name_plural = 'DPR — Risk Items'
        unique_together = [('section', 'risk_category', 'risk_code')]
        ordering = ['order', 'id']

    def __str__(self):
        return f'{self.get_risk_category_display()} — {self.get_risk_code_display()}'
