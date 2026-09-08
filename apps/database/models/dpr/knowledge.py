"""
DPR §Knowledge Base — sourced content that grounds AI-generated narratives.

Per KAU RCD reply A.2 (2026-09-02):
    "AI-generated content shall be grounded in authoritative sources — KAU
     Package of Practices, existing scheme inventories, Kefi Tech-compiled
     SOPs, Kerala Government statutory portals, and market intelligence
     feeds such as AGMARKNET. Every AI-generated paragraph shall be
     traceable back to the source knowledge base entries it was derived
     from."

One row = one retrievable knowledge fragment (a scheme summary, a PoP
practice note, a market price observation, etc.). The `retrieval` service
(apps/fpo/services/dpr/knowledge_retrieval.py) selects rows relevant to a
DPR project's commodity + components + business types, packs them into the
Claude API context window, and Phase 5's narrative generator records the
IDs used in `DPRAIContent.knowledge_source_ids` for full traceability.

Versioning: rows are never edited in place after use. To update, a NEW row
is created and the old row's `superseded_by` FK points to the new row. Old
rows stay queryable for audit but `is_active=False`. The retrieval layer
only ever returns active rows.

Author: Athul Gopan (Kefi Tech Solutions)
"""
from django.db import models

from apps.core.models.base import TimeStampedModel, AuditModel


class DPRKnowledgeEntry(TimeStampedModel, AuditModel):
    """One versioned, retrievable knowledge fragment from an authoritative source."""

    class SourceType(models.TextChoices):
        KAU_POP     = 'kau_pop',     'KAU Package of Practices'
        SCHEME      = 'scheme',      'Government scheme / subsidy'
        SOP         = 'sop',         'Kefi Tech SOP'
        STATUTORY   = 'statutory',   'Kerala statutory / regulatory'
        AGMARKNET   = 'agmarknet',   'AGMARKNET market prices'
        OTHER       = 'other',       'Other'

    # ── Source metadata ────────────────────────────────────────────────────

    source_type = models.CharField(
        max_length=20,
        choices=SourceType.choices,
        db_index=True,
    )
    source_name = models.CharField(
        max_length=200,
        help_text='Human-readable source identifier — e.g. "KAU PoP: Turmeric 2024" '
                  'or "PMKSY — Per Drop More Crop".',
    )
    source_url = models.URLField(
        blank=True,
        help_text='Optional canonical URL to the source document / page.',
    )
    source_version = models.CharField(
        max_length=50, blank=True,
        help_text='Version indicator from the source — e.g. "2024 edition", '
                  '"v3.2", release date. Used for audit trail when superseded.',
    )

    # ── Payload ────────────────────────────────────────────────────────────

    title = models.CharField(
        max_length=255,
        help_text='One-line summary shown in admin lists + retrieval preview.',
    )
    content = models.TextField(
        help_text='The actual retrievable text. Kept short (a few paragraphs) — '
                  'large documents should be split into multiple entries so '
                  'retrieval can pick the relevant slice.',
    )
    language = models.CharField(
        max_length=10, default='en', db_index=True,
        help_text='Language code — "en" or "ml". Retrieval matches to project '
                  'language preference; falls back to English if unavailable.',
    )

    # ── Retrieval anchors — how the retrieval layer finds this entry ──────
    # All three are optional. Blank = "applies to any". At retrieval time the
    # entry matches a project if EACH filter is either empty here OR contains
    # the project's value. This lets us mix broad (state-wide statutory) and
    # narrow (commodity-specific PoP) entries in one table.

    commodities = models.ManyToManyField(
        'core.MasterLookup', blank=True,
        related_name='knowledge_entries_by_commodity',
        help_text="Commodities this entry is relevant to (MasterLookup "
                  "category='commodity'). Blank = applies to any commodity.",
    )
    components = models.ManyToManyField(
        'database.DPRComponent', blank=True,
        related_name='knowledge_entries',
        help_text='Project components this entry is relevant to. Blank = applies '
                  'to any component.',
    )
    business_types = models.ManyToManyField(
        'database.DPRNatureOfBusiness', blank=True,
        related_name='knowledge_entries',
        help_text='Nature-of-business categories this entry is relevant to. '
                  'Blank = applies to any business type.',
    )
    section_keys = models.JSONField(
        default=list, blank=True,
        help_text='DPR section keys this entry is relevant to — e.g. '
                  '["market", "technology"]. Empty = applies to any section. '
                  'Retrieval narrows by the section currently being generated.',
    )
    tags = models.JSONField(
        default=list, blank=True,
        help_text='Free-form tags for admin search — e.g. ["organic", "kerala-only"].',
    )

    # ── Versioning ─────────────────────────────────────────────────────────

    is_active = models.BooleanField(
        default=True, db_index=True,
        help_text='Only active entries are returned by retrieval. Deactivated '
                  'entries stay for audit (old narratives may cite them).',
    )
    superseded_by = models.ForeignKey(
        'self', null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='supersedes',
        help_text='If set, this entry has been replaced by a newer version. '
                  'Marking superseded_by automatically sets is_active=False.',
    )
    ingested_at = models.DateTimeField(
        auto_now_add=True, db_index=True,
        help_text='When this entry was first added — separate from created_at '
                  'so re-ingestion of the same source can preserve original date.',
    )

    class Meta:
        db_table = 'dpr_knowledge_entry'
        verbose_name = 'DPR — Knowledge Entry'
        verbose_name_plural = 'DPR — Knowledge Entries'
        ordering = ['-ingested_at', 'id']
        indexes = [
            models.Index(fields=['source_type', 'is_active']),
            models.Index(fields=['language', 'is_active']),
        ]

    def __str__(self):
        return f'[{self.get_source_type_display()}] {self.title}'

    def save(self, *args, **kwargs):
        # Setting superseded_by → this entry is no longer the current version,
        # so remove it from active retrieval automatically. Callers only need
        # to update one field.
        if self.superseded_by_id and self.is_active:
            self.is_active = False
        super().save(*args, **kwargs)
