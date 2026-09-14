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
        # 5000 max_tokens supports the 400-900 word per-chapter briefs.
        # Gemini 3.6-flash uses roughly half the budget on internal reasoning
        # so effective visible output is ~2500 tokens (~1800 words).
        response: LLMResponse = call_llm(cfg, prompt, max_tokens=5000)
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
    # Chapter label removed — the PDF template renders <h2> for each chapter,
    # so echoing the label at the top of the body would duplicate it.
    # Strip common Gemini prompt-echoes seen in practice: leading title,
    # leading '###', '**' bold markdown, trailing "Grounded in:" that some
    # runs regenerate on their own inside the body.
    body = _strip_prompt_echoes(body, chapter)

    if kb_entries:
        # One-line compact citation footer — reads clean in prose PDFs.
        # Capped at 6 refs; more than that becomes visual noise.
        ids = ', '.join(f'KB #{e.id}' for e in kb_entries[:6])
        grounded = f'Sources: {ids}.'
    else:
        grounded = ''

    return f'{body.strip()}\n\n{grounded}' if grounded else body.strip()


def _strip_prompt_echoes(body: str, chapter: str) -> str:
    """Clean common LLM output artefacts before storing.

    Handles:
      * Chapter label repeated as first line (Gemini often does this)
      * Leading markdown headers (###, ##, #)
      * Standalone '**bold**' markers
      * Meta-commentary lines like 'Paragraph count:', 'Tone:', 'Final Polish:'
      * Redundant self-generated 'Grounded in:' or 'Sources:' footer
    """
    import re
    label = CHAPTER_LABELS.get(chapter, chapter).strip()
    text = body.strip()

    # Drop leading duplicate title line (case-insensitive).
    lines = text.split('\n')
    if lines and lines[0].strip().lower() == label.lower():
        lines = lines[1:]
    if lines and re.match(r'^\s*#{1,4}\s+' + re.escape(label), lines[0], re.I):
        lines = lines[1:]
    text = '\n'.join(lines).strip()

    # Strip leading markdown headers on any line.
    text = re.sub(r'^\s*#{1,4}\s+', '', text, flags=re.MULTILINE)
    # Strip bold markers but keep the enclosed text.
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)

    # Drop meta-commentary lines (some Gemini responses echo prompt structure).
    meta_pat = re.compile(
        r'^\s*(?:\*\s*)?(?:\d+\.\s*)?'
        r'(paragraph count|tone|final polish|kb citations|word count|structure|note)\s*[:\-].*$',
        re.IGNORECASE | re.MULTILINE,
    )
    text = meta_pat.sub('', text)

    # Drop trailing 'Grounded in:' block if the model added one — we render
    # our own compact citation footer just below.
    text = re.sub(r'\n\s*grounded in\s*:.*$', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'\n\s*sources\s*:.*$', '', text, flags=re.IGNORECASE | re.DOTALL)

    # Collapse 3+ blank lines to 2.
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# Per-chapter guidance — what specific sub-topics to cover + target length.
# Keeps prompts consistent and lets each chapter carry its own scope without
# ballooning the base prompt template. Length figures roughly match the
# IIFPT reference DPR (Documents/Dpr-rcd-response/Rice-based-Product-Dpr.pdf).
_CHAPTER_BRIEF = {
    'executive_summary': (
        'Cover the project rationale in one sentence, the FPO and its promoter '
        'context, proposed capacity and product mix, total project cost with '
        'means-of-finance summary, and a clear one-line viability statement '
        'backed by DSCR / IRR / payback. 400-600 words.'
    ),
    'project_background': (
        'Cover the sector context (national + Kerala production, demand trend, '
        'value-addition opportunity for the commodity), the local landscape '
        '(district-level cluster, existing processing capacity gap), why this '
        'FPO is well positioned, and how the project aligns with a specific '
        'scheme or policy from the knowledge base. 600-800 words.'
    ),
    'promoter_profile': (
        'Cover the FPO\'s legal identity + registration status, its member base '
        '(numbers, gender split if available, geographic spread), governance / '
        'board composition, past turnover or operational track record (use '
        'placeholders where not provided), and the CEO / management '
        'competency. 500-700 words.'
    ),
    'market_analysis': (
        'Cover demand drivers for the primary commodity + secondary products, '
        'target customer segments (B2B, retail, institutional), competitor '
        'landscape in the FPO\'s catchment, pricing benchmarks, planned '
        'marketing / distribution channels, and expected off-take arrangements. '
        '600-900 words.'
    ),
    'technical_feasibility': (
        'Cover the process technology chosen with reasons, raw material '
        'sourcing plan, plant + machinery selection, utility requirements '
        '(power, water, fuel), and quality control / statutory clearance '
        'considerations. Reference specific machinery items if provided. '
        '600-900 words.'
    ),
    'implementation_plan': (
        'Cover the phased implementation roadmap (land, civil, machinery, '
        'trial run, commissioning), timeline with key milestones by month, '
        'resource ramp-up plan, and risks to schedule. Reference '
        'implementation-period tranche schedule if available. 500-700 words.'
    ),
    'financial_analysis': (
        'Cover capital cost breakdown, means of finance mix and rationale '
        '(promoter + debt + subsidy), revenue projection basis, operating cost '
        'assumptions, key ratios (NPV, IRR, DSCR, BCR, payback, break-even), '
        'and sensitivity commentary. 700-900 words.'
    ),
    'risk_analysis': (
        'Cover the top production, market, financial, regulatory, technology '
        'and climate risks the project faces, with likelihood + impact + a '
        'concrete mitigation strategy for each. Group by risk category. '
        '600-800 words.'
    ),
    'swot': (
        'Cover strengths, weaknesses, opportunities and threats in four '
        'clearly-labelled paragraphs. Ground each with a specific project or '
        'sector fact rather than generic statements. 500-700 words.'
    ),
    'environmental_impact': (
        'Cover the anticipated environmental impact (effluent, emissions, '
        'waste), pollution control measures planned, statutory clearances '
        'required (PCB consent, FSSAI, local body NOC), and any climate-'
        'resilience or renewable-energy initiatives. 500-700 words.'
    ),
    'conclusion': (
        'Summarise the case for approval: viability signal from key ratios, '
        'social + economic impact on FPO members, alignment with scheme / '
        'policy objectives, and a clear recommendation. 300-500 words.'
    ),
}


def build_prompt(
    project: DPRProject,
    chapter: str,
    kb_entries: list,
) -> str:
    """Assemble the prompt sent to the LLM for one narrative chapter.

    Public helper so FE / debug tools can preview the exact prompt without
    triggering an actual generation call.

    Structure:
      * Role framing
      * Project context (title / commodity / FPO / upstream sections)
      * KB block (numbered entries for inline citation)
      * Per-chapter brief (topic coverage + target length)
      * Hard formatting rules — critical, otherwise the model echoes back
        prompt scaffolding and meta-commentary (observed with Gemini 3.6).
    """
    label = CHAPTER_LABELS.get(chapter, chapter)
    upstream = ', '.join(_chapter_to_sections(chapter)) or 'general'
    commodity = (
        project.primary_commodity.get_name('en')
        if project.primary_commodity_id else 'unspecified'
    )
    kb_block = format_for_prompt(kb_entries)
    brief = _CHAPTER_BRIEF.get(chapter, 'Write 500-700 words of professional narrative.')

    return (
        f'You are drafting the "{label}" chapter of a Detailed Project Report '
        f'for a Kerala FPO. Model the depth and tone on IIFPT / NABARD model '
        f'DPRs — dense, factual, professional.\n\n'
        f'Project: {project.title or "(untitled)"}\n'
        f'Primary commodity: {commodity}\n'
        f'FPO: {project.fpo.name if project.fpo_id else "?"}\n'
        f'Upstream data sections: {upstream}\n\n'
        f'<knowledge_base>\n{kb_block}\n</knowledge_base>\n\n'
        f'BRIEF FOR THIS CHAPTER:\n{brief}\n\n'
        f'STRICT OUTPUT RULES:\n'
        f'1. Output ONLY the finished narrative prose — nothing else.\n'
        f'2. NO markdown headers (###, ##), NO bullet lists, NO numbered lists.\n'
        f'3. NO meta-commentary like "Paragraph count:", "Tone:", '
        f'"Final Polish:" or references to this brief itself.\n'
        f'4. NO restating the chapter title as the first line.\n'
        f'5. Write in flowing paragraphs separated by a blank line.\n'
        f'6. Cite knowledge base entries inline as [KB #ID] where relevant, '
        f'and only when directly used — never as a trailing list.\n'
        f'7. Do NOT fabricate specific figures. Where a number is required '
        f'and not present in the data, write a natural placeholder in square '
        f'brackets (e.g. "[projected annual turnover]").\n'
        f'8. Start directly with the first sentence of the narrative.'
    )


# ─────────────────────────────────────────────────────────────────────────────
# Bulk generation — one call to fill all 11 chapters
# ─────────────────────────────────────────────────────────────────────────────

def generate_all_narratives(
    project: DPRProject,
    requested_by=None,
    skip_existing: bool = True,
) -> dict:
    """Generate every AI narrative chapter for `project` in one pass.

    Iterates `CHAPTER_KEYS` and calls `generate_chapter()` for each. When
    `skip_existing=True` (default), chapters that already have `user_edited`
    content are left alone — safe to re-run without burning tokens or
    overwriting user edits. Set to False to force regeneration (goes to
    `candidate_regen` for chapters that already have content).

    Returns a summary dict:
        {
          'generated': ['executive_summary', ...],
          'skipped':   ['financial_analysis', ...],
          'failed':    [('risk_analysis', 'reason'), ...],
        }

    Never raises — a single chapter failure is logged and the loop continues.
    Callers (PDF generator, admin bulk button) get partial success instead
    of one bad chapter blocking a whole DPR.
    """
    from apps.database.models.dpr.ai_content import CHAPTER_KEYS

    generated: list[str] = []
    skipped: list[str] = []
    failed: list[tuple[str, str]] = []

    for chapter in CHAPTER_KEYS:
        # Skip when a live chapter already exists — first-time generation
        # auto-promotes to user_edited, subsequent runs would land in
        # candidate_regen which needs manual accept. Cheaper + safer to
        # leave already-generated chapters alone by default.
        if skip_existing:
            existing = DPRAIContent.objects.filter(
                project=project, chapter=chapter,
            ).first()
            if existing and existing.user_edited:
                skipped.append(chapter)
                continue
        try:
            generate_chapter(project, chapter, requested_by=requested_by)
            generated.append(chapter)
        except Exception as e:  # noqa: BLE001 — chapter failure never blocks the loop
            failed.append((chapter, str(e)[:200]))

    return {'generated': generated, 'skipped': skipped, 'failed': failed}
