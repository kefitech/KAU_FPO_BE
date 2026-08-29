"""
DPR §2.3.2 — Project Components.

Simplest section in the spec: multi-select checkbox across 6 groups + optional
"Others (Specify)" per group. Drives the future dynamic-questionnaire engine
(Phase 3): which sections are shown depends on which components are selected.

One table:
    DPRSectionComponents — 1:1 with project. M2M to DPRComponent + 6 companion
    CharFields for the "Others (Specify)" text per component group.
"""

from django.db import models

from apps.core.models.base import TimeStampedModel, AuditModel


class DPRSectionComponents(TimeStampedModel, AuditModel):
    """§2.3.2 section — one row per project."""

    project = models.OneToOneField(
        'database.DPRProject',
        on_delete=models.CASCADE,
        related_name='section_components',
    )
    components = models.ManyToManyField(
        'database.DPRComponent',
        blank=True,
        related_name='+',
        help_text='Selected project components (multi-select across 6 KAU groups)',
    )

    # "Others (Specify)" per group — filled when the corresponding "_other" component is selected
    other_primary_production = models.CharField(max_length=200, blank=True)
    other_processing = models.CharField(max_length=200, blank=True)
    other_storage = models.CharField(max_length=200, blank=True)
    other_marketing = models.CharField(max_length=200, blank=True)
    other_service = models.CharField(max_length=200, blank=True)
    other_supporting = models.CharField(max_length=200, blank=True)

    is_complete = models.BooleanField(default=False)

    class Meta:
        db_table = 'dpr_section_components'
        verbose_name = 'DPR — Components Section'
        verbose_name_plural = 'DPR — Components Sections'

    def __str__(self):
        return f'Components section for project {self.project_id}'
