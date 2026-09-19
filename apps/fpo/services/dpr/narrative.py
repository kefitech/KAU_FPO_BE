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

import re
from decimal import Decimal
from typing import List, Optional

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

from .calculation import CalculationResult, compute
from .knowledge_retrieval import (
    format_for_prompt,
    get_context_for_project,
    get_context_ids,
)
from .llm_gateway import LLMError, LLMResponse, call_llm


class NarrativeError(Exception):
    """Raised when generation cannot proceed (service disabled, cap hit, etc.)."""


# ─────────────────────────────────────────────────────────────────────────────
# KAU AI grounding (2026-09-19) — facts injection + placeholder scrubber
#
# KAU 2026-09-19 review (Documents/DPR-RESPONSE/AI.docx) said every generated
# statement must trace to (a) questionnaire input, (b) calc-engine output,
# (c) verified knowledge base, or (d) AI interpretation of the above. AI must
# not invent FPO facts and must never emit `[X ...]` placeholder tokens.
#
# Two mechanisms enforce this:
#   1. `format_calc_facts_for_prompt()` builds a labelled fact block from
#      `compute(project)` that the prompt tells the LLM to quote verbatim.
#   2. `scrub_placeholders()` catches any leftover `[X …]` tokens in the
#      response and replaces them with "Not available", flagging the chapter
#      as `needs_review=True` on DPRAIContent.
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_inr(amount: Optional[Decimal]) -> str:
    """Render a Decimal ₹ amount as `₹ 12,34,567.89` (Indian numbering).
    Returns 'Not available' for None."""
    if amount is None:
        return 'Not available'
    # Split into integer + fractional
    negative = amount < 0
    a = abs(amount).quantize(Decimal('0.01'))
    int_part, _, dec_part = str(a).partition('.')
    # Indian grouping: last 3 digits, then groups of 2.
    if len(int_part) > 3:
        head, tail = int_part[:-3], int_part[-3:]
        # groups-of-2 from the right on head
        pieces = []
        while len(head) > 2:
            pieces.insert(0, head[-2:])
            head = head[:-2]
        if head:
            pieces.insert(0, head)
        int_part = ','.join(pieces) + ',' + tail
    sign = '-' if negative else ''
    return f'₹ {sign}{int_part}.{dec_part or "00"}'


def _fmt_pct(v: Optional[Decimal]) -> str:
    return f'{v}%' if v is not None else 'Not available'


def _fmt_ratio(v: Optional[Decimal]) -> str:
    return f'{v}' if v is not None else 'Not available'


def format_calc_facts_for_prompt(project: DPRProject, result: CalculationResult) -> str:
    """Return the labelled FACTS block that the prompt injects verbatim.

    The block is the ONLY source of numbers the LLM is allowed to quote. If
    a value is None on `result` (project not far enough along), the line
    reads 'Not available' rather than being omitted — that way the LLM
    consistently has the same field names to reason about.

    Format is deliberately verbose + machine-parseable so KAU can audit the
    prompt directly. Numbers use Indian comma grouping to match the PDF.
    """
    cost = result.cost
    mof = result.mof
    ratios = result.ratios
    pl_rows = result.profit_loss.rows if result.profit_loss else []
    y1 = pl_rows[0] if pl_rows else None

    # Debt:Equity — same convention as the PDF (banking `x.xx : 1`).
    debt = mof.by_field.get('mof_bank_term_loan') or Decimal('0')
    equity = mof.by_field.get('mof_promoters_contribution') or Decimal('0')
    if equity > 0:
        de_ratio = (debt / equity).quantize(Decimal('0.01'))
        de_display = f'{de_ratio} : 1'
    else:
        de_display = 'Not available'

    commodity = (
        project.primary_commodity.get_name('en')
        if project.primary_commodity_id else 'Not available'
    )
    fpo_name = project.fpo.name if project.fpo_id else 'Not available'

    lines = [
        '=== PROJECT FACTS (use these values verbatim; do not estimate) ===',
        f'Project title:              {project.title or "Not available"}',
        f'FPO / promoter:             {fpo_name}',
        f'Primary commodity:          {commodity}',
        '',
        f'Total project cost:         {_fmt_inr(cost.total)}',
        f'Total means of finance:     {_fmt_inr(mof.total)}',
        f'  - Promoter contribution:  {_fmt_inr(mof.by_field.get("mof_promoters_contribution"))}',
        f'  - Bank / term loan:       {_fmt_inr(mof.by_field.get("mof_bank_term_loan"))}',
        f'  - Working capital loan:   {_fmt_inr(mof.by_field.get("mof_working_capital_loan"))}',
        f'  - Subsidy / grant:        {_fmt_inr(mof.by_field.get("mof_subsidy_grant"))}',
        f'Debt : Equity ratio:        {de_display}',
        '',
        f'Y1 revenue:                 {_fmt_inr(y1.revenue) if y1 else "Not available"}',
        f'Y1 operating cost:          {_fmt_inr(y1.operating_cost) if y1 else "Not available"}',
        f'Y1 EBITDA:                  {_fmt_inr(y1.ebitda) if y1 else "Not available"}',
        f'Y1 PAT:                     {_fmt_inr(y1.pat) if y1 else "Not available"}',
        '',
        f'IRR:                        {_fmt_pct(ratios.irr_pct) if ratios else "Not available"}',
        f'NPV (@ discount rate):      {_fmt_inr(ratios.npv) if ratios else "Not available"}',
        f'Discount rate used:         {_fmt_pct(ratios.discount_rate_pct) if ratios else "Not available"}',
        f'Average DSCR:               {_fmt_ratio(ratios.dscr_avg) if ratios else "Not available"}',
        f'Minimum DSCR:               {_fmt_ratio(ratios.dscr_min) if ratios else "Not available"}',
        f'Payback period (years):     {_fmt_ratio(ratios.payback_period_years) if ratios else "Not available"}',
        f'Break-even year:            {ratios.break_even_year if ratios and ratios.break_even_year else "Not available"}',
        '=== END FACTS ===',
    ]
    return '\n'.join(lines)


# Regex — catches the placeholder shapes KAU flagged in AI.docx and the ones
# our own prompt used to explicitly encourage (see the pre-2026-09-19
# build_prompt rule #7). Matches `[X MT per day]`, `[Rs. X Lakhs]`, `[Name
# of ...]`, `[insert ...]`, `[TODO ...]`, `[Placeholder ...]`, `[projected
# ...]`, `[CIN Number]`, `[XX%]`, etc. Single-line matches only — never
# swallows an actual multi-word inline citation like `[KB #12]`.
_PLACEHOLDER_RE = re.compile(
    r'\['
    r'(?!KB\s*#\d+\])'                 # negative lookahead — spare our own KB citations
    r'(?:'
    r'X+(?:\s*[A-Za-z%₹()./\-]+)*'     # [X MT per day], [XX%]
    r'|Rs\.?\s*X+.*?'                  # [Rs. X Lakhs]
    r'|₹\s*X+.*?'                      # [₹ X Lakhs]
    r'|X+\s*(?:MT|kg|Ha|ha|acre|acres|Nos?|units?|months?)\s.*?'
    r'|Name\s+of\s+[^\]]+'             # [Name of the CEO]
    r'|Insert\s+[^\]]+'                # [Insert value]
    r'|TODO[^\]]*'                     # [TODO ...]
    r'|Placeholder[^\]]*'              # [Placeholder ...]
    r'|projected\s+[^\]]+'             # [projected annual turnover]
    r'|CIN\s+Number'                   # [CIN Number]
    r'|Location(?:/[A-Za-z]+)?'        # [Location/Taluk]
    r'|number\s+of\s+[^\]]+'           # [number of active farmer members]
    r'|turnover\s+FY\s*[^\]]*'         # [turnover FY 2021-22]
    r'|\?+'                            # [???]
    r')'
    r'\]',
    re.IGNORECASE,
)


def scrub_placeholders(text: str) -> tuple[str, list[dict]]:
    """Post-generation cleanup: replace `[X ...]`, `[Name of ...]`, etc. with
    "Not available" and return per-token hit records.

    Returns:
        (cleaned_text, hits) — where hits is a list of
        {"raw": <matched substring>, "count": <int>} entries. Aggregation is
        by exact raw match so a chapter that emits `[Name of the CEO]` five
        times reports one hit with count=5, not five hits.
    """
    hits_by_raw: dict[str, int] = {}

    def _replace(m: re.Match) -> str:
        raw = m.group(0)
        hits_by_raw[raw] = hits_by_raw.get(raw, 0) + 1
        return 'Not available'

    cleaned = _PLACEHOLDER_RE.sub(_replace, text)
    hits = [{'raw': raw, 'count': n} for raw, n in hits_by_raw.items()]
    return cleaned, hits


# Prompt block reused across every chapter — inverts the old rule #7 (which
# actively encouraged placeholders). Kept out of `build_prompt` so it's easy
# to audit at a glance. Renumbered rules match the new sequence in build_prompt.
_HARD_RULES = (
    'STRICT OUTPUT RULES (violations will fail post-processing):\n'
    '1. Output ONLY the finished narrative prose — nothing else.\n'
    '2. NO markdown headers (###, ##), NO bullet lists, NO numbered lists.\n'
    '3. NO meta-commentary like "Paragraph count:", "Tone:", '
    '"Final Polish:" or references to this brief itself.\n'
    '4. NO restating the chapter title as the first line.\n'
    '5. Write in flowing paragraphs separated by a blank line.\n'
    '6. Cite knowledge base entries inline as [KB #ID] where relevant, '
    'and only when directly used — never as a trailing list.\n'
    '7. GROUNDING: Every number in your output MUST come from the PROJECT '
    'FACTS block above. Do not invent, estimate, approximate, or infer '
    'numeric values. Do not present generic industry statistics as '
    'project facts.\n'
    '8. NO PLACEHOLDER TOKENS. Never write [X ...], [Rs. X ...], [Name of '
    '...], [CIN Number], [projected ...], [insert ...], [TODO ...], or '
    'any similar bracketed placeholder. If a required fact is not in the '
    'FACTS block or the knowledge base, write "Not available" or "Not '
    'provided" in flowing prose — never a bracketed placeholder.\n'
    '9. Do not claim the FPO has certifications, buyers, awards, land, '
    'staff, or turnover that are not present in the FACTS block or the '
    'knowledge base.\n'
    '10. Start directly with the first sentence of the narrative.'
)


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
    calc_facts: Optional[str] = None,
    calc_result: Optional[CalculationResult] = None,
) -> DPRAIContent:
    """Generate a fresh narrative candidate for one chapter.

    Writes to `candidate_regen` — the user must explicitly accept via the
    /accept/ endpoint for it to become live.

    `calc_facts` / `calc_result` — optional caller-provided precomputed
    facts. `generate_all_narratives()` runs `compute()` once and passes both
    through so N chapters share one calc pass. When both are None we compute
    here so single-chapter calls still work standalone.
    """
    if chapter not in dict(DPRAIContent.Chapter.choices):
        raise NarrativeError(f'Unknown chapter: {chapter}')

    cfg = _get_service_config()
    if not cfg.is_enabled:
        raise NarrativeError(
            'DPR narrative generation is currently disabled. Contact the KAU '
            'administrator to re-enable.'
        )

    # KAU 2026-09-19 order-enforcement: narrative MUST read final validated
    # calc-engine numbers, never re-estimate them. Compute here if the caller
    # didn't pre-compute. Refuse to generate if compute() fails outright.
    if calc_facts is None:
        try:
            calc_result = compute(project)
        except Exception as e:  # noqa: BLE001
            raise NarrativeError(
                f'Cannot generate narrative — calculation engine failed: {e}'
            ) from e
        calc_facts = format_calc_facts_for_prompt(project, calc_result)

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
    prompt = build_prompt(project, chapter, kb_entries, calc_facts=calc_facts)
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

    # KAU 2026-09-19 anti-hallucination scrubber: catch any leftover `[X ...]`,
    # `[Name of the CEO]`, `[Rs. X Lakhs]` etc. placeholders the LLM emitted
    # despite the HARD RULES and replace them with "Not available". Hits are
    # recorded on DPRAIContent.placeholder_hits so admin can see WHICH
    # chapters were incomplete without diffing the text against the prompt.
    text, scrubber_hits = scrub_placeholders(text)

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

    # KAU 2026-09-19: record scrubber outcome. Zero hits → clear both fields
    # so re-generation of a previously-flagged chapter can un-flag itself.
    row.placeholder_hits = scrubber_hits
    row.needs_review = bool(scrubber_hits)

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
    calc_facts: Optional[str] = None,
) -> str:
    """Assemble the prompt sent to the LLM for one narrative chapter.

    Public helper so FE / debug tools can preview the exact prompt without
    triggering an actual generation call.

    Structure:
      * Role framing
      * Project context (title / commodity / FPO / upstream sections)
      * FACTS block (from `format_calc_facts_for_prompt`) — the only source
        the LLM is allowed to quote numbers from. Post-KAU-2026-09-19 fix.
      * KB block (numbered entries for inline citation)
      * Per-chapter brief (topic coverage + target length)
      * Hard formatting + anti-placeholder rules

    Backwards-compat: if `calc_facts` is None, we call `compute(project)`
    ourselves so debug tools + old callers still work. Callers that generate
    many chapters in one run should pass a pre-computed facts string to
    avoid re-running compute() N times.
    """
    label = CHAPTER_LABELS.get(chapter, chapter)
    upstream = ', '.join(_chapter_to_sections(chapter)) or 'general'
    commodity = (
        project.primary_commodity.get_name('en')
        if project.primary_commodity_id else 'unspecified'
    )
    kb_block = format_for_prompt(kb_entries)
    brief = _CHAPTER_BRIEF.get(chapter, 'Write 500-700 words of professional narrative.')

    if calc_facts is None:
        calc_facts = format_calc_facts_for_prompt(project, compute(project))

    return (
        f'You are drafting the "{label}" chapter of a Detailed Project Report '
        f'for a Kerala FPO. Model the depth and tone on IIFPT / NABARD model '
        f'DPRs — dense, factual, professional.\n\n'
        f'Project: {project.title or "(untitled)"}\n'
        f'Primary commodity: {commodity}\n'
        f'FPO: {project.fpo.name if project.fpo_id else "?"}\n'
        f'Upstream data sections: {upstream}\n\n'
        f'{calc_facts}\n\n'
        f'<knowledge_base>\n{kb_block}\n</knowledge_base>\n\n'
        f'BRIEF FOR THIS CHAPTER:\n{brief}\n\n'
        f'{_HARD_RULES}'
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

    # KAU 2026-09-19 order-enforcement + N-chapters-share-one-calc: run
    # compute() ONCE and pass the same facts block into every chapter. If
    # compute fails, refuse the whole run — narrative without validated
    # numbers is exactly what KAU flagged as the bug.
    try:
        calc_result = compute(project)
    except Exception as e:  # noqa: BLE001
        raise NarrativeError(
            f'Cannot generate any narrative — calculation engine failed: {e}'
        ) from e
    calc_facts = format_calc_facts_for_prompt(project, calc_result)

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
            generate_chapter(
                project,
                chapter,
                requested_by=requested_by,
                calc_facts=calc_facts,
                calc_result=calc_result,
            )
            generated.append(chapter)
        except Exception as e:  # noqa: BLE001 — chapter failure never blocks the loop
            failed.append((chapter, str(e)[:200]))

    return {'generated': generated, 'skipped': skipped, 'failed': failed}
