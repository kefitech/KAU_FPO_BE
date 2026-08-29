"""
DPR §2.3.13 — Land, Site Suitability and Infrastructure Readiness.

Supports MULTIPLE land parcels under a single project (per KAU spec Remarks).

Four tables:
    DPRSectionSite             — 1:1 with project. Cat B + D + E + F + G + toggles.
    DPRLandParcel              — N per section. Cat A (Land Details, one per parcel).
    DPRExistingInfrastructure  — N per section. Cat C (approach road, buildings, utilities, etc.).
    DPRSiteConstraint          — N per section. Cat H (flooding, water scarcity, etc. with mitigation).

Master FKs used (all seeded):
    DPRCapacityUnit         — parcel area unit
    DPRLandOwnershipType    — parcel ownership
"""

from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.core.models.base import TimeStampedModel, AuditModel


TERRAIN_CHOICES = [
    ('plain',      'Plain'),
    ('undulating', 'Undulating'),
    ('hilly',      'Hilly'),
    ('coastal',    'Coastal'),
    ('river_basin', 'River Basin'),
    ('other',      'Others (Specify)'),
]

ELECTRICITY_AVAILABILITY_CHOICES = [
    ('available',      'Available'),
    ('proposed',       'Proposed'),
    ('not_available',  'Not Available'),
]

WATER_AVAILABILITY_CHOICES = [
    ('available',      'Available'),
    ('not_available',  'Not Available'),
]

ROAD_CONNECTIVITY_CHOICES = [
    ('excellent', 'Excellent'),
    ('good',      'Good'),
    ('fair',      'Fair'),
    ('poor',      'Poor'),
]

WATER_SOURCE_CHOICES = [
    ('borewell',        'Borewell'),
    ('open_well',       'Open Well'),
    ('panchayat_supply', 'Panchayat Supply'),
    ('river',           'River'),
    ('canal',           'Canal'),
    ('tank',            'Tank'),
    ('other',           'Others'),
]

STATUTORY_APPROVAL_CHOICES = [
    ('land_conversion',       'Land Conversion'),
    ('building_permit',       'Building Permit'),
    ('factory_licence',       'Factory Licence'),
    ('pollution_clearance',   'Pollution Control Clearance'),
    ('fire_safety',           'Fire & Safety Approval'),
    ('electrical_approval',   'Electrical Approval'),
    ('ground_water_permit',   'Ground Water Permission'),
    ('panchayat_approval',    'Panchayat Approval'),
    ('municipality_approval', 'Municipality Approval'),
    ('environmental_clearance', 'Environmental Clearance'),
    ('other',                 'Others (Specify)'),
]

INFRA_TYPE_CHOICES = [
    ('approach_road',     'Approach Road'),
    ('office_building',   'Office Building'),
    ('storage_building',  'Storage Building'),
    ('processing_shed',   'Processing Shed'),
    ('electricity',       'Electricity'),
    ('drinking_water',    'Drinking Water'),
    ('toilets',           'Toilets'),
    ('drainage',          'Drainage'),
    ('other',             'Others (Specify)'),
]

CONSTRAINT_TYPE_CHOICES = [
    ('flooding',            'Flooding'),
    ('water_scarcity',      'Water Scarcity'),
    ('power_shortage',      'Power Shortage'),
    ('poor_road_access',    'Poor Road Access'),
    ('land_dispute',        'Land Dispute'),
    ('env_restriction',     'Environmental Restriction'),
    ('wildlife_restriction', 'Wildlife Restriction'),
    ('crz_restriction',     'CRZ Restriction'),
    ('forest_land',         'Forest Land'),
    ('high_transport_cost', 'High Transportation Cost'),
    ('labour_shortage',     'Labour Shortage'),
    ('other',               'Others (Specify)'),
]


class DPRSectionSite(TimeStampedModel, AuditModel):
    """§2.3.13 section — one row per project."""

    project = models.OneToOneField(
        'database.DPRProject',
        on_delete=models.CASCADE,
        related_name='section_site',
    )

    # ── B. Site Characteristics ──
    terrain = models.CharField(max_length=20, choices=TERRAIN_CHOICES, blank=True)
    terrain_other = models.CharField(max_length=200, blank=True)
    is_flood_prone = models.BooleanField(null=True, blank=True)
    water_available_year_round = models.BooleanField(null=True, blank=True)
    topography = models.CharField(max_length=200, blank=True)
    soil_type = models.CharField(max_length=200, blank=True)
    soil_bearing_capacity = models.CharField(max_length=200, blank=True)
    water_logging = models.CharField(max_length=200, blank=True)
    drainage_condition = models.CharField(max_length=200, blank=True)
    slope = models.CharField(max_length=200, blank=True)
    ground_water_level = models.CharField(max_length=200, blank=True)

    # ── D. Site Accessibility (distances in km) ──
    dist_major_market_km = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    dist_major_raw_material_source_km = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    dist_all_weather_road_km = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    dist_state_highway_km = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    dist_national_highway_km = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    dist_railway_station_km = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    dist_airport_km = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    dist_seaport_km = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    dist_collection_centre_km = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    dist_processing_centre_km = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    # ── E. Utility Availability ──
    electricity_availability = models.CharField(max_length=20, choices=ELECTRICITY_AVAILABILITY_CHOICES, blank=True)
    water_availability = models.CharField(max_length=20, choices=WATER_AVAILABILITY_CHOICES, blank=True)
    road_connectivity = models.CharField(max_length=20, choices=ROAD_CONNECTIVITY_CHOICES, blank=True)
    water_sources = ArrayField(
        models.CharField(max_length=30, choices=WATER_SOURCE_CHOICES),
        default=list, blank=True,
    )
    water_source_other = models.CharField(max_length=200, blank=True)
    has_fibre = models.BooleanField(default=False)
    has_broadband = models.BooleanField(default=False)
    has_mobile_network = models.BooleanField(default=False)
    internet_unavailable = models.BooleanField(default=False)

    # ── F. Statutory Suitability (approvals already obtained) ──
    approvals_available = ArrayField(
        models.CharField(max_length=30, choices=STATUTORY_APPROVAL_CHOICES),
        default=list, blank=True,
    )
    approvals_other = models.CharField(max_length=300, blank=True)
    pending_approvals_remarks = models.TextField(blank=True)

    # ── G. Future Expansion ──
    has_future_expansion = models.BooleanField(default=False)
    additional_land_available = models.CharField(max_length=200, blank=True)
    area_reserved_for_expansion = models.CharField(max_length=200, blank=True)
    future_buildings_planned = models.TextField(blank=True)
    utility_expansion_feasibility = models.TextField(blank=True)

    is_complete = models.BooleanField(default=False)

    class Meta:
        db_table = 'dpr_section_site'
        verbose_name = 'DPR — Site Section'
        verbose_name_plural = 'DPR — Site Sections'

    def __str__(self):
        return f'Site section for project {self.project_id}'


class DPRLandParcel(TimeStampedModel, AuditModel):
    """§2.3.13 Cat A — one land parcel per row. Multi-parcel support per KAU spec."""

    section = models.ForeignKey(
        DPRSectionSite,
        on_delete=models.CASCADE,
        related_name='parcels',
    )
    order = models.IntegerField(default=0)

    total_land_available = models.DecimalField(max_digits=15, decimal_places=4, null=True, blank=True)
    land_proposed_for_project = models.DecimalField(max_digits=15, decimal_places=4, null=True, blank=True)
    unit = models.ForeignKey(
        'database.DPRCapacityUnit',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='+',
    )
    village = models.CharField(max_length=100, blank=True)
    taluk = models.CharField(max_length=100, blank=True)
    district = models.CharField(max_length=100, blank=True)
    ownership = models.ForeignKey(
        'database.DPRLandOwnershipType',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='+',
    )
    ownership_other = models.CharField(max_length=200, blank=True)

    # Additional (optional)
    survey_number = models.CharField(max_length=200, blank=True)
    resurvey_number = models.CharField(max_length=200, blank=True)
    date_of_acquisition = models.DateField(null=True, blank=True)
    present_land_use = models.CharField(max_length=200, blank=True)
    previous_land_use = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table = 'dpr_land_parcel'
        verbose_name = 'DPR — Land Parcel'
        verbose_name_plural = 'DPR — Land Parcels'
        ordering = ['order', 'id']

    def __str__(self):
        return f'Parcel #{self.pk} ({self.village or "unnamed"})'


class DPRExistingInfrastructure(TimeStampedModel, AuditModel):
    """§2.3.13 Cat C — existing infrastructure item on site."""

    section = models.ForeignKey(
        DPRSectionSite,
        on_delete=models.CASCADE,
        related_name='existing_infrastructure',
    )
    order = models.IntegerField(default=0)
    infrastructure_type = models.CharField(max_length=30, choices=INFRA_TYPE_CHOICES)
    infrastructure_type_other = models.CharField(max_length=200, blank=True)
    condition = models.CharField(max_length=200, blank=True, help_text='Existing condition (free text)')
    approximate_area = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    year_of_construction = models.IntegerField(null=True, blank=True)
    renovation_required = models.BooleanField(null=True, blank=True)

    class Meta:
        db_table = 'dpr_existing_infrastructure'
        verbose_name = 'DPR — Existing Infrastructure'
        verbose_name_plural = 'DPR — Existing Infrastructure Items'
        ordering = ['order', 'id']

    def __str__(self):
        return f'{self.get_infrastructure_type_display()} — section {self.section_id}'


class DPRSiteConstraint(TimeStampedModel, AuditModel):
    """§2.3.13 Cat H — site constraint with mandatory mitigation."""

    section = models.ForeignKey(
        DPRSectionSite,
        on_delete=models.CASCADE,
        related_name='constraints',
    )
    constraint_type = models.CharField(max_length=30, choices=CONSTRAINT_TYPE_CHOICES)
    constraint_type_other = models.CharField(max_length=200, blank=True)
    mitigation_measure = models.TextField(
        blank=True,
        help_text='Required per KAU spec — enforced by validator',
    )
    existing_situation = models.TextField(blank=True)

    class Meta:
        db_table = 'dpr_site_constraint'
        verbose_name = 'DPR — Site Constraint'
        verbose_name_plural = 'DPR — Site Constraints'
        ordering = ['id']

    def __str__(self):
        return f'{self.get_constraint_type_display()} — section {self.section_id}'
