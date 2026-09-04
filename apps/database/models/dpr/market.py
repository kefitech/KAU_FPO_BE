"""
DPR §2.3.11 — Market Assessment and Business Model.

Six normalized tables (per BUILD_PLAN.md Phase 2 Stream A):
    DPRSectionMarket             — 1:1 with project. Cat B + E + G section-level + toggles.
    DPRMarketingProduct          — N per section. Cat A + Cat H merged (identity + sales projection).
    DPRMarketingBuyer            — N per section. Cat C (existing buyers).
    DPRMarketingChannelSelection — N per section. Cat D (channel + expected share %).
    DPRMarketingCompetitor       — N per section. Cat F (competitors).
    DPRMarketingRisk             — N per section. Cat I (marketing risks).

Master FKs (all already seeded):
    DPRProductCategory, DPRProductType, DPRCustomerCategory,
    DPRBuyerType, DPRMarketingChannel, DPRPromotionalActivity,
    DPRCapacityUnit, DPRIntendedMarket (added migration 0047)

"Others (Specify)" handling: every dropdown with an "other" option has a companion
`_other` CharField that captures the free-text explanation when the dropdown value = 'other'.
"""

from django.db import models

from apps.core.models.base import TimeStampedModel, AuditModel


YES_NO_UNSURE = [
    ('yes', 'Yes'),
    ('no', 'No'),
    ('not_sure', 'Not Sure'),
]

DEMAND_BASIS_CHOICES = [
    ('market_survey', 'Market Survey'),
    ('existing_sales', 'Existing Sales'),
    ('buyer_enquiry', 'Buyer Enquiry'),
    ('secondary_data', 'Secondary Data'),
    ('industry_report', 'Industry Report'),
    ('govt_stats', 'Government Statistics'),
    ('previous_experience', 'Previous Experience'),
    ('other', 'Others (Specify)'),
]

PRICING_BASIS_CHOICES = [
    ('cost_plus', 'Cost Plus Pricing'),
    ('market_price', 'Market Price'),
    ('competitive', 'Competitive Pricing'),
    ('govt_support', 'Government Support Price'),
    ('contract', 'Contract Price'),
    ('negotiated', 'Negotiated Price'),
    ('export', 'Export Price'),
    ('other', 'Others (Specify)'),
]

PURCHASE_FREQUENCY_CHOICES = [
    ('daily', 'Daily'),
    ('weekly', 'Weekly'),
    ('monthly', 'Monthly'),
    ('seasonal', 'Seasonal'),
    ('as_required', 'As Required'),
]

COMPETITOR_TYPE_CHOICES = [
    ('local', 'Local'),
    ('regional', 'Regional'),
    ('national', 'National'),
    ('international', 'International'),
]

MARKETING_RISK_CHOICES = [
    ('price_fluctuation', 'Price Fluctuation'),
    ('market_competition', 'Market Competition'),
    ('consumer_preference', 'Consumer Preference Change'),
    ('transportation', 'Transportation Constraints'),
    ('demand_reduction', 'Demand Reduction'),
    ('quality_issues', 'Quality Issues'),
    ('branding_challenges', 'Branding Challenges'),
    ('other', 'Others (Specify)'),
]


# ─────────────────────────────────────────────────────────────────────────────
# Section container (Categories B + E + G section-level + toggles)
# ─────────────────────────────────────────────────────────────────────────────

class DPRSectionMarket(TimeStampedModel, AuditModel):
    """§2.3.11 section container. One-to-one with DPRProject."""

    project = models.OneToOneField(
        'database.DPRProject',
        on_delete=models.CASCADE,
        related_name='section_market',
    )

    # ── Category B — Market Demand ──
    demand_exists = models.CharField(max_length=10, choices=YES_NO_UNSURE, blank=True)
    estimated_annual_demand = models.DecimalField(max_digits=18, decimal_places=3, null=True, blank=True)
    demand_basis = models.CharField(max_length=30, choices=DEMAND_BASIS_CHOICES, blank=True)
    demand_basis_other = models.CharField(max_length=200, blank=True)
    current_supply = models.DecimalField(max_digits=18, decimal_places=3, null=True, blank=True)
    supply_gap = models.DecimalField(max_digits=18, decimal_places=3, null=True, blank=True)
    expected_demand_growth_pct = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    seasonal_demand_pattern = models.TextField(blank=True)
    peak_demand_period = models.CharField(max_length=200, blank=True)
    off_season_demand = models.CharField(max_length=200, blank=True)

    # ── Category C — Existing Buyers toggle ──
    has_existing_buyers = models.BooleanField(default=False)

    # ── Category E — Pricing Strategy (section-level) ──
    pricing_basis = models.CharField(max_length=30, choices=PRICING_BASIS_CHOICES, blank=True)
    pricing_basis_other = models.CharField(max_length=200, blank=True)
    existing_market_price = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    competitor_price = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    expected_annual_price_increase_pct = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    promotional_pricing_notes = models.TextField(blank=True)
    seasonal_price_variation = models.TextField(blank=True)
    credit_sales_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    cash_sales_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    # ── Category F — Competitors toggle ──
    has_competitors = models.CharField(max_length=10, choices=YES_NO_UNSURE, blank=True)

    # ── Category G — Branding & Promotion (section-level) ──
    is_branded = models.BooleanField(default=False)
    brand_name = models.CharField(
        max_length=200, blank=True,
        help_text='Company-level brand (per-product brand on DPRMarketingProduct.proposed_brand_name)',
    )
    existing_brand_name = models.CharField(max_length=200, blank=True)
    promotional_activities = models.ManyToManyField(
        'database.DPRPromotionalActivity',
        blank=True,
        related_name='+',
    )
    packaging_strategy = models.TextField(blank=True)
    label_design_available = models.BooleanField(default=False)
    certification_logo = models.CharField(max_length=200, blank=True)
    website = models.URLField(blank=True)
    social_media_presence = models.TextField(blank=True)

    is_complete = models.BooleanField(default=False)

    class Meta:
        db_table = 'dpr_section_market'
        verbose_name = 'DPR — Market Section'
        verbose_name_plural = 'DPR — Market Sections'

    def __str__(self):
        return f'Market section for project {self.project_id}'


# ─────────────────────────────────────────────────────────────────────────────
# Category A + H — Products (merged: identity + sales projection)
# ─────────────────────────────────────────────────────────────────────────────

class DPRMarketingProduct(TimeStampedModel, AuditModel):
    """Category A (identity) + Category H (sales projection) — one row per product."""

    section = models.ForeignKey(
        DPRSectionMarket,
        on_delete=models.CASCADE,
        related_name='products',
    )
    order = models.IntegerField(default=0)

    # ── Cat A: Identity ──
    name = models.CharField(max_length=200)
    product_category = models.ForeignKey(
        'database.DPRProductCategory',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='+',
    )
    product_type = models.ForeignKey(
        'database.DPRProductType',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='+',
        help_text='Primary / Secondary / By-product',
    )
    intended_market = models.ForeignKey(
        'database.DPRIntendedMarket',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='+',
    )
    geographic_market = models.CharField(
        max_length=500, blank=True,
        help_text='Free text — cities / regions / states',
    )
    proposed_brand_name = models.CharField(
        max_length=200, blank=True,
        help_text='Per-product brand (section-level company brand on DPRSectionMarket.brand_name)',
    )
    existing_brand_name = models.CharField(max_length=200, blank=True)
    customer_categories = models.ManyToManyField(
        'database.DPRCustomerCategory',
        blank=True,
        related_name='+',
    )

    # ── Cat H: Sales projection ──
    # User fills Yr 1 (mandatory) + Yr 2-5 optional; Yr 6-10 will be AI-generated separately.
    proposed_selling_price = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    unit_of_sale = models.ForeignKey(
        'database.DPRCapacityUnit',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='+',
    )
    year1_qty = models.DecimalField(max_digits=18, decimal_places=3, null=True, blank=True)
    year2_qty = models.DecimalField(max_digits=18, decimal_places=3, null=True, blank=True)
    year3_qty = models.DecimalField(max_digits=18, decimal_places=3, null=True, blank=True)
    year4_qty = models.DecimalField(max_digits=18, decimal_places=3, null=True, blank=True)
    year5_qty = models.DecimalField(max_digits=18, decimal_places=3, null=True, blank=True)

    # Cat H: Channel-mix split % (should sum ≤ 100 across all six)
    domestic_sales_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    export_sales_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    institutional_sales_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    retail_sales_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    wholesale_sales_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    online_sales_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    class Meta:
        db_table = 'dpr_marketing_product'
        verbose_name = 'DPR — Marketing Product'
        verbose_name_plural = 'DPR — Marketing Products'
        ordering = ['order', 'id']

    def __str__(self):
        return self.name or f'Product #{self.pk}'


# ─────────────────────────────────────────────────────────────────────────────
# Category C — Existing Buyers
# ─────────────────────────────────────────────────────────────────────────────

class DPRMarketingBuyer(TimeStampedModel, AuditModel):
    """§2.3.11 Cat C — existing buyer. Populated when section.has_existing_buyers=True."""

    section = models.ForeignKey(
        DPRSectionMarket,
        on_delete=models.CASCADE,
        related_name='buyers',
    )
    order = models.IntegerField(default=0)
    buyer_name = models.CharField(max_length=200, blank=True, help_text='Optional per spec')
    buyer_category = models.ForeignKey(
        'database.DPRBuyerType',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='+',
    )
    location = models.CharField(max_length=300, blank=True)
    purchase_frequency = models.CharField(max_length=20, choices=PURCHASE_FREQUENCY_CHOICES, blank=True)
    num_buyers = models.IntegerField(null=True, blank=True)
    avg_quantity_purchased = models.DecimalField(max_digits=18, decimal_places=3, null=True, blank=True)
    has_purchase_agreement = models.BooleanField(null=True, blank=True)
    has_contract = models.BooleanField(null=True, blank=True)
    credit_period_days = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = 'dpr_marketing_buyer'
        verbose_name = 'DPR — Marketing Buyer'
        verbose_name_plural = 'DPR — Marketing Buyers'
        ordering = ['order', 'id']

    def __str__(self):
        return self.buyer_name or f'Buyer #{self.pk}'


# ─────────────────────────────────────────────────────────────────────────────
# Category D — Marketing Channel selection with expected share
# ─────────────────────────────────────────────────────────────────────────────

class DPRMarketingChannelSelection(TimeStampedModel, AuditModel):
    """§2.3.11 Cat D — one row per selected marketing channel with share and arrangement."""

    section = models.ForeignKey(
        DPRSectionMarket,
        on_delete=models.CASCADE,
        related_name='channel_selections',
    )
    channel = models.ForeignKey(
        'database.DPRMarketingChannel',
        on_delete=models.PROTECT,
        related_name='+',
    )
    channel_other = models.CharField(
        max_length=200, blank=True,
        help_text='Only used when channel.code == "other"',
    )
    expected_share_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    existing_arrangement = models.TextField(blank=True)
    remarks = models.TextField(blank=True)

    class Meta:
        db_table = 'dpr_marketing_channel_selection'
        verbose_name = 'DPR — Marketing Channel Selection'
        verbose_name_plural = 'DPR — Marketing Channel Selections'
        unique_together = [('section', 'channel')]
        ordering = ['id']

    def __str__(self):
        return f'channel {self.channel_id} for section {self.section_id}'


# ─────────────────────────────────────────────────────────────────────────────
# Category F — Competitors
# ─────────────────────────────────────────────────────────────────────────────

class DPRMarketingCompetitor(TimeStampedModel, AuditModel):
    """§2.3.11 Cat F — competitor detail. Populated when section.has_competitors='yes'."""

    section = models.ForeignKey(
        DPRSectionMarket,
        on_delete=models.CASCADE,
        related_name='competitors',
    )
    order = models.IntegerField(default=0)
    name = models.CharField(max_length=200)
    competitor_type = models.CharField(max_length=20, choices=COMPETITOR_TYPE_CHOICES, blank=True)
    competitive_advantage = models.TextField(
        help_text='Advantage of our project over this competitor — spec requires at least one when competitors exist',
    )
    differentiation_strategy = models.TextField(blank=True)
    num_competitors = models.IntegerField(null=True, blank=True)
    estimated_market_share_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    strengths = models.TextField(blank=True)
    weaknesses = models.TextField(blank=True)

    class Meta:
        db_table = 'dpr_marketing_competitor'
        verbose_name = 'DPR — Marketing Competitor'
        verbose_name_plural = 'DPR — Marketing Competitors'
        ordering = ['order', 'id']

    def __str__(self):
        return self.name


# ─────────────────────────────────────────────────────────────────────────────
# Category I — Marketing Risks
# ─────────────────────────────────────────────────────────────────────────────

class DPRMarketingRisk(TimeStampedModel, AuditModel):
    """§2.3.11 Cat I — marketing risks with mandatory per-risk mitigation strategy."""

    section = models.ForeignKey(
        DPRSectionMarket,
        on_delete=models.CASCADE,
        related_name='risks',
    )
    risk_type = models.CharField(max_length=30, choices=MARKETING_RISK_CHOICES)
    risk_type_other = models.CharField(max_length=200, blank=True)
    mitigation_strategy = models.TextField()
    existing_practices = models.TextField(blank=True)
    import_competition = models.TextField(blank=True)
    export_restrictions = models.TextField(blank=True)
    certification_issues = models.TextField(blank=True)

    class Meta:
        db_table = 'dpr_marketing_risk'
        verbose_name = 'DPR — Marketing Risk'
        verbose_name_plural = 'DPR — Marketing Risks'
        ordering = ['id']

    def __str__(self):
        return f'{self.get_risk_type_display()} — section {self.section_id}'
