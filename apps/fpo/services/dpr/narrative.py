"""
DPR §Narrative — AI-generated chapter text with KB grounding.

Per KAU RCD B.5 (2026-09-02):
    Narratives never auto-overwrite the user's active version. Generation
    always writes to `candidate_regen`; the user explicitly chooses Accept
    (candidate → active), Keep-existing (discard candidate), or Merge
    (user-supplied text becomes active).

Per KAU RCD A.2:
    Every generation grounds itself in DPRKnowledgeEntry rows selected by
    the retrieval layer. The chosen entry IDs are recorded in
    `DPRAIContent.candidate_regen_kb_ids` so the PDF footer can cite them.

Design:
    `generate_chapter(project, chapter, requested_by)` is the public entry
    point. It:
      1. Checks AIServiceConfig — feature enabled + budget available
      2. Retrieves KB entries via knowledge_retrieval for this chapter
      3. Assembles a coherent narrative — chapter title + AI-generated body
         (via `llm_gateway.call_llm`) + KB citation footer
      4. Writes to `candidate_regen` (never `user_edited`)
      5. Logs to AIUsageLog with the provider + model actually used
      6. Returns the fresh DPRAIContent row

Provider selection is decoupled — `llm_gateway.call_llm(config, prompt)`
reads `AIServiceConfig.provider` and dispatches to Anthropic / OpenAI /
Google / mock. Switching vendor is an admin config change, not a code
deploy. See `llm_gateway.py` for the per-provider wire-up snippets.

Author: Athul Gopan (Kefi Tech Solutions)
"""
from __future__ import annotations

from decimal import Decimal
from typing import List

from django.utils import timezone

from apps.database.models import (
    AIServiceConfig,
    AIUsageLog,
    DPRAIContent,
    DPRProject,
)
from apps.database.models.dpr.ai_content import (
    CHAPTER_LABELS,
    CHAPTER_UPSTREAM_SECTIONS,
)

from .knowledge_retrieval import (
    format_for_prompt,
    get_context_for_project,
    get_context_ids,
)
from .llm_gateway import LLMError, LLMResponse, call_llm


class NarrativeError(Exception):
    """Raised when generation cannot proceed (service disabled, cap hit, etc.)."""


def _get_service_config() -> AIServiceConfig:
    """Return the DPR_NARRATIVES service config, creating a default if absent.

    Keeps the API usable on a fresh DB — admin can then configure via
    /admin/ai-services/.
    """
    cfg, _ = AIServiceConfig.objects.get_or_create(
        service=AIServiceConfig.Service.DPR_NARRATIVES,
        defaults={'is_enabled': True, 'monthly_cap_inr': 0},
    )
    return cfg


def _chapter_to_sections(chapter: str) -> List[str]:
    """Which DPR section keys feed this chapter — used by KB retrieval."""
    return CHAPTER_UPSTREAM_SECTIONS.get(chapter, [])


def ensure_row(project: DPRProject, chapter: str) -> DPRAIContent:
    """Return the DPRAIContent row for (project, chapter), creating if absent.

    Callers that only need to read state should use this rather than raw
    `.get()` so a fresh project starts with placeholder rows the FE can list.
    """
    row, _ = DPRAIContent.objects.get_or_create(
        project=project,
        chapter=chapter,
        defaults={'active_version': DPRAIContent.ActiveVersion.USER_EDITED},
    )
    return row


# ─────────────────────────────────────────────────────────────────────────────
# Generation
# ─────────────────────────────────────────────────────────────────────────────

def generate_chapter(
    project: DPRProject,
    chapter: str,
    requested_by=None,
) -> DPRAIContent:
    """Generate a fresh narrative candidate for one chapter.

    Writes to `candidate_regen` — the user must explicitly accept via the
    /accept/ endpoint for it to become live.
    """
    if chapter not in dict(DPRAIContent.Chapter.choices):
        raise NarrativeError(f'Unknown chapter: {chapter}')

    cfg = _get_service_config()
    if not cfg.is_enabled:
        raise NarrativeError(
            'DPR narrative generation is currently disabled. Contact the KAU '
            'administrator to re-enable.'
        )

    # KB retrieval — for each upstream section, gather relevant KB entries.
    # De-dupe by id so the same entry cited by two sections isn't packed twice.
    seen_ids: set[int] = set()
    kb_entries = []
    for section_key in _chapter_to_sections(chapter):
        entries = get_context_for_project(project, section_key=section_key)
        for e in entries:
            if e.id in seen_ids:
                continue
            seen_ids.add(e.id)
            kb_entries.append(e)
    # Also fetch section-less (universal) entries so exec-summary style
    # chapters still get statutory / SOP context.
    for e in get_context_for_project(project, section_key=None):
        if e.id in seen_ids:
            continue
        seen_ids.add(e.id)
        kb_entries.append(e)

    # Generate via the provider-agnostic gateway. `call_llm` dispatches to
    # Anthropic / OpenAI / Google / mock based on `cfg.provider`, so
    # switching vendors is admin config only.
    prompt = build_prompt(project, chapter, kb_entries)
    try:
        response: LLMResponse = call_llm(cfg, prompt)
    except LLMError as e:
        # Log the failure so it appears in the admin usage table, then bubble
        # up as NarrativeError so the API layer returns 503.
        AIUsageLog.objects.create(
            service=AIUsageLog.Service.DPR_NARRATIVES,
            fpo=project.fpo,
            user=requested_by,
            provider=cfg.provider,
            model_used=cfg.model_name or 'unknown',
            input_tokens=0, output_tokens=0, total_tokens=0,
            cost_usd=Decimal('0'), cost_inr=Decimal('0'),
            success=False,
            error_message=str(e)[:500],
            reference_id=str(project.id),
        )
        raise NarrativeError(f'LLM provider failure: {e}') from e

    # Wrap the raw LLM output with the chapter title + KB citation footer.
    # Presentation lives here rather than in the gateway so switching provider
    # doesn't reshape the narrative structure.
    text = _assemble_chapter_text(chapter, response.text, kb_entries)

    # Convert USD → INR using the configured rate, then record + apply the
    # spend against the monthly cap (auto-disables if breached).
    cost_inr = response.cost_usd * cfg.usd_to_inr_rate
    AIUsageLog.objects.create(
        service=AIUsageLog.Service.DPR_NARRATIVES,
        fpo=project.fpo,
        user=requested_by,
        provider=response.provider,
        model_used=response.model,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        total_tokens=response.input_tokens + response.output_tokens,
        cost_usd=response.cost_usd,
        cost_inr=cost_inr,
        success=True,
        reference_id=str(project.id),
    )
    # Update running budget totals — no-op for mock (cost=0) but keeps the
    # cap enforced for real providers.
    if response.cost_usd > 0:
        cfg.record_usage(
            cost_inr=float(cost_inr),
            tokens=response.input_tokens + response.output_tokens,
        )

    # Write candidate — never touch original_ai or user_edited here.
    row = ensure_row(project, chapter)
    row.candidate_regen = text
    row.candidate_regen_kb_ids = get_context_ids(kb_entries)
    row.candidate_generated_at = timezone.now()

    # First-ever generation for this chapter: also seed original_ai +
    # user_edited so the user has an active version to compare against.
    if not row.has_original:
        row.original_ai = text
        row.original_ai_kb_ids = get_context_ids(kb_entries)
        row.user_edited = text
        row.active_kb_ids = get_context_ids(kb_entries)
        row.generated_at = timezone.now()
        # On first generation there's nothing to compare to, so promote
        # candidate straight to active — no diff needed. The FE handles this
        # gracefully: candidate == active means no diff banner.
        row.candidate_regen = ''
        row.candidate_regen_kb_ids = []
        row.candidate_generated_at = None
        row.is_stale = False
        row.stale_reason = ''

    row.updated_by = requested_by
    row.save()
    return row


# ─────────────────────────────────────────────────────────────────────────────
# Chapter assembly — wraps raw LLM output with title + KB citation footer
# ─────────────────────────────────────────────────────────────────────────────

def _assemble_chapter_text(
    chapter: str,
    body: str,
    kb_entries: list,
) -> str:
    """Wrap raw LLM body text in the standard chapter shape.

        <chapter title>
        <LLM body>
        Grounded in:
          - [KB #<id>] <title>
          ...

    Kept separate from the LLM call so the same shape works for every
    provider (Claude / Gemini / GPT / mock). Providers that already emit
    their own title get it de-duped naturally by the diff view — the label
    is a short prefix.
    """
    label = CHAPTER_LABELS.get(chapter, chapter)
    if kb_entries:
        grounded = 'Grounded in:\n' + '\n'.join(
            f'  - [KB #{e.id}] {e.title}'
            for e in kb_entries[:6]  # cap to keep output tight
        )
    else:
        grounded = (
            'Grounded in: (no matching knowledge base entries — narrative '
            'uses general knowledge only).'
        )
    return f'{label}\n\n{body.strip()}\n\n{grounded}'


def build_prompt(
    project: DPRProject,
    chapter: str,
    kb_entries: list,
) -> str:
    """Assemble the prompt that will be sent to Claude when live.

    Kept as a public helper so the FE / test tools can preview exactly what
    Claude would see, without triggering an actual call.
    """
    label = CHAPTER_LABELS.get(chapter, chapter)
    upstream = ', '.join(_chapter_to_sections(chapter)) or 'general'
    commodity = (
        project.primary_commodity.get_name('en')
        if project.primary_commodity_id else 'unspecified'
    )
    kb_block = format_for_prompt(kb_entries)

    return (
        f'You are drafting the "{label}" chapter of a Detailed Project Report '
        f'for a Kerala FPO.\n\n'
        f'Project: {project.title or "(untitled)"}\n'
        f'Primary commodity: {commodity}\n'
        f'FPO: {project.fpo.name if project.fpo_id else "?"}\n'
        f'Upstream data sections: {upstream}\n\n'
        f'<knowledge_base>\n{kb_block}\n</knowledge_base>\n\n'
        f'Write a professional, 2-3 paragraph narrative for this chapter. '
        f'Cite the knowledge base entries by their #ID inline where relevant. '
        f'Do not fabricate figures — leave placeholders when a specific number '
        f'is needed and the data section does not provide it.'
    )
