"""
DPR §2.3.15 — Plant, Machinery and Equipment.

Three tables:
    DPRSectionMachinery      — 1:1 with project (Cat G statutory approvals section-level)
    DPRMachineryItem         — N per section (Cat A + B + C + D + E + F per item)
    DPRSupportingAssetItem   — N per section (Cat H — trolleys, forklifts, computers, etc.)

Masters used:
    DPRComponent             — Cat A project component linkage
    DPRMachineryCategory     — Cat A machine category (includes default depreciation + life)
    DPRCapacityUnit          — Cat A unit, Cat B capacity_unit
    DPRSupportingAsset       — Cat H supporting asset type (19 items seeded)
"""

from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.core.models.base import TimeStampedModel, AuditModel


AUTOMATION_LEVEL_CHOICES = [
    ('manual',      'Manual'),
    ('semi_auto',   'Semi-Automatic'),
    ('auto',        'Automatic'),
    ('fully_auto',  'Fully Automatic'),
]

SPARE_PARTS_AVAILABILITY_CHOICES = [
    ('easily',      'Easily Available'),
    ('on_order',    'Available on Order'),
    ('imported',    'Imported'),
    ('limited',     'Limited Availability'),
]

STATUTORY_APPROVAL_CHOICES = [
    ('factory_inspector',   'Factory Inspector Approval'),
    ('electrical_inspector', 'Electrical Inspector Approval'),
    ('boiler_inspection',   'Boiler Inspection'),
    ('calibration',         'Calibration'),
    ('safety_cert',         'Safety Certification'),
    ('pollution_control',   'Pollution Control Approval'),
    ('food_safety',         'Food Safety Compliance'),
    ('other',               'Others (Specify)'),
]


class DPRSectionMachinery(TimeStampedModel, AuditModel):
    """§2.3.15 section — one row per project."""

    project = models.OneToOneField(
        'database.DPRProject',
        on_delete=models.CASCADE,
        related_name='section_machinery',
    )

    # ── Cat G: Statutory Requirements (section-level) ──
    statutory_approvals = ArrayField(
        models.CharField(max_length=30, choices=STATUTORY_APPROVAL_CHOICES),
        default=list, blank=True,
    )
    statutory_approvals_other = models.CharField(max_length=300, blank=True)
    statutory_remarks = models.TextField(blank=True)

    is_complete = models.BooleanField(default=False)

    class Meta:
        db_table = 'dpr_section_machinery'
        verbose_name = 'DPR — Machinery Section'
        verbose_name_plural = 'DPR — Machinery Sections'

    def __str__(self):
        return f'Machinery section for project {self.project_id}'


class DPRMachineryItem(TimeStampedModel, AuditModel):
    """One machinery/equipment item — Cat A + B + C + D + E + F."""

    section = models.ForeignKey(
        DPRSectionMachinery,
        on_delete=models.CASCADE,
        related_name='items',
    )
    order = models.IntegerField(default=0)

    # ── Cat A: Machinery Identification ──
    name = models.CharField(max_length=200)
    purpose = models.CharField(max_length=500, blank=True)
    project_component = models.ForeignKey(
        'database.DPRComponent',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='+',
        help_text='Must link to a selected project component per KAU spec',
    )
    machine_category = models.ForeignKey(
        'database.DPRMachineryCategory',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='+',
    )
    machine_category_other = models.CharField(max_length=200, blank=True)
    quantity_required = models.DecimalField(max_digits=15, decimal_places=3, null=True, blank=True)
    process_stage = models.CharField(max_length=200, blank=True)
    unit = models.ForeignKey(
        'database.DPRCapacityUnit',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='+',
    )
    manufacturer = models.CharField(max_length=200, blank=True)
    supplier = models.CharField(max_length=200, blank=True)
    model_number = models.CharField(max_length=100, blank=True)
    country_of_manufacture = models.CharField(max_length=100, blank=True)

    # ── Cat B: Technical Specifications ──
    rated_capacity = models.DecimalField(max_digits=15, decimal_places=3, null=True, blank=True)
    capacity_unit = models.ForeignKey(
        'database.DPRCapacityUnit',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='dpr_machinery_capacity_unit',
    )
    power_source = models.CharField(max_length=200, blank=True)
    automation_level = models.CharField(max_length=20, choices=AUTOMATION_LEVEL_CHOICES, blank=True)
    operating_capacity = models.CharField(max_length=200, blank=True)
    operating_principle = models.TextField(blank=True)
    power_requirement = models.CharField(max_length=200, blank=True, help_text='e.g. "5 kW"')
    fuel_requirement = models.CharField(max_length=200, blank=True)
    water_requirement = models.CharField(max_length=200, blank=True)
    compressed_air_requirement = models.CharField(max_length=200, blank=True)
    recommended_operating_hours = models.CharField(max_length=200, blank=True)
    num_operators_required = models.IntegerField(null=True, blank=True)

    # ── Cat C: Space Requirement ──
    installation_area_required = models.CharField(max_length=200, blank=True, help_text='e.g. "50 sqm"')
    foundation_required = models.BooleanField(default=False)
    foundation_type = models.CharField(max_length=200, blank=True)
    working_clearance_required = models.CharField(max_length=200, blank=True)
    foundation_size = models.CharField(max_length=200, blank=True)

    # ── Cat D: Cost Details ──
    unit_cost = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    basic_cost = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    gst = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    transportation_charges = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    loading_unloading_charges = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    installation_charges = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    commissioning_charges = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    insurance = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    other_charges = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    # ── Cat E: Procurement Details ──
    supplier_identified = models.BooleanField(default=False)
    supplier_name = models.CharField(max_length=200, blank=True)
    supplier_location = models.CharField(max_length=300, blank=True)
    delivery_period = models.CharField(max_length=100, blank=True, help_text='e.g. "3 months"')
    warranty_period = models.CharField(max_length=100, blank=True)
    amc_required = models.BooleanField(null=True, blank=True)
    amc_cost = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    amc_duration = models.CharField(max_length=100, blank=True)

    # ── Cat F: Operation & Maintenance ──
    annual_maintenance_required = models.BooleanField(null=True, blank=True)
    spare_parts_availability = models.CharField(max_length=20, choices=SPARE_PARTS_AVAILABILITY_CHOICES, blank=True)
    daily_maintenance_requirement = models.TextField(blank=True)
    preventive_maintenance_frequency = models.CharField(max_length=200, blank=True)
    major_overhaul_frequency = models.CharField(max_length=200, blank=True)
    useful_life_years = models.IntegerField(null=True, blank=True)
    residual_value_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    class Meta:
        db_table = 'dpr_machinery_item'
        verbose_name = 'DPR — Machinery Item'
        verbose_name_plural = 'DPR — Machinery Items'
        ordering = ['order', 'id']

    def __str__(self):
        return self.name or f'Machinery #{self.pk}'


class DPRSupportingAssetItem(TimeStampedModel, AuditModel):
    """§2.3.15 Cat H — supporting asset (trolley, forklift, computer, etc.)."""

    section = models.ForeignKey(
        DPRSectionMachinery,
        on_delete=models.CASCADE,
        related_name='supporting_assets',
    )
    order = models.IntegerField(default=0)
    asset = models.ForeignKey(
        'database.DPRSupportingAsset',
        on_delete=models.PROTECT,
        related_name='+',
    )
    asset_name_other = models.CharField(max_length=200, blank=True, help_text='Only when asset.code == "other" or free-text override')
    quantity = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    purpose = models.CharField(max_length=500, blank=True)
    estimated_cost = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    class Meta:
        db_table = 'dpr_supporting_asset_item'
        verbose_name = 'DPR — Supporting Asset Item'
        verbose_name_plural = 'DPR — Supporting Asset Items'
        ordering = ['order', 'id']

    def __str__(self):
        return f'{self.asset_id} — section {self.section_id}'
