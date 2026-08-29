"""
DPR Project — root record for a Detailed Project Report.

§2.2 Project Identification fields (KAU spec):
  1. project_title            — Text, mandatory (stored on `title`)
  2. project_types            — M2M DPRProjectType (multi-select)
  3. brief_description        — Long Text, min 50 chars
  4. primary_commodity        — FK MasterLookup category='commodity'
  5. secondary_commodities    — M2M MasterLookup (optional)
  6. project_objectives (+_other) — M2M DPRProjectObjective + free-text "Other"
  7. expected_outcomes (+_other)  — M2M DPRProjectOutcome + free-text "Other"

Author: Athul Gopan (Kefi Tech Solutions)
"""
from django.db import models

from apps.core.models.base import BaseModel


class DPRProject(BaseModel):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        IN_PROGRESS = 'in_progress', 'In Progress'
        SUBMITTED = 'submitted', 'Submitted'
        GENERATED = 'generated', 'PDF Generated'

    fpo = models.ForeignKey(
        'database.FPO',
        on_delete=models.CASCADE,
        related_name='dpr_projects',
        help_text='FPO that owns this DPR project',
    )
    title = models.CharField(
        max_length=255, blank=True,
        help_text='§2.2 field 1 — Proposed Project Title. Mandatory; validator enforces non-blank on submit.',
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True,
    )

    # §2.2 field 2 — Project Type (multi-select from DPRProjectType master)
    project_types = models.ManyToManyField(
        'database.DPRProjectType', blank=True, related_name='projects',
        help_text='§2.2 field 2. Multi-select. New / Expansion / Diversification / …',
    )

    # §2.2 field 3 — Brief Description
    brief_description = models.TextField(
        blank=True,
        help_text='§2.2 field 3 — short description of the proposed project. Validator enforces min 50 chars on submit.',
    )

    # §2.2 field 4 — Primary Commodity (single, from shared MasterLookup)
    primary_commodity = models.ForeignKey(
        'core.MasterLookup', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='dpr_projects_primary',
        help_text="§2.2 field 4. Points to MasterLookup category='commodity'.",
    )

    # §2.2 field 5 — Secondary Commodities (optional multi-select)
    secondary_commodities = models.ManyToManyField(
        'core.MasterLookup', blank=True, related_name='dpr_projects_secondary',
        help_text="§2.2 field 5. Optional multi-select from MasterLookup category='commodity'.",
    )

    # §2.2 field 6 — Project Objectives (multi-select + Other free-text)
    project_objectives = models.ManyToManyField(
        'database.DPRProjectObjective', blank=True, related_name='projects',
        help_text='§2.2 field 6 — multi-select. At least one required on submit.',
    )
    project_objectives_other = models.CharField(
        max_length=500, blank=True,
        help_text="Free-text 'Other' entry when a matching objective is not in the master list.",
    )

    # §2.2 field 7 — Expected Outcomes (multi-select + Other free-text)
    expected_outcomes = models.ManyToManyField(
        'database.DPRProjectOutcome', blank=True, related_name='projects',
        help_text='§2.2 field 7 — multi-select. At least one required on submit.',
    )
    expected_outcomes_other = models.CharField(
        max_length=500, blank=True,
        help_text="Free-text 'Other' entry when a matching outcome is not in the master list.",
    )

    class Meta:
        db_table = 'dpr_project'
        verbose_name = 'DPR — Project'
        verbose_name_plural = 'DPR — Projects'
        ordering = ['-created_at']

    def __str__(self):
        return f'DPR {self.uuid} ({self.status})'
