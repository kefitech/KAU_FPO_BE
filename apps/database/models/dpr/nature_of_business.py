"""
DPR §2.3.3 — Nature of Business.

Single-table section: multi-select from 15 options + one "Others (Specify)" text field.
Master `DPRNatureOfBusiness` (15 rows already seeded, incl. code='other').
"""

from django.db import models

from apps.core.models.base import TimeStampedModel, AuditModel


class DPRSectionNatureOfBusiness(TimeStampedModel, AuditModel):
    """§2.3.3 section — one row per project."""

    project = models.OneToOneField(
        'database.DPRProject',
        on_delete=models.CASCADE,
        related_name='section_nature_of_business',
    )
    natures = models.ManyToManyField(
        'database.DPRNatureOfBusiness',
        blank=True,
        related_name='+',
        help_text='Selected nature(s) of business — multi-select',
    )
    nature_other = models.CharField(
        max_length=200, blank=True,
        help_text='Populated when the "other" master row is included in natures',
    )

    is_complete = models.BooleanField(default=False)

    class Meta:
        db_table = 'dpr_section_nature_of_business'
        verbose_name = 'DPR — Nature of Business Section'
        verbose_name_plural = 'DPR — Nature of Business Sections'

    def __str__(self):
        return f'NatureOfBusiness section for project {self.project_id}'
