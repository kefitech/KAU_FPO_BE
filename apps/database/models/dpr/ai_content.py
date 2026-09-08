"""
DPR §AI Content — per-chapter AI-generated narrative with version tracking.

Per KAU RCD reply B.5 (2026-09-02):
    "Where AI regeneration is offered, the previous AI-generated version and
     any user edits shall be preserved. Regeneration shall not silently
     overwrite the user's active version — the user shall be presented with
     both the existing version and the new candidate and explicitly choose
     which one becomes the active version."

Data model:
    One row per (project, chapter_key). Each row carries THREE version slots
    so the user can compare and choose:

        original_ai        — the FIRST AI-generated text; frozen after write
        user_edited        — the user's manual edit of the active narrative
                              (starts equal to original_ai; overwritten as
                              the user tweaks in place)
        candidate_regen    — the LATEST regeneration output waiting for the
                              user to Accept / Keep-existing / Merge

    `active_version` — pointer to which slot is currently the "live" text
                        shown on the DPR PDF (either 'user_edited' or, if the
                        user has just accepted a regen, effectively the same
                        slot after we promote candidate_regen into it).

Traceability (RCD A.2):
    Each slot carries a paired `*_kb_ids` JSONField listing which
    DPRKnowledgeEntry rows the AI cited when generating it. Nothing here
    references the KB entries via FK because entries can be superseded /
    deactivated later — the ID list stays as a historical trace even if the
    entry is gone.

Upstream staleness (RCD B.5):
    `is_stale` is set to True by the section-save hook (see
    apps/fpo/api/dpr/*_section.py) when a field feeding this chapter changes.
    The FE reads this flag to show an amber "Content may be stale — regenerate?"
    banner. Cleared automatically when a regen candidate is accepted.

Author: Athul Gopan (Kefi Tech Solutions)
"""
from django.db import models

from apps.core.models.base import TimeStampedModel, AuditModel


# Chapter keys — the narrative chapters that go into a DPR PDF. Kept as a
# module-level tuple (not a TextChoices) so callers can iterate for bulk
# operations. Order matches the PDF rendering order.
CHAPTER_KEYS = (
    'executive_summary',
    'project_background',
    'promoter_profile',
    'market_analysis',
    'technical_feasibility',
    'implementation_plan',
    'financial_analysis',
    'risk_analysis',
    'swot',
    'environmental_impact',
    'conclusion',
)

CHAPTER_LABELS = {
    'executive_summary':    'Executive Summary',
    'project_background':   'Project Background',
    'promoter_profile':     'Promoter Profile',
    'market_analysis':      'Market Analysis',
    'technical_feasibility': 'Technical Feasibility',
    'implementation_plan':  'Implementation Plan',
    'financial_analysis':   'Financial Analysis',
    'risk_analysis':        'Risk Analysis',
    'swot':                 'SWOT Analysis',
    'environmental_impact': 'Environmental Impact',
    'conclusion':           'Conclusion',
}

# Which DPR section keys feed which AI chapter — used by the section-save
# hook to mark chapters stale when their upstream inputs change. Keys align
# with DPR_SECTIONS in src/lib/api/dpr.ts.
CHAPTER_UPSTREAM_SECTIONS = {
    'executive_summary':     ['identification', 'components', 'investment', 'finance'],
    'project_background':    ['identification', 'rationale', 'baseline'],
    'promoter_profile':      ['identification'],
    'market_analysis':       ['market', 'products', 'capacity'],
    'technical_feasibility': ['technology', 'raw-material', 'machinery', 'utilities'],
    'implementation_plan':   ['implementation', 'site', 'civil'],
    'financial_analysis':    ['finance', 'investment', 'capacity'],
    'risk_analysis':         ['risk'],
    'swot':                  ['identification', 'market', 'rationale', 'baseline'],
    'environmental_impact':  ['ess', 'compliance'],
    'conclusion':            ['identification', 'rationale', 'finance', 'risk'],
}


class DPRAIContent(TimeStampedModel, AuditModel):
    """One AI narrative chapter per project. Three version slots preserved."""

    class Chapter(models.TextChoices):
        # Keep in sync with CHAPTER_KEYS / CHAPTER_LABELS above. Django needs
        # TextChoices for the CharField validation, but callers should prefer
        # the module-level constants for bulk iteration.
        EXECUTIVE_SUMMARY     = 'executive_summary',    'Executive Summary'
        PROJECT_BACKGROUND    = 'project_background',   'Project Background'
        PROMOTER_PROFILE      = 'promoter_profile',     'Promoter Profile'
        MARKET_ANALYSIS       = 'market_analysis',      'Market Analysis'
        TECHNICAL_FEASIBILITY = 'technical_feasibility', 'Technical Feasibility'
        IMPLEMENTATION_PLAN   = 'implementation_plan',  'Implementation Plan'
        FINANCIAL_ANALYSIS    = 'financial_analysis',   'Financial Analysis'
        RISK_ANALYSIS         = 'risk_analysis',        'Risk Analysis'
        SWOT                  = 'swot',                 'SWOT Analysis'
        ENVIRONMENTAL_IMPACT  = 'environmental_impact', 'Environmental Impact'
        CONCLUSION            = 'conclusion',           'Conclusion'

    class ActiveVersion(models.TextChoices):
        # `original_ai` is included even though the UI never resets to it —
        # a super-admin recovery path might need it later. Default is set to
        # `user_edited` in _ensure_row(); this enum just lists valid values.
        ORIGINAL_AI = 'original_ai', 'Original AI'
        USER_EDITED = 'user_edited', 'User-edited'

    project = models.ForeignKey(
        'database.DPRProject',
        on_delete=models.CASCADE,
        related_name='ai_content',
    )
    chapter = models.CharField(
        max_length=30, choices=Chapter.choices, db_index=True,
    )

    # ── Three version slots ─────────────────────────────────────────────────
    # `original_ai` — never overwritten after first save (frozen provenance).
    # `user_edited` — the live editable version; starts = original_ai.
    # `candidate_regen` — set by /generate/, cleared by /accept/ or /keep/.

    original_ai = models.TextField(
        blank=True,
        help_text='FIRST AI-generated text — frozen after first write. Used '
                  'in the diff view as the historical baseline.',
    )
    user_edited = models.TextField(
        blank=True,
        help_text='The current live version — either the original AI text or '
                  'the user\'s edit of it. This is what the DPR PDF renders.',
    )
    candidate_regen = models.TextField(
        blank=True,
        help_text='Latest regeneration output waiting for user Accept/Keep/'
                  'Merge decision. Empty when there is no pending candidate.',
    )

    # Paired KB citation lists (per slot). Never FK because KB entries can be
    # superseded — the ID stays as historical trace even after deactivation.
    original_ai_kb_ids = models.JSONField(
        default=list, blank=True,
        help_text='DPRKnowledgeEntry ids cited when the original AI text was '
                  'generated. Historical trace.',
    )
    candidate_regen_kb_ids = models.JSONField(
        default=list, blank=True,
        help_text='DPRKnowledgeEntry ids cited by the latest regeneration.',
    )
    active_kb_ids = models.JSONField(
        default=list, blank=True,
        help_text='DPRKnowledgeEntry ids the currently-active text is grounded '
                  'in. Set on generate (matches original_ai_kb_ids) and updated '
                  'on accept (from candidate_regen_kb_ids).',
    )

    # ── State ──────────────────────────────────────────────────────────────

    active_version = models.CharField(
        max_length=20, choices=ActiveVersion.choices,
        default=ActiveVersion.USER_EDITED,
        help_text='Which slot is the live version. Only "user_edited" is used '
                  'in practice; enum kept for future admin recovery flow.',
    )
    is_stale = models.BooleanField(
        default=False, db_index=True,
        help_text='True when an upstream section field has changed since the '
                  'current active text was generated. Cleared on accept/regen.',
    )
    stale_reason = models.CharField(
        max_length=200, blank=True,
        help_text='Which section change marked this chapter stale — e.g. '
                  '"market section updated 2026-09-05". For FE tooltip.',
    )

    generated_at = models.DateTimeField(
        null=True, blank=True,
        help_text='When the original AI text was first generated.',
    )
    candidate_generated_at = models.DateTimeField(
        null=True, blank=True,
        help_text='When the current candidate_regen was generated.',
    )

    class Meta:
        db_table = 'dpr_ai_content'
        verbose_name = 'DPR — AI Content'
        verbose_name_plural = 'DPR — AI Content'
        ordering = ['project', 'chapter']
        unique_together = [('project', 'chapter')]
        indexes = [
            models.Index(fields=['project', 'chapter']),
            models.Index(fields=['project', 'is_stale']),
        ]

    def __str__(self):
        return f'{self.project_id} · {self.get_chapter_display()}'

    # ── Convenience predicates for the API layer ───────────────────────────

    @property
    def has_original(self) -> bool:
        return bool(self.original_ai.strip())

    @property
    def has_candidate(self) -> bool:
        return bool(self.candidate_regen.strip())

    @property
    def has_active(self) -> bool:
        return bool(self.user_edited.strip())
