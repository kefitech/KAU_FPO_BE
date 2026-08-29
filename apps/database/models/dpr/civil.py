"""
DPR §2.3.14 — Building, Civil Works and Physical Infrastructure.

Four tables:
    DPRSectionCivil            — 1:1 with project (Cat D cost + Cat E future expansion)
    DPRExistingBuilding        — N per section (Cat A)
    DPRProposedBuilding        — N per section (Cat B — FK to DPRBuildingType)
    DPRSiteDevelopmentItem     — N per section (Cat C — FK to DPRCivilCategory)

Masters used:
    DPRBuildingType    — 18 items (Cat B)
    DPRCivilCategory   — 13 items (Cat C)
"""

from django.db import models

from apps.core.models.base import TimeStampedModel, AuditModel


AREA_UNIT_CHOICES = [
    ('sqft', 'sq. ft.'),
    ('sqm',  'sq. m.'),
]

PROPOSED_ACTION_CHOICES = [
    ('continue',     'Continue as Existing'),
    ('renovate',     'Renovate'),
    ('expand',       'Expand'),
    ('demolish',     'Demolish'),
    ('convert_use',  'Convert to Different Use'),
]

BUILDING_OWNERSHIP_CHOICES = [
    ('fpo_owned',     'FPO Owned'),
    ('member_owned',  'Member Owned'),
    ('leased',        'Leased'),
    ('rented',        'Rented'),
    ('govt_allotted', 'Government Allotted'),
    ('other',         'Others'),
]

COST_BASIS_CHOICES = [
    ('engineer',    'Engineer\'s Estimate'),
    ('contractor',  'Contractor Quotation'),
    ('similar',     'Previous Similar Project'),
    ('consultant',  'Consultant Estimate'),
    ('other',       'Others (Specify)'),
]


class DPRSectionCivil(TimeStampedModel, AuditModel):
    """§2.3.14 section — one row per project."""

    project = models.OneToOneField(
        'database.DPRProject',
        on_delete=models.CASCADE,
        related_name='section_civil',
    )

    # ── Cat D: Civil Infrastructure Cost ──
    has_civil_cost_estimate = models.BooleanField(default=False)
    cost_site_development = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    cost_building_construction = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    cost_internal_roads = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    cost_compound_wall = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    cost_drainage = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    cost_water_supply = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    cost_sanitation = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    cost_electrical = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    cost_fire_protection = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    cost_landscaping = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    cost_other_civil = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    basis_of_estimate = models.CharField(max_length=20, choices=COST_BASIS_CHOICES, blank=True)
    basis_of_estimate_other = models.CharField(max_length=200, blank=True)

    # ── Cat E: Future Expansion Provision ──
    has_future_expansion = models.BooleanField(default=False)
    space_reserved_for_expansion = models.CharField(max_length=200, blank=True)
    future_buildings_planned = models.TextField(blank=True)
    future_civil_works_required = models.TextField(blank=True)
    estimated_future_investment = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)

    is_complete = models.BooleanField(default=False)

    class Meta:
        db_table = 'dpr_section_civil'
        verbose_name = 'DPR — Civil Section'
        verbose_name_plural = 'DPR — Civil Sections'

    def __str__(self):
        return f'Civil section for project {self.project_id}'


class DPRExistingBuilding(TimeStampedModel, AuditModel):
    """§2.3.14 Cat A — existing building."""

    section = models.ForeignKey(
        DPRSectionCivil,
        on_delete=models.CASCADE,
        related_name='existing_buildings',
    )
    order = models.IntegerField(default=0)

    building_name = models.CharField(max_length=200)
    purpose = models.CharField(max_length=500, blank=True)
    floor_area = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    area_unit = models.CharField(max_length=10, choices=AREA_UNIT_CHOICES, blank=True)
    present_condition = models.CharField(max_length=200, blank=True)
    ownership_status = models.CharField(max_length=20, choices=BUILDING_OWNERSHIP_CHOICES, blank=True)
    proposed_action = models.CharField(max_length=20, choices=PROPOSED_ACTION_CHOICES, blank=True)
    year_of_construction = models.IntegerField(null=True, blank=True)
    num_floors = models.IntegerField(null=True, blank=True)
    current_utilisation = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table = 'dpr_existing_building'
        verbose_name = 'DPR — Existing Building'
        verbose_name_plural = 'DPR — Existing Buildings'
        ordering = ['order', 'id']

    def __str__(self):
        return self.building_name or f'Building #{self.pk}'


class DPRProposedBuilding(TimeStampedModel, AuditModel):
    """§2.3.14 Cat B — proposed building."""

    section = models.ForeignKey(
        DPRSectionCivil,
        on_delete=models.CASCADE,
        related_name='proposed_buildings',
    )
    order = models.IntegerField(default=0)

    building_type = models.ForeignKey(
        'database.DPRBuildingType',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='+',
    )
    building_type_other = models.CharField(max_length=200, blank=True)
    purpose = models.CharField(max_length=500, blank=True)
    floor_area = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    area_unit = models.CharField(max_length=10, choices=AREA_UNIT_CHOICES, blank=True)
    proposed_location_within_site = models.CharField(max_length=300, blank=True)
    num_floors = models.IntegerField(null=True, blank=True)
    estimated_construction_cost = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    estimated_completion_period = models.CharField(max_length=100, blank=True, help_text='e.g. "6 months"')

    class Meta:
        db_table = 'dpr_proposed_building'
        verbose_name = 'DPR — Proposed Building'
        verbose_name_plural = 'DPR — Proposed Buildings'
        ordering = ['order', 'id']

    def __str__(self):
        return f'Proposed building #{self.pk}'


class DPRSiteDevelopmentItem(TimeStampedModel, AuditModel):
    """§2.3.14 Cat C — one site development work item."""

    section = models.ForeignKey(
        DPRSectionCivil,
        on_delete=models.CASCADE,
        related_name='site_development_items',
    )
    order = models.IntegerField(default=0)

    category = models.ForeignKey(
        'database.DPRCivilCategory',
        on_delete=models.PROTECT,
        related_name='+',
    )
    category_other = models.CharField(max_length=200, blank=True)
    estimated_quantity = models.CharField(max_length=200, blank=True, help_text='Free text — e.g. "500 m", "2 units"')
    estimated_cost = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    remarks = models.TextField(blank=True)

    class Meta:
        db_table = 'dpr_site_development_item'
        verbose_name = 'DPR — Site Development Item'
        verbose_name_plural = 'DPR — Site Development Items'
        ordering = ['order', 'id']

    def __str__(self):
        return f'{self.category_id} — section {self.section_id}'
