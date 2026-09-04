"""
DPR §2.3.9 — Project Capacity and Production System.

Single-table section covering 5 KAU sub-categories (A-E):
    A. Production Capacity (installed / practical / utilization / expansion toggle)
    B. Operating Schedule (working days / shifts / hours / months + peak/lean seasons)
    C. Production Process (description + type + automation + activities)
    D. Production Losses and Recovery (conditional on has_production_loss)
    E. Future Expansion (conditional on has_future_expansion)

ArrayField for month-based multi-selects. TextField for "major_activities" until
Phase 3 dynamic questionnaire engine converts it to component-driven M2M.
"""

from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.core.models.base import TimeStampedModel, AuditModel


MONTHS = [
    ('jan', 'January'), ('feb', 'February'), ('mar', 'March'), ('apr', 'April'),
    ('may', 'May'), ('jun', 'June'), ('jul', 'July'), ('aug', 'August'),
    ('sep', 'September'), ('oct', 'October'), ('nov', 'November'), ('dec', 'December'),
]

PROCESS_TYPE_CHOICES = [
    ('batch',       'Batch Process'),
    ('continuous',  'Continuous Process'),
    ('seasonal',    'Seasonal Process'),
    ('service_based', 'Service-based Operation'),
]

AUTOMATION_LEVEL_CHOICES = [
    ('manual',       'Manual'),
    ('semi_auto',    'Semi-Automatic'),
    ('auto',         'Automatic'),
    ('fully_auto',   'Fully Automatic'),
]

LOSS_SOURCE_CHOICES = [
    ('raw_material',   'Raw Material'),
    ('processing',     'Processing'),
    ('storage',        'Storage'),
    ('transportation', 'Transportation'),
    ('packaging',      'Packaging'),
    ('other',          'Others (Specify)'),
]

EXPANSION_NATURE_CHOICES = [
    ('capacity',       'Capacity Expansion'),
    ('product',        'Product Diversification'),
    ('infrastructure', 'Infrastructure Expansion'),
    ('technology',     'Technology Upgradation'),
    ('market',         'Market Expansion'),
    ('other',          'Others (Specify)'),
]


class DPRSectionCapacity(TimeStampedModel, AuditModel):
    """§2.3.9 section — one row per project."""

    project = models.OneToOneField(
        'database.DPRProject',
        on_delete=models.CASCADE,
        related_name='section_capacity',
    )

    # ── A. Production Capacity ──
    installed_capacity = models.DecimalField(max_digits=18, decimal_places=3, null=True, blank=True)
    capacity_unit = models.ForeignKey(
        'database.DPRCapacityUnit',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='+',
    )
    capacity_basis = models.ForeignKey(
        'database.DPRCapacityBasis',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='+',
    )
    practical_operating_capacity = models.DecimalField(max_digits=18, decimal_places=3, null=True, blank=True)
    first_year_capacity_utilisation_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    has_future_expansion = models.BooleanField(default=False)

    # ── B. Operating Schedule ──
    working_days_per_year = models.IntegerField(null=True, blank=True)
    shifts_per_day = models.IntegerField(null=True, blank=True)
    operating_hours_per_shift = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    operating_months_per_year = models.IntegerField(null=True, blank=True)
    peak_production_seasons = ArrayField(
        models.CharField(max_length=3, choices=MONTHS),
        default=list, blank=True,
    )
    lean_production_seasons = ArrayField(
        models.CharField(max_length=3, choices=MONTHS),
        default=list, blank=True,
    )

    # ── C. Production Process ──
    process_description = models.TextField(
        blank=True,
        help_text='Max 150 words per KAU spec. Enforced by validator.',
    )
    process_type = models.CharField(max_length=20, choices=PROCESS_TYPE_CHOICES, blank=True)
    automation_level = models.CharField(max_length=20, choices=AUTOMATION_LEVEL_CHOICES, blank=True)
    major_activities = models.TextField(
        blank=True,
        help_text='Free text for Phase 2. Phase 3 will convert to component-driven M2M via dynamic questionnaire engine.',
    )
    technology_method = models.CharField(max_length=300, blank=True)

    # ── D. Production Losses and Recovery ──
    has_production_loss = models.BooleanField(default=False)
    production_loss_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    product_recovery_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    loss_sources = ArrayField(
        models.CharField(max_length=20, choices=LOSS_SOURCE_CHOICES),
        default=list, blank=True,
    )
    loss_source_other = models.CharField(max_length=200, blank=True)

    # ── E. Future Expansion (only shown if has_future_expansion=True) ──
    expected_year_of_expansion = models.IntegerField(null=True, blank=True)
    expansion_nature = models.CharField(max_length=20, choices=EXPANSION_NATURE_CHOICES, blank=True)
    expansion_nature_other = models.CharField(max_length=200, blank=True)
    expansion_description = models.TextField(blank=True)

    is_complete = models.BooleanField(default=False)

    class Meta:
        db_table = 'dpr_section_capacity'
        verbose_name = 'DPR — Capacity Section'
        verbose_name_plural = 'DPR — Capacity Sections'

    def __str__(self):
        return f'Capacity section for project {self.project_id}'
