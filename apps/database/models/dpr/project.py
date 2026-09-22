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

    # ── Promoter Profile detail (KAU AI review 2026-09-19) ────────────────
    # Documents/DPR-RESPONSE/AI.docx §Promoter Profile para 35 asked us to
    # capture these fields directly so the DPR narrative stops emitting
    # placeholders like [Name of the CEO] / [PSC] / [women shareholding].
    #
    # Sits on DPRProject (not FPO) because:
    #   - FPO PATCH is locked once the FPO is APPROVED, but the DPR wizard
    #     still allows section edits until the DPR is generated — so FPOs
    #     can actually FILL these fields.
    #   - Values get time-locked per DPR: if the CEO changes next year,
    #     historical DPRs keep the CEO they cited.
    #   - PSC (Project Steering Committee) is scheme/project-scoped in
    #     practice — different DPRs may have different PSCs.
    # If KAU later asks for a proper "Promoter Profile" wizard section, we
    # extract these 8 fields into a DPRSectionPromoter model. Trivial migration.
    ceo_name                = models.CharField(
        max_length=200, blank=True,
        help_text='Full name of the FPO CEO / Chief Executive at the time of this DPR.',
    )
    ceo_qualification       = models.CharField(
        max_length=200, blank=True,
        help_text='CEO qualification (e.g. B.Sc Agri, MBA Agri-business).',
    )
    ceo_experience_years    = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text='Years of relevant experience the CEO brings to the FPO.',
    )
    total_area_acreage      = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text='Total farming area (in acres) covered by all member farmers of the FPO.',
    )
    women_shareholding_pct  = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text='Share of total paid-up capital held by women members (%). '
                  'Distinct from FPO.women_directors which is a governance count.',
    )
    landholding_summary     = models.TextField(
        blank=True,
        help_text="Free-text summary of member landholding pattern — e.g. "
                  "'70% smallholders under 2 acres, 25% medium 2-5 acres, "
                  "5% above 5 acres'. Used verbatim in the DPR narrative.",
    )
    board_meeting_frequency = models.CharField(
        max_length=20, blank=True,
        choices=[
            ('monthly',      'Monthly'),
            ('quarterly',    'Quarterly'),
            ('half_yearly',  'Half-yearly'),
            ('annually',     'Annually'),
        ],
        help_text='How often the Board of Directors meets.',
    )
    # PSC = Project Steering Committee — scheme-mandated body supervising
    # project implementation. Stored as JSON list of
    # {"name": str, "role": str, "affiliation": str} rows so a variable
    # count of members can be captured without a separate table.
    psc_members             = models.JSONField(
        default=list, blank=True,
        help_text='Project Steering Committee membership: list of '
                  '{name, role, affiliation} dicts. Empty list = no PSC constituted.',
    )

    # KAU RCD replies C.6 + C.7 (2026-09-02) — field-level provenance tracking.
    # Shape: { "<section_key>": { "<field_name>": "<source>" } }
    # source ∈ {"user_entered", "ai_inferred", "system_default", "user_overridden"}
    # Absence of a key implies "user_entered" (the default).
    #
    # Storing this at project root (not per-section) so:
    #   - one migration column vs 21 per-section columns
    #   - Phase 3 can add source entries without any schema change
    #   - queryable centrally for audit + PDF badge rendering
    #
    # Consumers should use the helpers in apps/fpo/services/dpr/field_sources.py
    # rather than reading/writing this dict directly.
    field_sources = models.JSONField(
        default=dict, blank=True,
        help_text='Per-field provenance map: {section_key: {field_name: source}}. '
                  "source ∈ user_entered / ai_inferred / system_default / user_overridden. "
                  'See apps/fpo/services/dpr/field_sources.py for accessor helpers.',
    )

    # Timestamp of the last IN_PROGRESS → SUBMITTED transition (Finish click).
    # Null while the DPR is still DRAFT / IN_PROGRESS. Re-set every time the
    # FPO re-clicks Finish after having reverted (edited a section after
    # submit bumps status back to IN_PROGRESS). Admin dashboards sort/filter
    # by this to build the review queue.
    submitted_at = models.DateTimeField(
        null=True, blank=True, db_index=True,
        help_text='UTC timestamp of the most recent transition to SUBMITTED. '
                  'Null while the DPR has never been finished.',
    )

    class Meta:
        db_table = 'dpr_project'
        verbose_name = 'DPR — Project'
        verbose_name_plural = 'DPR — Projects'
        ordering = ['-created_at']

    def __str__(self):
        return f'DPR {self.uuid} ({self.status})'
