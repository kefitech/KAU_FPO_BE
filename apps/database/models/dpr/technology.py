"""
DPR §2.3.12 — Technology Selection and Technical Feasibility.

Supports MULTIPLE technologies per project (spec: "grading, processing, drying,
packaging, storage, cold chain, value addition, service delivery, etc.").

Three tables:
    DPRSectionTechnology     — 1:1 with project (container)
    DPRTechnology            — N per section (covers Cat A + B + C + D + E + F + G per technology)
    DPRTechnologyRisk        — N per technology (Cat H — risk with mitigation)

Master FKs used (all seeded):
    DPRTechnologyReason      — Cat B reasons (16 items incl. "other")
    DPRQualityStandard       — Cat E certifications (13 items incl. FSSAI, AGMARK, etc.)
"""

from django.db import models

from apps.core.models.base import TimeStampedModel, AuditModel


TECHNOLOGY_STATUS_CHOICES = [
    ('proven',       'Proven Technology'),
    ('commercial',   'Commercially Established'),
    ('pilot',        'Pilot Technology'),
    ('emerging',     'Emerging Technology'),
    ('indigenous',   'Indigenous Technology'),
    ('imported',     'Imported Technology'),
    ('traditional',  'Traditional Technology'),
    ('other',        'Others (Specify)'),
]

PROCESS_TYPE_CHOICES = [
    ('batch',         'Batch Process'),
    ('continuous',    'Continuous Process'),
    ('seasonal',      'Seasonal Process'),
    ('service_based', 'Service-based Operation'),
]

AUTOMATION_LEVEL_CHOICES = [
    ('manual',      'Manual'),
    ('semi_auto',   'Semi-Automatic'),
    ('auto',        'Automatic'),
    ('fully_auto',  'Fully Automatic'),
]

TECH_RISK_CHOICES = [
    ('obsolescence',       'Technology Obsolescence'),
    ('skilled_labour',     'Skilled Labour Shortage'),
    ('spare_parts',        'Spare Parts Availability'),
    ('breakdown',          'Frequent Breakdown'),
    ('high_maintenance',   'High Maintenance Cost'),
    ('vendor_dependency',  'Vendor Dependency'),
    ('utility_dependency', 'Utility Dependency'),
    ('quality_issues',     'Product Quality Issues'),
    ('other',              'Others (Specify)'),
]


class DPRSectionTechnology(TimeStampedModel, AuditModel):
    """§2.3.12 section container. One-to-one with DPRProject."""

    project = models.OneToOneField(
        'database.DPRProject',
        on_delete=models.CASCADE,
        related_name='section_technology',
    )
    is_complete = models.BooleanField(default=False)

    class Meta:
        db_table = 'dpr_section_technology'
        verbose_name = 'DPR — Technology Section'
        verbose_name_plural = 'DPR — Technology Sections'

    def __str__(self):
        return f'Technology section for project {self.project_id}'


class DPRTechnology(TimeStampedModel, AuditModel):
    """One technology row — covers Cat A + B + C + D + E + F + G."""

    section = models.ForeignKey(
        DPRSectionTechnology,
        on_delete=models.CASCADE,
        related_name='technologies',
    )
    order = models.IntegerField(default=0)

    # ── Cat A: Technology Details ──
    name = models.CharField(max_length=200)
    nature = models.CharField(max_length=200, blank=True, help_text='Nature of technology (free text)')
    description = models.TextField(blank=True, help_text='Max 150 words per KAU spec, enforced by validator')
    source = models.CharField(max_length=200, blank=True, help_text='Source of technology')
    technology_provider = models.CharField(max_length=200, blank=True)
    country_of_origin = models.CharField(max_length=100, blank=True)
    year_introduced = models.IntegerField(null=True, blank=True)
    technology_status = models.CharField(max_length=20, choices=TECHNOLOGY_STATUS_CHOICES, blank=True)
    technology_status_other = models.CharField(max_length=200, blank=True)

    # ── Cat B: Selection ──
    reasons = models.ManyToManyField(
        'database.DPRTechnologyReason',
        blank=True,
        related_name='+',
    )
    reasons_other = models.CharField(max_length=200, blank=True)
    selection_justification = models.TextField(
        blank=True,
        help_text='Brief justification, max 100 words per KAU spec',
    )

    # ── Cat C: Production Process ──
    process_description = models.TextField(blank=True)
    process_type = models.CharField(max_length=20, choices=PROCESS_TYPE_CHOICES, blank=True)
    automation_level = models.CharField(max_length=20, choices=AUTOMATION_LEVEL_CHOICES, blank=True)
    process_flow_sequence = models.TextField(blank=True)
    critical_control_points = models.TextField(blank=True)
    quality_control_points = models.TextField(blank=True)
    bottleneck_operations = models.TextField(blank=True)

    # ── Cat D: Performance ──
    expected_production_efficiency = models.CharField(max_length=200, blank=True)
    expected_recovery = models.CharField(max_length=200, blank=True)
    energy_efficiency = models.CharField(max_length=200, blank=True)
    water_efficiency = models.CharField(max_length=200, blank=True)
    labour_efficiency = models.CharField(max_length=200, blank=True)
    machine_utilisation = models.CharField(max_length=200, blank=True)
    maintenance_frequency = models.CharField(max_length=200, blank=True)
    expected_technology_life_years = models.IntegerField(null=True, blank=True)

    # ── Cat E: Quality Standards ──
    quality_standards_applicable = models.BooleanField(default=False)
    product_quality_standard = models.CharField(max_length=200, blank=True)
    certification_required = models.BooleanField(null=True, blank=True)
    product_specification = models.TextField(blank=True)
    testing_requirement = models.TextField(blank=True)
    laboratory_requirement = models.TextField(blank=True)
    traceability_requirement = models.TextField(blank=True)
    food_safety_requirement = models.TextField(blank=True)
    certifications = models.ManyToManyField(
        'database.DPRQualityStandard',
        blank=True,
        related_name='+',
    )
    certifications_other = models.CharField(max_length=200, blank=True)

    # ── Cat F: Technical Expertise ──
    requires_skilled_operators = models.BooleanField(null=True, blank=True)
    requires_training = models.BooleanField(null=True, blank=True)
    technical_expert_available = models.TextField(blank=True)
    requires_consultant = models.BooleanField(null=True, blank=True)
    tech_transfer_agreement = models.BooleanField(null=True, blank=True)
    technical_collaboration = models.TextField(blank=True)
    amc_requirement = models.BooleanField(null=True, blank=True)
    vendor_support_available = models.BooleanField(null=True, blank=True)

    # ── Cat G: Future Technology Upgradation ──
    upgradation_planned = models.BooleanField(default=False)
    upgradation_year = models.IntegerField(null=True, blank=True)
    upgradation_description = models.TextField(blank=True)
    upgradation_cost = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    additional_infra_required = models.TextField(blank=True)
    additional_machinery_required = models.TextField(blank=True)

    class Meta:
        db_table = 'dpr_technology'
        verbose_name = 'DPR — Technology'
        verbose_name_plural = 'DPR — Technologies'
        ordering = ['order', 'id']

    def __str__(self):
        return self.name or f'Technology #{self.pk}'


class DPRTechnologyRisk(TimeStampedModel, AuditModel):
    """§2.3.12 Cat H — one risk per row, with mandatory mitigation."""

    technology = models.ForeignKey(
        DPRTechnology,
        on_delete=models.CASCADE,
        related_name='risks',
    )
    risk_type = models.CharField(max_length=30, choices=TECH_RISK_CHOICES)
    risk_type_other = models.CharField(max_length=200, blank=True)
    mitigation_measure = models.TextField(
        blank=True,
        help_text='Required per KAU spec — enforced by validator, not model, so readiness can report it',
    )
    existing_practice = models.TextField(blank=True)

    class Meta:
        db_table = 'dpr_technology_risk'
        verbose_name = 'DPR — Technology Risk'
        verbose_name_plural = 'DPR — Technology Risks'
        ordering = ['id']

    def __str__(self):
        return f'{self.get_risk_type_display()} — technology {self.technology_id}'
