"""
DPR §2.3.20 — Environmental, Social and Sustainability Assessment.

Three tables:
    DPRSectionESS                     — 1:1 (Cat B + D + E + F + G section-level)
    DPREnvironmentalImpactSelection   — N per section (Cat A — FK to DPREnvironmentalImpact + per-impact details)
    DPRClimateRiskSelection           — N per section (Cat C — FK to DPRClimateRisk + per-risk mitigation)

Masters used:
    DPREnvironmentalImpact  — 10 items (Cat A)
    DPRClimateRisk          — 8 items (Cat C)
"""

from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.core.models.base import TimeStampedModel, AuditModel


RESOURCE_CHOICES = [
    ('electricity',       'Electricity'),
    ('water',             'Water'),
    ('fuel',              'Fuel'),
    ('raw_materials',     'Raw Materials'),
    ('packaging',         'Packaging Materials'),
]

CONSERVATION_MEASURE_CHOICES = [
    ('water_conservation',  'Water Conservation'),
    ('energy_conservation', 'Energy Conservation'),
    ('waste_recycling',     'Waste Recycling'),
    ('rainwater_harvesting', 'Rainwater Harvesting'),
    ('solar_energy',        'Solar Energy'),
    ('biomass_utilisation', 'Biomass Utilisation'),
    ('other',               'Others (Specify)'),
]

SAFETY_MEASURE_CHOICES = [
    ('ppe',              'Personal Protective Equipment (PPE)'),
    ('fire_safety',      'Fire Safety'),
    ('first_aid',        'First Aid'),
    ('safety_signage',   'Safety Signage'),
    ('emergency_exit',   'Emergency Exit'),
    ('machine_guards',   'Machine Guards'),
    ('safety_training',  'Safety Training'),
    ('health_checkup',   'Health Check-up'),
    ('insurance',        'Insurance'),
    ('other',            'Others (Specify)'),
]

SUSTAINABILITY_INITIATIVE_CHOICES = [
    ('renewable_energy',       'Renewable Energy'),
    ('organic_production',     'Organic Production'),
    ('natural_farming',        'Natural Farming'),
    ('waste_recycling',        'Waste Recycling'),
    ('water_reuse',            'Water Reuse'),
    ('eco_packaging',          'Eco-friendly Packaging'),
    ('circular_economy',       'Circular Economy Practices'),
    ('resource_recovery',      'Resource Recovery'),
    ('carbon_reduction',       'Carbon Reduction Measures'),
    ('other',                  'Others (Specify)'),
]


class DPRSectionESS(TimeStampedModel, AuditModel):
    """§2.3.20 section — one row per project."""

    project = models.OneToOneField(
        'database.DPRProject',
        on_delete=models.CASCADE,
        related_name='section_ess',
    )

    # ── Cat B: Resource Utilisation ──
    resources_used = ArrayField(
        models.CharField(max_length=30, choices=RESOURCE_CHOICES),
        default=list, blank=True,
    )
    conservation_measures = ArrayField(
        models.CharField(max_length=30, choices=CONSERVATION_MEASURE_CHOICES),
        default=list, blank=True,
    )
    conservation_other = models.CharField(max_length=200, blank=True)
    annual_electricity_requirement = models.CharField(max_length=200, blank=True)
    annual_water_requirement = models.CharField(max_length=200, blank=True)
    annual_fuel_requirement = models.CharField(max_length=200, blank=True)

    # ── Cat D: Occupational Health & Safety ──
    safety_measures = ArrayField(
        models.CharField(max_length=30, choices=SAFETY_MEASURE_CHOICES),
        default=list, blank=True,
    )
    safety_other = models.CharField(max_length=200, blank=True)

    # ── Cat E: Social Impact ──
    farmers_benefited = models.IntegerField(null=True, blank=True)
    direct_jobs_created = models.IntegerField(null=True, blank=True)
    indirect_jobs_created = models.IntegerField(null=True, blank=True)
    women_beneficiaries = models.IntegerField(null=True, blank=True)
    youth_beneficiaries = models.IntegerField(null=True, blank=True)
    sc_st_beneficiaries = models.IntegerField(null=True, blank=True)
    small_marginal_farmers = models.IntegerField(null=True, blank=True)
    expected_income_increase = models.CharField(max_length=200, blank=True)
    expected_post_harvest_loss_reduction = models.CharField(max_length=200, blank=True)

    # ── Cat F: Sustainability Measures ──
    sustainability_initiatives = ArrayField(
        models.CharField(max_length=30, choices=SUSTAINABILITY_INITIATIVE_CHOICES),
        default=list, blank=True,
    )
    sustainability_other = models.CharField(max_length=200, blank=True)

    # ── Cat G: ESG (Optional) ──
    environmental_initiatives = models.TextField(blank=True)
    social_initiatives = models.TextField(blank=True)
    governance_practices = models.TextField(blank=True)

    is_complete = models.BooleanField(default=False)

    class Meta:
        db_table = 'dpr_section_ess'
        verbose_name = 'DPR — ESS Section'
        verbose_name_plural = 'DPR — ESS Sections'

    def __str__(self):
        return f'ESS section for project {self.project_id}'


class DPREnvironmentalImpactSelection(TimeStampedModel, AuditModel):
    """§2.3.20 Cat A — one environmental impact per row."""

    section = models.ForeignKey(
        DPRSectionESS,
        on_delete=models.CASCADE,
        related_name='environmental_impacts',
    )
    impact = models.ForeignKey(
        'database.DPREnvironmentalImpact',
        on_delete=models.PROTECT,
        related_name='+',
    )
    impact_other = models.CharField(max_length=200, blank=True)
    estimated_quantity = models.CharField(max_length=200, blank=True)
    source = models.CharField(max_length=300, blank=True)
    existing_control_measure = models.TextField(blank=True)
    proposed_mitigation_measure = models.TextField(blank=True)

    class Meta:
        db_table = 'dpr_environmental_impact_selection'
        verbose_name = 'DPR — Environmental Impact Selection'
        verbose_name_plural = 'DPR — Environmental Impact Selections'
        unique_together = [('section', 'impact')]
        ordering = ['id']

    def __str__(self):
        return f'{self.impact_id} — section {self.section_id}'


class DPRClimateRiskSelection(TimeStampedModel, AuditModel):
    """§2.3.20 Cat C — one climate risk per row with mitigation."""

    section = models.ForeignKey(
        DPRSectionESS,
        on_delete=models.CASCADE,
        related_name='climate_risks',
    )
    risk = models.ForeignKey(
        'database.DPRClimateRisk',
        on_delete=models.PROTECT,
        related_name='+',
    )
    risk_other = models.CharField(max_length=200, blank=True)
    expected_impact = models.TextField(blank=True)
    proposed_mitigation_strategy = models.TextField(blank=True)

    class Meta:
        db_table = 'dpr_climate_risk_selection'
        verbose_name = 'DPR — Climate Risk Selection'
        verbose_name_plural = 'DPR — Climate Risk Selections'
        unique_together = [('section', 'risk')]
        ordering = ['id']

    def __str__(self):
        return f'{self.risk_id} — section {self.section_id}'
