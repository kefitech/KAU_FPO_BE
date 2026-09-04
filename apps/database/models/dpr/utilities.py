"""
DPR §2.3.16 — Utilities and Support Services.

Five tables:
    DPRSectionUtilities              — 1:1 (Cat A + B + D + G section + Cat H + I ArrayField multi-selects)
    DPRFuelUsage                     — N per section (Cat C — FK to DPRFuelType + per-fuel data)
    DPRProcessUtility                — N per section (Cat E — compressed air/steam/boiler/hot water)
    DPRWasteManagement               — N per section (Cat F — FK to DPRWasteType + per-waste disposal)
    DPRRenewableInitiativeSelection  — N per section (Cat J — FK to DPRRenewableInitiative + capacity/cost/savings)

Masters used:
    DPRFuelType             — 10 items (Cat C)
    DPRWasteType            — 8 items (Cat F)
    DPRRenewableInitiative  — Cat J
"""

from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.core.models.base import TimeStampedModel, AuditModel


ELECTRICITY_SUPPLY_CHOICES = [
    ('single_phase', 'Single Phase'),
    ('three_phase',  'Three Phase'),
    ('ht',           'HT Connection'),
    ('lt',           'LT Connection'),
]

WATER_SOURCE_CHOICES = [
    ('borewell',           'Borewell'),
    ('open_well',          'Open Well'),
    ('panchayat_supply',   'Panchayat Water Supply'),
    ('municipal_supply',   'Municipal Water Supply'),
    ('river',              'River'),
    ('canal',              'Canal'),
    ('tank',               'Tank'),
    ('rainwater_harvesting', 'Rainwater Harvesting'),
    ('private_supply',     'Private Supply'),
    ('other',              'Others (Specify)'),
]

PROCESS_UTILITY_TYPE_CHOICES = [
    ('compressed_air', 'Compressed Air'),
    ('steam',          'Steam'),
    ('boiler',         'Boiler'),
    ('hot_water',      'Hot Water'),
]

COMMUNICATION_CHOICES = [
    ('broadband_internet', 'Broadband Internet'),
    ('mobile_internet',    'Mobile Internet'),
    ('wifi',               'Wi-Fi'),
    ('cctv',               'CCTV'),
    ('fibre',              'Fibre Connection'),
    ('erp',                'ERP Software'),
    ('accounting',         'Accounting Software'),
    ('inventory',          'Inventory Software'),
    ('barcode',            'Barcode System'),
    ('qr_code',            'QR Code System'),
    ('digital_weighing',   'Digital Weighing'),
    ('biometric',          'Biometric Attendance'),
    ('cloud_backup',       'Cloud Backup'),
    ('other',              'Others (Specify)'),
]

FIRE_SAFETY_CHOICES = [
    ('fire_extinguishers', 'Fire Extinguishers'),
    ('first_aid',          'First Aid Kit'),
    ('ppe',                'PPE'),
    ('emergency_exit',     'Emergency Exit'),
    ('fire_alarm',         'Fire Alarm'),
    ('fire_hydrant',       'Fire Hydrant'),
    ('smoke_detector',     'Smoke Detector'),
    ('emergency_lighting', 'Emergency Lighting'),
    ('safety_signage',     'Safety Signage'),
    ('other',              'Others (Specify)'),
]


class DPRSectionUtilities(TimeStampedModel, AuditModel):
    """§2.3.16 section — one row per project."""

    project = models.OneToOneField(
        'database.DPRProject',
        on_delete=models.CASCADE,
        related_name='section_utilities',
    )

    # ── Cat A: Electricity ──
    electricity_required = models.BooleanField(default=False)
    existing_electricity_connection = models.BooleanField(null=True, blank=True)
    electricity_supply_type = models.CharField(max_length=20, choices=ELECTRICITY_SUPPLY_CHOICES, blank=True)
    backup_power_required = models.BooleanField(null=True, blank=True)
    consumer_number = models.CharField(max_length=100, blank=True)
    connected_load_kw = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    contract_demand_kva = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    additional_load_required = models.CharField(max_length=200, blank=True)
    generator_capacity = models.CharField(max_length=200, blank=True)
    dg_set_required = models.BooleanField(default=False)
    ups_required = models.BooleanField(default=False)
    solar_backup_proposed = models.BooleanField(default=False)

    # ── Cat B: Water ──
    water_required = models.BooleanField(default=False)
    water_source = models.CharField(max_length=30, choices=WATER_SOURCE_CHOICES, blank=True)
    water_source_other = models.CharField(max_length=200, blank=True)
    water_available_year_round = models.BooleanField(null=True, blank=True)
    daily_water_requirement = models.CharField(max_length=200, blank=True)
    peak_water_requirement = models.CharField(max_length=200, blank=True)
    annual_water_requirement = models.CharField(max_length=200, blank=True)
    water_storage_capacity = models.CharField(max_length=200, blank=True)
    water_treatment_required = models.TextField(blank=True)

    # ── Cat D: Refrigeration and Cooling ──
    refrigeration_required = models.BooleanField(default=False)
    temperature_range = models.CharField(max_length=200, blank=True)
    cooling_capacity = models.CharField(max_length=200, blank=True)
    cold_room_size = models.CharField(max_length=200, blank=True)
    num_chambers = models.IntegerField(null=True, blank=True)
    refrigerant_type = models.CharField(max_length=200, blank=True)
    refrigeration_backup_arrangement = models.CharField(max_length=200, blank=True)

    # ── Cat G: Effluent Management ──
    generates_effluent = models.BooleanField(default=False)
    effluent_quantity = models.CharField(max_length=200, blank=True)
    effluent_treatment_required = models.CharField(max_length=200, blank=True)
    effluent_treatment_method = models.TextField(blank=True)
    effluent_disposal_method = models.CharField(max_length=200, blank=True)
    effluent_reuse_proposed = models.TextField(blank=True)

    # ── Cat H: Communication & Digital ──
    communication_items = ArrayField(
        models.CharField(max_length=30, choices=COMMUNICATION_CHOICES),
        default=list, blank=True,
    )
    communication_other = models.CharField(max_length=200, blank=True)

    # ── Cat I: Fire & Safety ──
    fire_safety_items = ArrayField(
        models.CharField(max_length=30, choices=FIRE_SAFETY_CHOICES),
        default=list, blank=True,
    )
    fire_safety_other = models.CharField(max_length=200, blank=True)

    is_complete = models.BooleanField(default=False)

    class Meta:
        db_table = 'dpr_section_utilities'
        verbose_name = 'DPR — Utilities Section'
        verbose_name_plural = 'DPR — Utilities Sections'

    def __str__(self):
        return f'Utilities section for project {self.project_id}'


class DPRFuelUsage(TimeStampedModel, AuditModel):
    """§2.3.16 Cat C — one fuel per row with usage details."""

    section = models.ForeignKey(
        DPRSectionUtilities,
        on_delete=models.CASCADE,
        related_name='fuels',
    )
    fuel = models.ForeignKey(
        'database.DPRFuelType',
        on_delete=models.PROTECT,
        related_name='+',
    )
    fuel_other = models.CharField(max_length=200, blank=True)
    purpose = models.CharField(max_length=500, blank=True)
    daily_consumption = models.CharField(max_length=200, blank=True)
    annual_consumption = models.CharField(max_length=200, blank=True)
    estimated_annual_cost = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    class Meta:
        db_table = 'dpr_fuel_usage'
        verbose_name = 'DPR — Fuel Usage'
        verbose_name_plural = 'DPR — Fuel Usages'
        unique_together = [('section', 'fuel')]
        ordering = ['id']

    def __str__(self):
        return f'{self.fuel_id} — section {self.section_id}'


class DPRProcessUtility(TimeStampedModel, AuditModel):
    """§2.3.16 Cat E — compressed air / steam / boiler / hot water."""

    section = models.ForeignKey(
        DPRSectionUtilities,
        on_delete=models.CASCADE,
        related_name='process_utilities',
    )
    utility_type = models.CharField(max_length=20, choices=PROCESS_UTILITY_TYPE_CHOICES)
    purpose = models.CharField(max_length=500, blank=True)
    capacity = models.CharField(max_length=200, blank=True)
    source = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table = 'dpr_process_utility'
        verbose_name = 'DPR — Process Utility'
        verbose_name_plural = 'DPR — Process Utilities'
        unique_together = [('section', 'utility_type')]
        ordering = ['id']

    def __str__(self):
        return f'{self.get_utility_type_display()} — section {self.section_id}'


class DPRWasteManagement(TimeStampedModel, AuditModel):
    """§2.3.16 Cat F — one waste type per row with disposal method."""

    section = models.ForeignKey(
        DPRSectionUtilities,
        on_delete=models.CASCADE,
        related_name='wastes',
    )
    waste = models.ForeignKey(
        'database.DPRWasteType',
        on_delete=models.PROTECT,
        related_name='+',
    )
    waste_other = models.CharField(max_length=200, blank=True)
    disposal_method = models.TextField(
        blank=True,
        help_text='Required per KAU spec — enforced by validator',
    )
    estimated_quantity = models.CharField(max_length=200, blank=True)
    utilisation_method = models.TextField(blank=True)
    revenue_from_byproducts = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    class Meta:
        db_table = 'dpr_waste_management'
        verbose_name = 'DPR — Waste Management'
        verbose_name_plural = 'DPR — Waste Management Items'
        unique_together = [('section', 'waste')]
        ordering = ['id']

    def __str__(self):
        return f'{self.waste_id} — section {self.section_id}'


class DPRRenewableInitiativeSelection(TimeStampedModel, AuditModel):
    """§2.3.16 Cat J — one renewable energy initiative per row."""

    section = models.ForeignKey(
        DPRSectionUtilities,
        on_delete=models.CASCADE,
        related_name='renewable_initiatives',
    )
    initiative = models.ForeignKey(
        'database.DPRRenewableInitiative',
        on_delete=models.PROTECT,
        related_name='+',
    )
    initiative_other = models.CharField(max_length=200, blank=True)
    capacity = models.CharField(max_length=200, blank=True)
    estimated_cost = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    expected_annual_savings = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    class Meta:
        db_table = 'dpr_renewable_initiative_selection'
        verbose_name = 'DPR — Renewable Initiative Selection'
        verbose_name_plural = 'DPR — Renewable Initiative Selections'
        unique_together = [('section', 'initiative')]
        ordering = ['id']

    def __str__(self):
        return f'{self.initiative_id} — section {self.section_id}'
