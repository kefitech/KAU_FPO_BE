"""
DPR AI Content — FPO-facing endpoints for narrative regen + accept/keep/merge.

Per KAU RCD B.5 (2026-09-02):
    Regeneration writes to a CANDIDATE slot. The user then picks:
      - Accept  → candidate becomes the active version
      - Keep    → candidate is discarded; existing active stays
      - Merge   → user pastes their reconciled text; becomes active

All three actions are audited via AuditLog(DPR_AI_CONTENT_CHANGE) with the
old / new hash + KB citation ids so KAU can trace which version was chosen
for any PDF.

Endpoints (mounted under /api/fpo/dpr/projects/<uuid>/):
    GET    /ai-content/                        → list all 11 chapter rows
    GET    /ai-content/<chapter>/              → single chapter detail
    PATCH  /ai-content/<chapter>/              → in-place edit user_edited slot
    POST   /ai-content/<chapter>/generate/     → produce candidate
    POST   /ai-content/<chapter>/accept/       → candidate → active
    POST   /ai-content/<chapter>/keep/         → discard candidate
    POST   /ai-content/<chapter>/merge/        → body: {text} → active
    GET    /ai-content/<chapter>/kb-preview/   → preview KB entries the next
                                                   generation would use
                                                   (helpful before spending
                                                    a Claude call)

Author: Athul Gopan (Kefi Tech Solutions)
"""
from __future__ import annotations

import hashlib

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.models.generic import AuditLog
from apps.core.utils.responses import StandardResponse
from apps.database.models import DPRAIContent
from apps.database.models.dpr.ai_content import (
    CHAPTER_KEYS,
    CHAPTER_LABELS,
    CHAPTER_UPSTREAM_SECTIONS,
)
from apps.fpo.services.dpr import narrative
from apps.fpo.services.dpr.knowledge_retrieval import get_context_for_project

from .projects import get_project_or_error


# ─────────────────────────────────────────────────────────────────────────────
# Serializers
# ─────────────────────────────────────────────────────────────────────────────

class AIContentSerializer(serializers.ModelSerializer):
    """Full read shape — includes all 3 version slots + KB ids + state."""

    chapter_display = serializers.CharField(source='get_chapter_display', read_only=True)
    upstream_sections = serializers.SerializerMethodField()
    has_original = serializers.BooleanField(read_only=True)
    has_candidate = serializers.BooleanField(read_only=True)
    has_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = DPRAIContent
        fields = (
            'id', 'chapter', 'chapter_display', 'upstream_sections',
            'original_ai', 'user_edited', 'candidate_regen',
            'original_ai_kb_ids', 'candidate_regen_kb_ids', 'active_kb_ids',
            'has_original', 'has_candidate', 'has_active',
            'active_version', 'is_stale', 'stale_reason',
            'generated_at', 'candidate_generated_at', 'updated_at',
        )
        read_only_fields = fields  # writes go through dedicated action endpoints

    def get_upstream_sections(self, obj):
        return CHAPTER_UPSTREAM_SECTIONS.get(obj.chapter, [])


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _short_hash(text: str) -> str:
    """8-char hash for audit-log diff markers. Blank text → empty string."""
    if not text:
        return ''
    return hashlib.sha256(text.encode()).hexdigest()[:8]


def _audit(user, project, row: DPRAIContent, op: str, extra: dict | None = None):
    """Write an AuditLog row for an AI-content decision.

    op ∈ {generate, accept, keep, merge, edit}. Includes text hashes rather
    than full bodies so the audit table stays small — investigations can
    pull the DPRAIContent row for full text.
    """
    changes = {
        'op': op,
        'project_id': str(project.id),
        'chapter': row.chapter,
        'active_hash': _short_hash(row.user_edited),
        'candidate_hash': _short_hash(row.candidate_regen),
        'active_kb_ids': row.active_kb_ids,
    }
    if extra:
        changes.update(extra)
    AuditLog.objects.create(
        user=user,
        action=AuditLog.Action.DPR_AI_CONTENT_CHANGE,
        object_repr=f'{project.id}/{row.chapter}',
        changes=changes,
    )


def _get_row(project, chapter: str) -> tuple[DPRAIContent | None, object | None]:
    """Return (row, err). row is None + err set when chapter is invalid."""
    if chapter not in dict(DPRAIContent.Chapter.choices):
        valid = ', '.join(CHAPTER_KEYS)
        return None, StandardResponse.error(
            f'Unknown chapter: {chapter}. Valid: {valid}', status_code=400,
        )
    row = narrative.ensure_row(project, chapter)
    return row, None


# ─────────────────────────────────────────────────────────────────────────────
# Views
# ─────────────────────────────────────────────────────────────────────────────

@extend_schema(tags=['FPO - DPR AI Content'])
class AIContentListView(APIView):
    """GET all 11 chapter rows for a project — ensures rows exist on first read."""

    permission_classes = [IsAuthenticated]

    def get(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        # Ensure a row exists per chapter — the FE lists all 11 up-front.
        rows = [narrative.ensure_row(project, key) for key in CHAPTER_KEYS]
        return StandardResponse.success(
            AIContentSerializer(rows, many=True).data,
            f'{len(rows)} chapter(s) retrieved',
        )


@extend_schema(tags=['FPO - DPR AI Content'])
class AIContentDetailView(APIView):
    """GET one chapter; PATCH to in-place edit `user_edited`."""

    permission_classes = [IsAuthenticated]

    def get(self, request, project_uuid, chapter):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        row, err = _get_row(project, chapter)
        if err:
            return err
        return StandardResponse.success(AIContentSerializer(row).data, 'Retrieved')

    def patch(self, request, project_uuid, chapter):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        row, err = _get_row(project, chapter)
        if err:
            return err
        text = request.data.get('user_edited')
        if text is None or not isinstance(text, str):
            return StandardResponse.error(
                {'user_edited': 'Must be a string.'}, status_code=400,
            )
        row.user_edited = text
        row.updated_by = request.user
        row.save(update_fields=['user_edited', 'updated_by', 'updated_at'])
        _audit(request.user, project, row, 'edit')
        return StandardResponse.success(AIContentSerializer(row).data, 'Updated')


@extend_schema(tags=['FPO - DPR AI Content'])
class AIContentGenerateView(APIView):
    """POST → produce a candidate narrative for this chapter."""

    permission_classes = [IsAuthenticated]

    def post(self, request, project_uuid, chapter):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        if chapter not in dict(DPRAIContent.Chapter.choices):
            return StandardResponse.error(f'Unknown chapter: {chapter}', status_code=400)
        try:
            row = narrative.generate_chapter(project, chapter, requested_by=request.user)
        except narrative.NarrativeError as e:
            return StandardResponse.error(str(e), status_code=503)
        _audit(request.user, project, row, 'generate', extra={
            'kb_ids_used': row.candidate_regen_kb_ids or row.active_kb_ids,
        })
        return StandardResponse.success(AIContentSerializer(row).data, 'Candidate generated')


@extend_schema(tags=['FPO - DPR AI Content'])
class AIContentAcceptView(APIView):
    """POST → promote candidate_regen into user_edited (active)."""

    permission_classes = [IsAuthenticated]

    def post(self, request, project_uuid, chapter):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        row, err = _get_row(project, chapter)
        if err:
            return err
        if not row.has_candidate:
            return StandardResponse.error(
                'No candidate to accept — generate first.', status_code=400,
            )
        # Snapshot the outgoing active hash for the audit row before we swap.
        old_hash = _short_hash(row.user_edited)
        row.user_edited = row.candidate_regen
        row.active_kb_ids = list(row.candidate_regen_kb_ids or [])
        row.candidate_regen = ''
        row.candidate_regen_kb_ids = []
        row.candidate_generated_at = None
        row.is_stale = False
        row.stale_reason = ''
        row.updated_by = request.user
        row.save()
        _audit(request.user, project, row, 'accept', extra={'previous_active_hash': old_hash})
        return StandardResponse.success(AIContentSerializer(row).data, 'Candidate accepted')


@extend_schema(tags=['FPO - DPR AI Content'])
class AIContentKeepView(APIView):
    """POST → discard candidate, keep existing user_edited untouched."""

    permission_classes = [IsAuthenticated]

    def post(self, request, project_uuid, chapter):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        row, err = _get_row(project, chapter)
        if err:
            return err
        if not row.has_candidate:
            return StandardResponse.error(
                'No candidate to discard.', status_code=400,
            )
        discarded_hash = _short_hash(row.candidate_regen)
        row.candidate_regen = ''
        row.candidate_regen_kb_ids = []
        row.candidate_generated_at = None
        row.updated_by = request.user
        row.save(update_fields=[
            'candidate_regen', 'candidate_regen_kb_ids', 'candidate_generated_at',
            'updated_by', 'updated_at',
        ])
        _audit(request.user, project, row, 'keep', extra={'discarded_hash': discarded_hash})
        return StandardResponse.success(AIContentSerializer(row).data, 'Candidate discarded')


@extend_schema(tags=['FPO - DPR AI Content'])
class AIContentMergeView(APIView):
    """POST body {text: str} → user-merged text becomes active, candidate cleared."""

    permission_classes = [IsAuthenticated]

    def post(self, request, project_uuid, chapter):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        row, err = _get_row(project, chapter)
        if err:
            return err
        text = request.data.get('text')
        if not text or not isinstance(text, str):
            return StandardResponse.error(
                {'text': 'Merged text is required.'}, status_code=400,
            )
        old_hash = _short_hash(row.user_edited)
        discarded_hash = _short_hash(row.candidate_regen)
        row.user_edited = text
        # Merging is a user judgement — track BOTH kb id sets as the grounding
        # since the user has visibility of both while merging.
        merged_kb_ids = list({
            *(row.active_kb_ids or []),
            *(row.candidate_regen_kb_ids or []),
        })
        row.active_kb_ids = merged_kb_ids
        row.candidate_regen = ''
        row.candidate_regen_kb_ids = []
        row.candidate_generated_at = None
        row.is_stale = False
        row.stale_reason = ''
        row.updated_by = request.user
        row.save()
        _audit(request.user, project, row, 'merge', extra={
            'previous_active_hash': old_hash,
            'discarded_candidate_hash': discarded_hash,
        })
        return StandardResponse.success(AIContentSerializer(row).data, 'Merged content saved')


@extend_schema(tags=['FPO - DPR AI Content'])
class AIContentKBPreviewView(APIView):
    """GET → preview which KB entries the next generation would use.

    Useful for the "before you spend a Claude call" preview panel and for
    admins wanting to trace grounding without paying for a regen.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, project_uuid, chapter):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        if chapter not in dict(DPRAIContent.Chapter.choices):
            return StandardResponse.error(f'Unknown chapter: {chapter}', status_code=400)
        # Same de-dupe logic as narrative.generate_chapter — keep in sync.
        seen: set[int] = set()
        preview = []
        for section_key in CHAPTER_UPSTREAM_SECTIONS.get(chapter, []):
            for e in get_context_for_project(project, section_key=section_key):
                if e.id in seen:
                    continue
                seen.add(e.id)
                preview.append({
                    'id': e.id,
                    'source_type': e.source_type,
                    'source_name': e.source_name,
                    'title': e.title,
                    'via_section': section_key,
                })
        for e in get_context_for_project(project, section_key=None):
            if e.id in seen:
                continue
            seen.add(e.id)
            preview.append({
                'id': e.id,
                'source_type': e.source_type,
                'source_name': e.source_name,
                'title': e.title,
                'via_section': None,
            })
        return StandardResponse.success({
            'chapter': chapter,
            'chapter_label': CHAPTER_LABELS.get(chapter, chapter),
            'entries': preview,
            'count': len(preview),
        }, f'{len(preview)} KB entries would be used')
