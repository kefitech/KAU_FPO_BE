"""
DPR §2.3.7 — Project Rationale.

Multi-select from 30 reasons (existing `DPRProjectRationale` master, 29 items + 1 "other")
with a mandatory per-selection justification (max 100 words).

Two tables:
    DPRSectionRationale     — 1:1 container + `rationale_other` free-text
    DPRRationaleSelection   — one row per (section, rationale) with justification
"""

from django.db import models

from apps.core.models.base import TimeStampedModel, AuditModel


class DPRSectionRationale(TimeStampedModel, AuditModel):
    """§2.3.7 section — one row per project."""

    project = models.OneToOneField(
        'database.DPRProject',
        on_delete=models.CASCADE,
        related_name='section_rationale',
    )
    rationale_other = models.CharField(
        max_length=200, blank=True,
        help_text='Free text — populated when the "other" master row is included in selections',
    )

    is_complete = models.BooleanField(default=False)

    class Meta:
        db_table = 'dpr_section_rationale'
        verbose_name = 'DPR — Rationale Section'
        verbose_name_plural = 'DPR — Rationale Sections'

    def __str__(self):
        return f'Rationale section for project {self.project_id}'


class DPRRationaleSelection(TimeStampedModel, AuditModel):
    """One selected rationale with its user-provided justification."""

    section = models.ForeignKey(
        DPRSectionRationale,
        on_delete=models.CASCADE,
        related_name='selections',
    )
    rationale = models.ForeignKey(
        'database.DPRProjectRationale',
        on_delete=models.PROTECT,
        related_name='+',
    )
    justification = models.TextField(
        blank=True,
        help_text='Brief justification, max 100 words per KAU spec §2.3.7. '
                  'Enforced by validator, not by serializer, so readiness endpoint can report the actual error.',
    )

    class Meta:
        db_table = 'dpr_rationale_selection'
        verbose_name = 'DPR — Rationale Selection'
        verbose_name_plural = 'DPR — Rationale Selections'
        unique_together = [('section', 'rationale')]
        ordering = ['id']

    def __str__(self):
        return f'{self.rationale_id} — section {self.section_id}'
