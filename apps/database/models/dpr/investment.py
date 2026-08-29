"""
DPR §2.3.4 — Proposed Project Investment.

Single-table section. Conditional per KAU spec — user MAY enter a preliminary
project cost estimate, or leave the section blank (system auto-computes from
Land + Civil + Machinery + Utilities + WC sections during DPR generation).
"""

from django.db import models

from apps.core.models.base import TimeStampedModel, AuditModel


BASIS_CHOICES = [
    ('consultant',        'Consultant Estimate'),
    ('preliminary_fpo',   'Preliminary Estimate by FPO'),
    ('machinery_quote',   'Machinery Quotations'),
    ('civil_estimate',    'Civil Estimate'),
    ('govt_estimate',     'Government Estimate'),
    ('not_yet_estimated', 'Not Yet Estimated'),
]


class DPRSectionInvestment(TimeStampedModel, AuditModel):
    """§2.3.4 section — one row per project."""

    project = models.OneToOneField(
        'database.DPRProject',
        on_delete=models.CASCADE,
        related_name='section_investment',
    )
    estimated_project_cost = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True,
        help_text='Optional. If provided, system compares against auto-computed cost during DPR generation.',
    )
    basis_of_estimate = models.CharField(max_length=30, choices=BASIS_CHOICES, blank=True)
    remarks = models.TextField(blank=True)

    is_complete = models.BooleanField(default=False)

    class Meta:
        db_table = 'dpr_section_investment'
        verbose_name = 'DPR — Investment Section'
        verbose_name_plural = 'DPR — Investment Sections'

    def __str__(self):
        return f'Investment section for project {self.project_id}'
