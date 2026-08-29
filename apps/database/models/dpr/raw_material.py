"""
DPR §2.3.10 — Raw Material Assessment and Supply System.

Five normalized tables (per BUILD_PLAN.md Phase 1):
    DPRSectionRawMaterial   — 1:1 with project. Category C section-level + risks container.
    DPRRawMaterial          — N per section. Categories A + B + D + E per row.
    DPRRawMaterialRisk      — N per section. Category F.
    DPRPackagingMaterial    — N per section. Category G.
    DPRConsumable           — N per section. Category H.

Cross-references KAU master data:
    - core.MasterLookup(category='commodity')  — for commodity dropdown (63 items shared platform-wide)
    - DPRCapacityUnit, DPRRawMaterialSource, DPRProcurementModel,
      DPRQualityStandard, DPRQualityParameter — dedicated DPR masters
"""

from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.core.models.base import TimeStampedModel, AuditModel


MONTHS = [
    ('jan', 'January'), ('feb', 'February'), ('mar', 'March'), ('apr', 'April'),
    ('may', 'May'), ('jun', 'June'), ('jul', 'July'), ('aug', 'August'),
    ('sep', 'September'), ('oct', 'October'), ('nov', 'November'), ('dec', 'December'),
]

FREQUENCY_CHOICES = [
    ('daily', 'Daily'),
    ('weekly', 'Weekly'),
    ('monthly', 'Monthly'),
    ('seasonal', 'Seasonal'),
    ('as_required', 'As Required'),
]

PRICE_BASIS_CHOICES = [
    ('recent_purchase', 'Recent Purchase'),
    ('supplier_quotation', 'Supplier Quotation'),
    ('market_survey', 'Market Survey'),
    ('govt_price', 'Government Price'),
    ('other', 'Other (Specify)'),
]

PRICE_VARIATION_CHOICES = [
    ('low', 'Low (<10%)'),
    ('moderate', 'Moderate (10–25%)'),
    ('high', 'High (>25%)'),
]

RISK_TYPE_CHOICES = [
    ('seasonal_shortage', 'Seasonal Shortage'),
    ('climate_risk', 'Climate Risk'),
    ('pest_disease', 'Pest and Disease'),
    ('price_fluctuation', 'Price Fluctuation'),
    ('transportation', 'Transportation Issues'),
    ('labour_shortage', 'Labour Shortage'),
    ('competition', 'Competition for Raw Material'),
    ('quality_variation', 'Quality Variation'),
    ('import_dependence', 'Import Dependence'),
    ('other', 'Other (Specify)'),
]


class DPRSectionRawMaterial(TimeStampedModel, AuditModel):
    """§2.3.10 section container. One-to-one with DPRProject."""

    project = models.OneToOneField(
        'database.DPRProject',
        on_delete=models.CASCADE,
        related_name='section_raw_material',
    )

    # ─── Category C — Procurement System (section-level overall strategy) ───
    procurement_model = models.ForeignKey(
        'database.DPRProcurementModel',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='+',
        help_text='Overall procurement model (per-material method is on DPRRawMaterial.procurement_method)',
    )
    procurement_model_other = models.CharField(max_length=200, blank=True)
    procurement_frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, blank=True)
    collection_method = models.CharField(max_length=500, blank=True)
    transportation_arrangement = models.CharField(max_length=500, blank=True)

    # Category C — additional cost info
    avg_procurement_cost = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    loading_cost = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    unloading_cost = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    sorting_grading_cost = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    handling_charges = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    is_complete = models.BooleanField(
        default=False,
        help_text='FPO marked section complete (frontend flag; server also runs validators)',
    )

    class Meta:
        db_table = 'dpr_section_raw_material'
        verbose_name = 'DPR — Raw Material Section'
        verbose_name_plural = 'DPR — Raw Material Sections'

    def __str__(self):
        return f'RawMaterial section for {self.project_id}'


class DPRRawMaterial(TimeStampedModel, AuditModel):
    """One primary raw material row — Categories A + B + D + E."""

    section = models.ForeignKey(
        DPRSectionRawMaterial,
        on_delete=models.CASCADE,
        related_name='materials',
    )
    order = models.IntegerField(default=0, help_text='Display order in UI table')

    # ── Category A — Primary Raw Material ──
    name = models.CharField(max_length=200, help_text='Raw material name (required)')
    scientific_name = models.CharField(max_length=200, blank=True)
    variety_grade = models.CharField(max_length=200, blank=True)
    commodity = models.ForeignKey(
        'core.MasterLookup',
        on_delete=models.PROTECT,
        null=True, blank=True,
        limit_choices_to={'category': 'commodity', 'is_active': True},
        related_name='+',
        help_text='Commodity category from cross-platform master',
    )
    unit_of_purchase = models.ForeignKey(
        'database.DPRCapacityUnit',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='+',
    )
    estimated_annual_requirement = models.DecimalField(
        max_digits=15, decimal_places=3, null=True, blank=True,
    )
    approx_purchase_price = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    primary_source = models.ForeignKey(
        'database.DPRRawMaterialSource',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='+',
    )
    primary_source_other = models.CharField(max_length=200, blank=True)
    procurement_method = models.ForeignKey(
        'database.DPRProcurementModel',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='+',
        help_text='Per-material procurement method (section-level model on DPRSectionRawMaterial.procurement_model)',
    )
    procurement_method_other = models.CharField(max_length=200, blank=True)
    avg_procurement_radius_km = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    # ── Category B — Availability ──
    estimated_qty_available_annual = models.DecimalField(
        max_digits=15, decimal_places=3, null=True, blank=True,
    )
    num_supplying_farmers = models.IntegerField(null=True, blank=True)
    num_supplying_villages = models.IntegerField(null=True, blank=True)
    available_months = ArrayField(
        models.CharField(max_length=3, choices=MONTHS),
        default=list, blank=True,
        help_text='Months available (e.g. ["jan","feb","mar"])',
    )
    available_throughout_year = models.BooleanField(default=False)
    peak_harvest_season = models.CharField(max_length=100, blank=True)
    lean_season = models.CharField(max_length=100, blank=True)
    storage_required = models.BooleanField(
        null=True, blank=True,
        help_text='Nullable — only asked when NOT available year-round',
    )
    off_season_strategy = models.TextField(blank=True)
    estimated_annual_production_area = models.DecimalField(
        max_digits=15, decimal_places=3, null=True, blank=True,
    )
    avg_procurement_distance_km = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    preservation_method = models.CharField(max_length=200, blank=True)

    # ── Category D — Quality ──
    quality_standards_applicable = models.BooleanField(default=False)
    grade = models.CharField(max_length=100, blank=True)
    quality_standard = models.ForeignKey(
        'database.DPRQualityStandard',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='+',
    )
    certification_required = models.BooleanField(null=True, blank=True)
    quality_testing_required = models.BooleanField(null=True, blank=True)
    quality_parameters = models.ManyToManyField(
        'database.DPRQualityParameter',
        blank=True,
        related_name='+',
    )
    quality_remarks = models.TextField(blank=True)

    # ── Category E — Price ──
    current_purchase_price = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    price_estimation_basis = models.CharField(max_length=30, choices=PRICE_BASIS_CHOICES, blank=True)
    price_estimation_basis_other = models.CharField(max_length=200, blank=True)
    price_varies_seasonally = models.BooleanField(default=False)
    peak_price_season = models.CharField(max_length=100, blank=True)
    lowest_price_season = models.CharField(max_length=100, blank=True)
    price_variation_range = models.CharField(max_length=10, choices=PRICE_VARIATION_CHOICES, blank=True)
    expected_future_price = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    historical_price_trend = models.TextField(blank=True)
    transportation_cost = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    loading_charges = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    unloading_charges = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    commission_charges = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    storage_cost = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    class Meta:
        db_table = 'dpr_raw_material'
        verbose_name = 'DPR — Raw Material'
        verbose_name_plural = 'DPR — Raw Materials'
        ordering = ['order', 'id']

    def __str__(self):
        return self.name or f'RawMaterial #{self.pk}'


class DPRRawMaterialRisk(TimeStampedModel, AuditModel):
    """§2.3.10 Category F — Supply risks with per-risk mitigation."""

    section = models.ForeignKey(
        DPRSectionRawMaterial,
        on_delete=models.CASCADE,
        related_name='risks',
    )
    risk_type = models.CharField(max_length=30, choices=RISK_TYPE_CHOICES)
    risk_type_other = models.CharField(max_length=200, blank=True)
    mitigation_strategy = models.TextField()
    existing_practices = models.TextField(blank=True)
    previous_experience = models.TextField(blank=True)

    class Meta:
        db_table = 'dpr_raw_material_risk'
        verbose_name = 'DPR — Raw Material Risk'
        verbose_name_plural = 'DPR — Raw Material Risks'
        ordering = ['id']

    def __str__(self):
        return f'{self.get_risk_type_display()} — section {self.section_id}'


class DPRPackagingMaterial(TimeStampedModel, AuditModel):
    """§2.3.10 Category G — Packaging materials for finished-goods projects."""

    section = models.ForeignKey(
        DPRSectionRawMaterial,
        on_delete=models.CASCADE,
        related_name='packaging_materials',
    )
    order = models.IntegerField(default=0)
    material_name = models.CharField(max_length=200)
    purpose = models.CharField(max_length=500, blank=True)
    unit = models.ForeignKey(
        'database.DPRCapacityUnit',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='+',
    )
    estimated_annual_requirement = models.DecimalField(
        max_digits=15, decimal_places=3, null=True, blank=True,
    )
    unit_cost = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    supplier = models.CharField(max_length=200, blank=True)
    procurement_frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, blank=True)
    quality_standard = models.ForeignKey(
        'database.DPRQualityStandard',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='+',
    )

    class Meta:
        db_table = 'dpr_packaging_material'
        verbose_name = 'DPR — Packaging Material'
        verbose_name_plural = 'DPR — Packaging Materials'
        ordering = ['order', 'id']

    def __str__(self):
        return self.material_name


class DPRConsumable(TimeStampedModel, AuditModel):
    """§2.3.10 Category H — Other consumables (labels, cleaning chemicals, etc.)."""

    section = models.ForeignKey(
        DPRSectionRawMaterial,
        on_delete=models.CASCADE,
        related_name='consumables',
    )
    order = models.IntegerField(default=0)
    name = models.CharField(max_length=200)
    purpose = models.CharField(max_length=500, blank=True)
    estimated_annual_requirement = models.DecimalField(
        max_digits=15, decimal_places=3, null=True, blank=True,
    )
    unit = models.ForeignKey(
        'database.DPRCapacityUnit',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='+',
    )
    unit_cost = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    supplier = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table = 'dpr_consumable'
        verbose_name = 'DPR — Consumable'
        verbose_name_plural = 'DPR — Consumables'
        ordering = ['order', 'id']

    def __str__(self):
        return self.name
