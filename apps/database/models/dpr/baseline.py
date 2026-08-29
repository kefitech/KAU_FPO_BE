"""
DPR §2.3.8 — Current Status (Baseline Information).

Conditional questionnaire: `currently_engaged` (Yes/No) branches to two field sets:
    Yes → existing enterprise fields (products/capacity/turnover/employees/etc.)
    No  → new venture fields (reason/previous experience/proposed approach/etc.)

Single-table design. All fields nullable/blank. Validator enforces the branch.
"""

from django.db import models

from apps.core.models.base import TimeStampedModel, AuditModel


class DPRSectionBaseline(TimeStampedModel, AuditModel):
    """§2.3.8 section — one row per project."""

    project = models.OneToOneField(
        'database.DPRProject',
        on_delete=models.CASCADE,
        related_name='section_baseline',
    )

    currently_engaged = models.BooleanField(
        null=True, blank=True,
        help_text='True = existing enterprise, False = new venture. Null = not yet answered.',
    )

    # ── If Yes: existing enterprise fields ──
    existing_products = models.TextField(blank=True, help_text='Existing product(s) / service(s)')
    existing_installed_capacity = models.CharField(max_length=300, blank=True)
    current_annual_production = models.CharField(max_length=300, blank=True)
    current_annual_turnover = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    existing_infrastructure = models.TextField(blank=True)
    existing_machinery = models.TextField(blank=True)
    num_employees = models.IntegerField(null=True, blank=True)
    existing_market_coverage = models.TextField(blank=True)
    major_challenges = models.TextField(blank=True)
    current_capacity_utilization_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    existing_certifications = models.TextField(blank=True)

    # ── If No: new venture fields ──
    reason_for_proposing = models.TextField(blank=True)
    previous_experience = models.TextField(blank=True)
    technical_guidance_available = models.TextField(blank=True)
    proposed_implementation_approach = models.TextField(blank=True)
    similar_projects_visited = models.TextField(blank=True)

    is_complete = models.BooleanField(default=False)

    class Meta:
        db_table = 'dpr_section_baseline'
        verbose_name = 'DPR — Baseline Section'
        verbose_name_plural = 'DPR — Baseline Sections'

    def __str__(self):
        return f'Baseline section for project {self.project_id}'
