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


def _fmt_qty(value, unit: str = '') -> str:
    """Render a quantity with Indian comma grouping + an explicit unit.

    DPR-10 (UAT): Gemini was mis-reading raw floats such as `105000.000` as
    `1,050,000` (10x inflation) in a handful of chapters. Writing the value
    as `105,000 kg` with explicit grouping + unit removes the ambiguity.
    """
    if value is None:
        return ''
    try:
        d = Decimal(str(value))
    except (TypeError, ValueError, ArithmeticError):
        return f'{value} {unit}'.strip()
    # Round to integer when the fraction is .00; otherwise keep two dp.
    if d == d.to_integral_value():
        d = d.quantize(Decimal('1'))
        int_part, dec_part = str(d), ''
    else:
        d = d.quantize(Decimal('0.01'))
        int_part, _, dec_part = str(d).partition('.')
    # Indian grouping on int_part
    negative = int_part.startswith('-')
    if negative:
        int_part = int_part[1:]
    if len(int_part) > 3:
        head, tail = int_part[:-3], int_part[-3:]
        pieces = []
        while len(head) > 2:
            pieces.insert(0, head[-2:])
            head = head[:-2]
        if head:
            pieces.insert(0, head)
        int_part = ','.join(pieces) + ',' + tail
    sign = '-' if negative else ''
    body = f'{sign}{int_part}' + (f'.{dec_part}' if dec_part else '')
    return f'{body} {unit}'.strip()


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

    # DPR-06 (UAT) — Debt:Equity now aligned with the Balance Sheet. The
    # BS treats promoter contribution + share capital + internal accruals
    # as EQUITY and government grant/subsidy/CSR/NABARD as CAPITAL
    # RESERVE (quasi-equity). The earlier narrative convention of
    # loan / promoter_only inflated the ratio (e.g. 2.50:1 narrative vs
    # 1.00:1 balance sheet) because it ignored the subsidy reserve. One
    # consistent definition everywhere now:
    #   Debt  = long-term borrowings (bank term loan + VC)
    #   Equity = promoter equity + capital reserve (subsidy counts)
    term_debt = (
        (mof.by_field.get('mof_bank_term_loan') or Decimal('0'))
        + (mof.by_field.get('mof_venture_capital') or Decimal('0'))
    )
    promoter_eq = (
        (mof.by_field.get('mof_promoters_contribution') or Decimal('0'))
        + (mof.by_field.get('mof_share_capital') or Decimal('0'))
        + (mof.by_field.get('mof_internal_accruals') or Decimal('0'))
    )
    capital_reserve = (
        (mof.by_field.get('mof_government_grant') or Decimal('0'))
        + (mof.by_field.get('mof_government_subsidy') or Decimal('0'))
        + (mof.by_field.get('mof_csr_support') or Decimal('0'))
        + (mof.by_field.get('mof_nabard_assistance') or Decimal('0'))
        + (mof.by_field.get('mof_other_financial_assistance') or Decimal('0'))
    )
    total_equity_for_de = promoter_eq + capital_reserve
    if total_equity_for_de > 0:
        de_ratio = (term_debt / total_equity_for_de).quantize(Decimal('0.01'))
        de_display = f'{de_ratio} : 1'
    else:
        de_display = 'Not available'

    # Subsidy — the actual MoF fields are `mof_government_grant` + `mof_government_subsidy`
    # (Finance model). The earlier `mof_subsidy_grant` key was a typo and always
    # returned None, which is why DPR-01 (UAT bug) reported "subsidy details …
    # Not available" in every narrative even when the balance sheet showed ₹7.5L.
    subsidy_grant_amount = mof.by_field.get('mof_government_grant') or Decimal('0')
    subsidy_direct_amount = mof.by_field.get('mof_government_subsidy') or Decimal('0')
    subsidy_total = subsidy_grant_amount + subsidy_direct_amount
    # DPR-10 (UAT): when NO subsidy is proposed, emit an explicit state so the
    # LLM stops writing "subsidy or grant assistance ... currently listed as
    # not available" (observed on similar-01, contrasting-02, contrasting-03).
    subsidy_display = (
        _fmt_inr(subsidy_total)
        if subsidy_total > 0 else
        'No subsidy proposed in this project'
    )
    subsidy_proposed = subsidy_total > 0

    # Subsidy scheme metadata (name / agency / status) from the Finance section
    # so promoter / financial chapters can quote the actual scheme instead of
    # saying "subsidy details … Not available". Only surface the metadata when
    # a subsidy amount is actually proposed — otherwise the LLM reads three
    # 'Not available' lines and manufactures sentences about missing details
    # (DPR-10 UAT).
    finance_section = getattr(project, 'section_finance', None)
    subsidy_scheme = (
        (getattr(finance_section, 'subsidy_scheme_name', '') or '').strip()
        if finance_section else ''
    ) or 'Not disclosed by the FPO'
    subsidy_agency = (
        (getattr(finance_section, 'subsidy_implementing_agency', '') or '').strip()
        if finance_section else ''
    ) or 'Not disclosed by the FPO'
    subsidy_status = (
        (getattr(finance_section, 'subsidy_application_status', '') or '').strip()
        if finance_section else ''
    ) or 'Not disclosed by the FPO'

    commodity = (
        project.primary_commodity.get_name('en')
        if project.primary_commodity_id else 'Not provided by the FPO'
    )
    fpo_name = project.fpo.name if project.fpo_id else 'Not provided by the FPO'

    # KAU 2026-09-19 §Promoter Profile — surface these fields to the LLM
    # so the promoter_profile chapter stops emitting [Name of the CEO] etc.
    # DPR-10 (UAT): use the explicit "Not provided by the FPO" state in
    # place of the generic "Not available" so the LLM has one vocabulary
    # for missing promoter data (prompt rule 13 bans "not available").
    _NOT_PROVIDED = 'Not provided by the FPO'
    ceo_name = getattr(project, 'ceo_name', '') or _NOT_PROVIDED
    ceo_qual = getattr(project, 'ceo_qualification', '') or _NOT_PROVIDED
    ceo_exp  = getattr(project, 'ceo_experience_years', None)
    ceo_exp_display = f'{ceo_exp} years' if ceo_exp is not None else _NOT_PROVIDED
    area_acres = getattr(project, 'total_area_acreage', None)
    area_display = f'{area_acres} acres' if area_acres is not None else _NOT_PROVIDED
    women_pct = getattr(project, 'women_shareholding_pct', None)
    women_display = f'{women_pct}%' if women_pct is not None else _NOT_PROVIDED
    landholding = (getattr(project, 'landholding_summary', '') or '').strip() or _NOT_PROVIDED
    board_freq_raw = getattr(project, 'board_meeting_frequency', '') or ''
    board_freq_display = (
        dict((k, v) for k, v in [
            ('monthly', 'Monthly'), ('quarterly', 'Quarterly'),
            ('half_yearly', 'Half-yearly'), ('annually', 'Annually'),
        ]).get(board_freq_raw, board_freq_raw)
        or _NOT_PROVIDED
    )
    # FPO governance / membership snapshot — pulled from FPO row so the
    # narrative can quote member counts + director composition verbatim.
    fpo = project.fpo if project.fpo_id else None
    total_members = getattr(fpo, 'total_members', None) if fpo else None
    total_members_display = f'{total_members} members' if total_members else _NOT_PROVIDED
    women_members = getattr(fpo, 'female_members', None) if fpo else None
    women_members_display = f'{women_members} women members' if women_members else _NOT_PROVIDED
    total_dirs = getattr(fpo, 'total_directors', None) if fpo else None
    women_dirs = getattr(fpo, 'women_directors', None) if fpo else None
    board_display = (
        f'{total_dirs} directors ({women_dirs} women)'
        if total_dirs and women_dirs is not None else
        (f'{total_dirs} directors' if total_dirs else _NOT_PROVIDED)
    )

    # PSC — variable-length list, one line per member so the LLM sees the
    # full committee without having to parse JSON.
    psc = getattr(project, 'psc_members', None) or []
    if psc:
        psc_lines = [f'  - {m.get("name", "?")} — {m.get("role", "?")} ({m.get("affiliation", "?")})' for m in psc]
        psc_block = 'Project Steering Committee:\n' + '\n'.join(psc_lines)
    else:
        psc_block = 'Project Steering Committee:  Not constituted / Not provided by the FPO'

    # DPR-10 (UAT): Promoter Profile chapter was always writing "past
    # turnover / track record not available" because the FACTS block
    # never surfaced the baseline operating data. Pull from three places:
    #   1. FPO.annual_turnover  (declared headline turnover)
    #   2. DPRSectionBaseline   (existing production, capacity, employees,
    #                            certifications, current turnover)
    #   3. Finance section      (projected revenue is in P&L rows, so
    #                            implicit — not duplicated here)
    fpo_annual_turnover = (
        getattr(fpo, 'annual_turnover', None) if fpo else None
    )
    fpo_annual_turnover_display = (
        _fmt_inr(fpo_annual_turnover)
        if fpo_annual_turnover else _NOT_PROVIDED
    )

    baseline = getattr(project, 'section_baseline', None)
    baseline_turnover = getattr(baseline, 'current_annual_turnover', None) if baseline else None
    baseline_turnover_display = (
        _fmt_inr(baseline_turnover) if baseline_turnover else _NOT_PROVIDED
    )
    def _baseline_text(attr: str) -> str:
        if not baseline:
            return _NOT_PROVIDED
        raw = (getattr(baseline, attr, '') or '').strip()
        if not raw:
            return _NOT_PROVIDED
        return (raw[:217] + '...') if len(raw) > 220 else raw

    baseline_products   = _baseline_text('existing_products')
    baseline_capacity   = _baseline_text('existing_installed_capacity')
    baseline_production = _baseline_text('current_annual_production')
    baseline_certs      = _baseline_text('existing_certifications')
    baseline_market     = _baseline_text('existing_market_coverage')
    baseline_prev_exp   = _baseline_text('previous_experience')
    baseline_challenges = _baseline_text('major_challenges')

    baseline_employees = getattr(baseline, 'num_employees', None) if baseline else None
    baseline_employees_display = (
        f'{baseline_employees} employees' if baseline_employees else _NOT_PROVIDED
    )
    baseline_util = getattr(baseline, 'current_capacity_utilization_pct', None) if baseline else None
    baseline_util_display = (
        f'{baseline_util}%' if baseline_util is not None else _NOT_PROVIDED
    )

    lines = [
        '=== PROJECT FACTS (use these values verbatim; do not estimate) ===',
        f'Project title:              {project.title or "Not provided by the FPO"}',
        f'FPO / promoter:             {fpo_name}',
        f'Primary commodity:          {commodity}',
        '',
        '--- Promoter / institutional identity ---',
        f'CEO name:                   {ceo_name}',
        f'CEO qualification:          {ceo_qual}',
        f'CEO experience:             {ceo_exp_display}',
        f'Total member farmers:       {total_members_display}',
        f'Women members:              {women_members_display}',
        f'Board of Directors:         {board_display}',
        f'Board meeting frequency:    {board_freq_display}',
        f'Women shareholding:         {women_display}',
        f'Total area covered:         {area_display}',
        f'Landholding pattern:        {landholding}',
        psc_block,
        '',
        # DPR-10 (UAT): Promoter Profile chapter was always writing "past
        # turnover / track record not available" — this block fixes that.
        # The promoter_profile chapter should quote these fields verbatim
        # instead of saying track-record information is missing.
        '--- FPO track record (existing operations prior to this project) ---',
        f'Declared annual turnover (FPO master):  {fpo_annual_turnover_display}',
        f'Current annual turnover (baseline):     {baseline_turnover_display}',
        f'Current annual production:              {baseline_production}',
        f'Existing installed capacity:            {baseline_capacity}',
        f'Capacity utilisation (current):         {baseline_util_display}',
        f'Existing products / services:           {baseline_products}',
        f'Existing certifications held:           {baseline_certs}',
        f'Existing market coverage:               {baseline_market}',
        f'Employees on roll (current):            {baseline_employees_display}',
        f'Previous experience / track record:     {baseline_prev_exp}',
        f'Major existing operational challenges:  {baseline_challenges}',
        '',
        '--- Project cost + finance ---',
        f'Total project cost:         {_fmt_inr(cost.total)}',
        f'Total means of finance:     {_fmt_inr(mof.total)}',
    ]

    # DPR-10 (UAT): Emit EVERY non-zero funding source — the previous version
    # only emitted 4 lines (promoter / term loan / WC loan / subsidy) and
    # left out share capital, internal accruals, venture capital, CSR,
    # NABARD, other sources. That meant the AI narrative often listed
    # funding totals that didn't match the project cost (similar-01 showed
    # ₹2.25 Cr of sources against a ₹2.50 Cr total; contrasting-02 showed
    # ₹78 L against ₹90 L — ₹12 L member share capital was missing).
    _MOF_LABELS = [
        ('mof_promoters_contribution',     'Promoter contribution'),
        ('mof_share_capital',              'Member share capital'),
        ('mof_internal_accruals',          'Internal accruals'),
        ('mof_bank_term_loan',             'Bank / term loan'),
        ('mof_working_capital_loan',       'Working capital loan'),
        ('mof_government_grant',           'Government grant'),
        ('mof_government_subsidy',         'Government subsidy'),
        ('mof_nabard_assistance',          'NABARD assistance'),
        ('mof_csr_support',                'CSR support'),
        ('mof_venture_capital',            'Venture capital'),
        ('mof_other_financial_assistance', 'Other financial assistance'),
        ('mof_other_sources',              'Other sources'),
    ]
    mof_total_dec = mof.total or Decimal('0')
    listed_total = Decimal('0')
    nonzero_source_count = 0
    for key, label in _MOF_LABELS:
        v = mof.by_field.get(key) or Decimal('0')
        if v <= 0:
            continue
        listed_total += v
        nonzero_source_count += 1
        if mof_total_dec > 0:
            pct = (v * Decimal('100') / mof_total_dec).quantize(Decimal('0.1'))
            lines.append(f'  - {label}: {_fmt_inr(v)}  ({pct}% of total means of finance)')
        else:
            lines.append(f'  - {label}: {_fmt_inr(v)}')
    if nonzero_source_count == 0:
        lines.append('  - (no funding sources entered yet; means-of-finance total is '
                     'zero so the LLM MUST NOT quote a funding mix)')
    # Self-check line so the LLM can confirm sources sum to the total before
    # writing a funding paragraph. If this reads "mismatch", the FPO's
    # entered figures don't balance and the AI should flag that gap.
    lines.append(
        f'Sum of funding sources shown above:  {_fmt_inr(listed_total)}  '
        f'(this MUST equal the Total means of finance line; '
        f'{"MATCH" if listed_total == mof_total_dec else "mismatch — flag in prose"})'
    )
    # Aggregate subsidy summary line — rule 14 anchors on this phrase, so
    # keep it stable even when the per-source breakdown above is empty.
    lines.append(f'Government subsidy/grant (aggregate):  {subsidy_display}')
    if subsidy_proposed:
        lines.extend([
            f'  Subsidy scheme name:        {subsidy_scheme}',
            f'  Implementing agency:        {subsidy_agency}',
            f'  Application status:         {subsidy_status}',
        ])

    # DPR-10 (UAT): Explicit state for self-funded projects so the narrative
    # stops writing "the project shows an average DSCR of Not available"
    # (observed on contrasting-03 KAU-FPO-TVM-2026-0002). When there is no
    # term loan the DSCR / interest-coverage ratios do not apply.
    has_term_loan = term_debt > 0
    _dscr_na = (
        'N/A — self-funded project (no term loan to service)'
        if not has_term_loan else 'Not available'
    )

    lines.extend([
        f'Debt : Equity ratio:        {de_display}  (balance-sheet-aligned: '
        f'term debt ÷ (promoter equity + capital reserve); subsidy counts '
        f'as quasi-equity)',
        f'Has term loan:              {"Yes" if has_term_loan else "No — this is a self-funded / grant-only project; DSCR / debt-coverage ratios do not apply"}',
        '',
        f'Y1 revenue:                 {_fmt_inr(y1.revenue) if (y1 and y1.revenue is not None) else "Not available (projection not yet computed)"}',
        f'Y1 operating cost:          {_fmt_inr(y1.operating_cost) if (y1 and y1.operating_cost is not None) else "Not available (projection not yet computed)"}',
        f'Y1 EBITDA:                  {_fmt_inr(y1.ebitda) if (y1 and y1.ebitda is not None) else "Not available (projection not yet computed)"}',
        f'Y1 PAT:                     {_fmt_inr(y1.pat) if (y1 and y1.pat is not None) else "Not available (projection not yet computed)"}',
        '',
        f'IRR:                        {_fmt_pct(ratios.irr_pct) if (ratios and ratios.irr_pct is not None) else "Not available (projection not yet computed)"}',
        f'NPV (@ discount rate):      {_fmt_inr(ratios.npv) if (ratios and ratios.npv is not None) else "Not available (projection not yet computed)"}',
        f'Discount rate used:         {_fmt_pct(ratios.discount_rate_pct) if (ratios and ratios.discount_rate_pct is not None) else "Not available (projection not yet computed)"}',
        f'Average DSCR:               {_fmt_ratio(ratios.dscr_avg) if (ratios and ratios.dscr_avg is not None) else _dscr_na}',
        f'Minimum DSCR:               {_fmt_ratio(ratios.dscr_min) if (ratios and ratios.dscr_min is not None) else _dscr_na}',
        f'Payback period (years):     {_fmt_ratio(ratios.payback_period_years) if (ratios and ratios.payback_period_years is not None) else "Not available (projection not yet computed)"}',
        f'Break-even year:            {ratios.break_even_year if ratios and ratios.break_even_year else "Not available (projection not yet computed)"}',
        '',
        '--- Operating break-even (Y1 basis) ---',
        f'Break-even sales:           {_fmt_inr(ratios.break_even_sales_inr) if (ratios and ratios.break_even_sales_inr is not None) else "Not available (projection not yet computed)"}',
        f'Break-even capacity util.:  {_fmt_pct(ratios.break_even_capacity_utilisation_pct) if (ratios and ratios.break_even_capacity_utilisation_pct is not None) else "Not available (projection not yet computed)"} of Y1 sales',
        f'Contribution margin:        {_fmt_pct(ratios.break_even_contribution_margin_pct) if (ratios and ratios.break_even_contribution_margin_pct is not None) else "Not available (projection not yet computed)"}',
    ])

    # DPR-07 (UAT) — surface the actual products planned so the technical /
    # financial narratives describe the right process (e.g. "cold-pressed
    # virgin coconut oil" rather than making up a copra crude-oil story).
    products_section = getattr(project, 'section_products', None)
    product_rows = (
        list(products_section.items.order_by('order'))
        if products_section else []
    )
    lines.append('')
    lines.append('--- Products planned (verbatim product list) ---')
    if product_rows:
        for p in product_rows:
            ptype = str(p.product_type) if p.product_type_id else 'unspecified type'
            va = ' (value-added)' if p.is_value_added else ''
            qty = p.annual_quantity
            unit = getattr(p.unit_of_measurement, 'code', '') if p.unit_of_measurement_id else ''
            price = _fmt_inr(p.selling_price_per_unit) if p.selling_price_per_unit is not None else 'price n/a'
            # DPR-10 (UAT): format quantity with Indian commas + explicit unit
            # so Gemini can't read `105000.000` as `1,050,000`.
            qty_line = _fmt_qty(qty, unit) if qty is not None else 'quantity n/a'
            lines.append(f'  - {p.name} [{ptype}]{va}: {qty_line}/yr at {price}')
            if p.description:
                desc = p.description.strip().replace('\n', ' ')
                if len(desc) > 160:
                    desc = desc[:157] + '...'
                lines.append(f'    purpose/description: {desc}')
    else:
        lines.append('  (no products entered — do NOT invent product details)')

    # BUG-13 (KAU §6) — surface the FPO-entered raw-material annual
    # requirements verbatim so the Technical / Market chapters cannot
    # recompute them from output ÷ recovery %. similar-03 narrated
    # "approximately 3,780 tonnes" of paddy when the input was 4,070 t;
    # same shape in similar-01 v1.
    raw_material_section = getattr(project, 'section_raw_material', None)
    raw_material_rows = (
        list(raw_material_section.materials.order_by('order'))
        if raw_material_section else []
    )
    lines.append('')
    lines.append('--- Raw materials (verbatim annual requirements — quote these, NEVER recompute) ---')
    if raw_material_rows:
        for rm in raw_material_rows[:15]:
            variety = (rm.variety_grade or '').strip()
            name_bit = f'{rm.name}' + (f' ({variety})' if variety else '')
            qty = rm.estimated_annual_requirement
            unit = getattr(rm.unit_of_purchase, 'code', '') if rm.unit_of_purchase_id else ''
            qty_display = _fmt_qty(qty, unit) if qty is not None else 'quantity n/a'
            price = (
                _fmt_inr(rm.approx_purchase_price)
                if rm.approx_purchase_price is not None else 'price n/a'
            )
            lines.append(
                f'  - {name_bit}: {qty_display}/yr @ {price}/{unit or "unit"}'
            )
    else:
        lines.append('  (no raw materials entered — Technical chapter must '
                     'describe the process generically; do NOT invent input quantities)')

    # DPR-07 (UAT) — surface machinery by name + purpose so the technical
    # chapter cannot describe equipment the FPO did not enter.
    machinery_section = getattr(project, 'section_machinery', None)
    machinery_rows = (
        list(machinery_section.items.order_by('order'))
        if machinery_section else []
    )
    lines.append('')
    lines.append('--- Key machinery (verbatim list — purpose = what the equipment does) ---')
    if machinery_rows:
        for m in machinery_rows[:15]:  # cap at 15 to keep prompt bounded
            purpose = (m.purpose or '').strip() or 'purpose not specified'
            # DPR-10 (UAT): emit rated capacity with Indian commas + unit so
            # Gemini doesn't mis-read raw floats.
            cap = (m.operating_capacity or '').strip() or (
                _fmt_qty(m.rated_capacity, getattr(m.capacity_unit, 'code', ''))
                if m.rated_capacity is not None and m.capacity_unit_id else ''
            )
            cap_display = f', capacity {cap}' if cap else ''
            principle = (m.operating_principle or '').strip()
            lines.append(f'  - {m.name}: {purpose}{cap_display}')
            if principle:
                principle = principle.replace('\n', ' ')
                if len(principle) > 160:
                    principle = principle[:157] + '...'
                lines.append(f'    operating principle: {principle}')
    else:
        lines.append('  (no machinery entered — do NOT invent machinery types)')

    # DPR-08 (UAT) — explicit utility / waste / renewable list so the
    # environmental and technical chapters cannot hallucinate ETP / ZLD /
    # rooftop solar / diesel genset etc. that aren't in the project cost or
    # utility entries. The Utilities section is spread across four reverse
    # relations: fuels (power/diesel/LPG), process_utilities (water/steam/
    # compressed air), wastes (effluent/solid/air), renewable_initiatives
    # (rooftop solar / biogas / rainwater harvesting).
    utilities_section = getattr(project, 'section_utilities', None)
    utility_lines: list[str] = []
    if utilities_section:
        def _label_fuel(row):
            name = str(getattr(row, 'fuel', '') or row.fuel_other or 'fuel')
            use = (row.purpose or '').strip()
            cons = (row.annual_consumption or row.daily_consumption or '').strip()
            parts = [name]
            if use:
                parts.append(f'for {use}')
            if cons:
                parts.append(f'~{cons}')
            return ', '.join(parts)[:160]

        def _label_process_util(row):
            name = str(getattr(row, 'utility_type', '') or 'process utility')
            use = (row.purpose or '').strip()
            cap = (row.capacity or '').strip()
            src = (row.source or '').strip()
            parts = [name]
            if use:
                parts.append(f'for {use}')
            if cap:
                parts.append(f'capacity {cap}')
            if src:
                parts.append(f'source: {src}')
            return ', '.join(parts)[:160]

        def _label_waste(row):
            name = str(getattr(row, 'waste', '') or row.waste_other or 'waste stream')
            disposal = (row.disposal_method or '').strip()
            parts = [name]
            if disposal:
                parts.append(f'disposal: {disposal}')
            return ', '.join(parts)[:160]

        def _label_renewable(row):
            name = str(getattr(row, 'initiative', '') or row.initiative_other or 'initiative')
            cap = (row.capacity or '').strip()
            parts = [name]
            if cap:
                parts.append(f'capacity {cap}')
            return ', '.join(parts)[:160]

        for rel_name, header, labeller in [
            ('fuels', 'Fuel / power sources', _label_fuel),
            ('process_utilities', 'Process utilities', _label_process_util),
            ('wastes', 'Waste streams declared', _label_waste),
            ('renewable_initiatives', 'Renewable / sustainability initiatives', _label_renewable),
        ]:
            qs = getattr(utilities_section, rel_name, None)
            try:
                rows = list(qs.all()) if qs is not None else []
            except Exception:  # noqa: BLE001
                rows = []
            if rows:
                utility_lines.append(f'  {header}:')
                for row in rows[:8]:
                    utility_lines.append(f'    - {labeller(row)}')
    lines.append('')
    lines.append('--- Utilities / infrastructure actually entered + budgeted ---')
    if utility_lines:
        lines.extend(utility_lines)
    else:
        lines.append(
            '  (no utility / waste / renewable entries recorded — treat ETP, '
            'STP, ZLD, rooftop solar, diesel genset, rainwater harvesting, '
            'air pollution control as NOT IN SCOPE unless they appear above '
            'or in a project cost line)'
        )

    # DPR-04 (UAT polish) — surface the project's actual risks + the
    # FPO's own mitigation strategies so the Risk Analysis chapter can
    # quote them verbatim instead of paraphrasing / inventing. Only
    # entered risks appear here; scored vs draft is noted so the LLM
    # knows which rows have probability+impact.
    risk_section = getattr(project, 'section_risk', None)
    risk_rows = list(risk_section.items.all()) if risk_section else []
    lines.append('')
    lines.append('--- Risks + FPO-authored mitigations (verbatim) ---')
    if risk_rows:
        for r in risk_rows[:20]:
            code = (r.risk_code or r.risk_code_other or 'unspecified').strip()
            cat = (r.risk_category or 'unspecified').strip()
            desc = (r.risk_description or '').strip()
            if len(desc) > 200:
                desc = desc[:197] + '...'
            prob = (r.probability or '').strip() or '—'
            imp = (r.impact or '').strip() or '—'
            scored = ' (scored)' if prob != '—' and imp != '—' else ' (draft)'
            lines.append(f'  - [{cat}/{code}]{scored} prob={prob}, impact={imp}')
            if desc:
                lines.append(f'    description: {desc}')
            mitig = (r.mitigation_strategy or '').strip()
            if mitig:
                m = mitig.replace('\n', ' ')
                if len(m) > 220:
                    m = m[:217] + '...'
                lines.append(f'    mitigation (verbatim): {m}')
            existing = (r.existing_measures or '').strip()
            if existing:
                e = existing.replace('\n', ' ')
                if len(e) > 160:
                    e = e[:157] + '...'
                lines.append(f'    existing measures: {e}')
    else:
        lines.append('  (no risks entered — Risk Analysis chapter should discuss '
                     'typical sector risks generically and recommend the FPO '
                     'populate the §2.3.22 Risk Register before submission)')

    # BUG-05 (KAU §6) — surface the OVERALL project risk class + the
    # per-category classes computed by the calc engine, so Exec Summary and
    # Conclusion state the classification instead of silently describing the
    # project as "strong" while Project at a Glance shows "High". The
    # classification rule is: any High category → overall High; else any
    # Moderate → overall Moderate; else Low. (See RiskAssessment docstring
    # in calculation.py for the full semantics incl. not_assessed.)
    _OVERALL_RISK_DISPLAY = {
        'low':          'Low (acceptable for financing without special conditions)',
        'moderate':     'Moderate (financiable with standard risk management clauses)',
        'high':         'High (bank will likely attach additional conditions and may require tighter covenants)',
        'not_assessed': 'Not assessed (risks entered but probability + impact missing — the FPO must score each risk before submission)',
    }
    ra = getattr(result, 'risk_assessment', None)
    lines.append('')
    lines.append('--- Overall project risk classification (calc engine output) ---')
    if ra is not None:
        overall_display = _OVERALL_RISK_DISPLAY.get(ra.overall_class, ra.overall_class)
        lines.append(f'Overall project risk class:  {ra.overall_class.upper()}  —  {overall_display}')
        lines.append(f'Risk register coverage:      {ra.total_risks_scored} of {ra.total_risks_added} risks scored')
        if ra.categories:
            lines.append('Per-category classes (worst-case per category):')
            for cat in ra.categories:
                lines.append(f'  - {cat.category_label}:  {cat.category_class.upper()}')
    else:
        lines.append('Overall project risk class:  not yet computed')

    # BUG-08 (KAU §6) — surface the FPO's statutory compliance list with
    # each item's current status, so chapters can neither claim an
    # "upgraded FSSAI licence" when the FPO has not applied for one, nor
    # treat a Not Applicable item as planned. Each row quotes the
    # registration name (or custom label), the status (`available`,
    # `applied`, `under_review`, `approved`, `rejected`, `proposed_to_obtain`,
    # `not_applicable`), the issuing authority if known, and the expected
    # approval date if applied/under_review.
    compliance_section = getattr(project, 'section_compliance', None)
    compliance_rows = (
        list(compliance_section.items.select_related('registration').order_by('order'))
        if compliance_section else []
    )
    _COMPLIANCE_STATUS_DISPLAY = {
        'available':          'Available (FPO already holds this)',
        'approved':           'Approved (certificate issued)',
        'applied':            'Applied (not yet granted — treat as proposed, not held)',
        'under_review':       'Under review (not yet granted — treat as proposed)',
        'proposed_to_obtain': 'Proposed to obtain (FPO plans to apply)',
        'rejected':           'Rejected',
        'not_applicable':     'Not applicable to this project',
        '':                   'Status not disclosed by the FPO',
    }
    lines.append('')
    lines.append('--- Statutory compliance list (verbatim — quote the FACTS status, never upgrade it) ---')
    if compliance_rows:
        for c in compliance_rows[:25]:
            if c.registration_id and c.registration:
                name = str(c.registration)
            else:
                name = (c.custom_name or '').strip() or 'Unnamed compliance item'
            status_display = _COMPLIANCE_STATUS_DISPLAY.get(c.status, c.status or 'Status not disclosed')
            authority = (c.issuing_authority or '').strip()
            auth_bit = f', issuing authority: {authority}' if authority else ''
            exp_bit = (
                f', expected approval: {c.expected_date_of_approval}'
                if c.expected_date_of_approval else ''
            )
            lines.append(f'  - {name}: {status_display}{auth_bit}{exp_bit}')
    else:
        lines.append('  (no statutory items entered — Promoter / Implementation / '
                     'Environmental chapters MUST NOT claim the FPO holds, has '
                     'applied for, or will "upgrade/renew" any licence)')

    # KAU 2026-09-19 P2.1 + DPR-10 (UAT): surface the rates the calc engine
    # ACTUALLY used — project overrides win over platform defaults, and the
    # provenance is now explicit per row ("project-entered: 6.00% (platform
    # default is 10.50%)" vs "platform default: 12.00% (not overridden)").
    # This fixes similar-01 narrating "fallback 10.50%" for a project that
    # had entered its own 6%.
    from .provenance import collect_system_assumptions
    lines.append('')
    lines.append('--- Rates actually used by the calc engine (project overrides win) ---')
    for a in collect_system_assumptions(project):
        if a.overridden:
            lines.append(
                f'{a.label}:  {a.value}%  '
                f'(project-entered — overrides platform default of {a.platform_default}%)'
            )
        else:
            lines.append(
                f'{a.label}:  {a.value}%  (platform default — not overridden by this project)'
            )

    lines.append('=== END FACTS ===')
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


def scrub_placeholders(text: str, chapter: Optional[str] = None) -> tuple[str, list[dict]]:
    """Post-generation cleanup: replace `[X ...]`, `[Name of ...]`, etc. with
    "Not available" and return per-token hit records.

    Args:
        text:    LLM response to clean.
        chapter: chapter key. Lenient chapters (Tech Feasibility, Env Impact)
                 skip the aggressive scrub entirely — those are ALLOWED to
                 emit `[TO BE FILLED: ...]` per KAU 2026-09-26 feedback and
                 draw on AI's general knowledge.

    Returns:
        (cleaned_text, hits) — where hits is a list of
        {"raw": <matched substring>, "count": <int>} entries. Aggregation is
        by exact raw match so a chapter that emits `[Name of the CEO]` five
        times reports one hit with count=5, not five hits.

    NOTE: `[TO BE FILLED: ...]` markers are ALWAYS preserved verbatim — they
    are the sanctioned way for the AI to hand a gap to a human editor.
    """
    if chapter in _LENIENT_CHAPTERS:
        # Lenient chapters: skip the aggressive scrub entirely. `[TO BE FILLED: ...]`
        # is intentional; other `[X ...]` shapes are unlikely because the lenient
        # prompt explicitly forbids them, but we don't rewrite them either — leave
        # the raw output for editor review.
        return text, []

    hits_by_raw: dict[str, int] = {}

    def _replace(m: re.Match) -> str:
        raw = m.group(0)
        # Always preserve `[TO BE FILLED: ...]` — sanctioned editor marker.
        if _TO_BE_FILLED_RE.fullmatch(raw):
            return raw
        hits_by_raw[raw] = hits_by_raw.get(raw, 0) + 1
        return 'Not available'

    cleaned = _PLACEHOLDER_RE.sub(_replace, text)
    hits = [{'raw': raw, 'count': n} for raw, n in hits_by_raw.items()]
    return cleaned, hits


# KAU 2026-09-26 finalisation feedback: for two chapters the strict grounding
# was making the narrative sound mechanical and short. KAU asked us to restore
# the older expansive style for these, allow AI's general/global knowledge to
# supplement the KB, and permit `[TO BE FILLED: ...]` markers where an
# FPO-specific detail is needed. Editors know they must fill those in before
# submission. All other chapters keep the strict 2026-09-19 grounding.
_LENIENT_CHAPTERS = frozenset({'technical_feasibility', 'environmental_impact'})

# Placeholder marker the LLM is allowed to emit on lenient chapters. Matches
# exactly `[TO BE FILLED: <anything>]` (no other bracketed forms). The PDF /
# DOCX renderers should preserve this verbatim so editors can find + fill it.
_TO_BE_FILLED_RE = re.compile(r'\[TO BE FILLED:[^\]]+\]', re.IGNORECASE)


# Prompt block reused across STRICT chapters (default) — inverts the old rule
# #7 (which actively encouraged placeholders). Kept out of `build_prompt` so
# it's easy to audit at a glance. Renumbered rules match the new sequence in
# build_prompt.
_HARD_RULES = (
    'STRICT OUTPUT RULES (violations will fail post-processing):\n'
    '1. Output ONLY the finished narrative prose — nothing else.\n'
    '2. NO markdown headers (###, ##), NO bullet lists, NO numbered lists, '
    'NO markdown italics (*word* / _word_) — a bank reviewer sees asterisks '
    'as raw characters.\n'
    '3. NO meta-commentary like "Paragraph count:", "Tone:", '
    '"Final Polish:" or references to this brief itself.\n'
    '4. NO restating the chapter title as the first line.\n'
    '5. Write in flowing paragraphs separated by a blank line.\n'
    '6. DO NOT cite the knowledge base inline. Never write "[KB #ID]", '
    '"[KB#4]", "(KB 10)", "Sources: KB #...", "Grounded in:" or any '
    'similar in-prose or trailing-footer markers. BUG-27 (KAU §6): the '
    'PDF no longer renders a per-chapter Sources footer because the IDs '
    'were repeated across every chapter and read as noise to the KAU '
    'reviewer. Provenance is stored on DPRAIContent and visible to admin '
    'in the AI Content Health panel — never emit KB IDs in prose.\n'
    '7. GROUNDING: Every number in your output MUST come from the PROJECT '
    'FACTS block above. Do not invent, estimate, approximate, or infer '
    'numeric values. Do not present generic industry statistics as '
    'project facts.\n'
    '8. NO PLACEHOLDER TOKENS. Never write [X ...], [Rs. X ...], [Name of '
    '...], [CIN Number], [projected ...], [insert ...], [TODO ...], '
    '[TO BE FILLED: ...], [system_default], or any similar bracketed '
    'placeholder / tag. If a required fact is not in the FACTS block or '
    'the knowledge base, write "Not available" or "Not provided" in '
    'flowing prose — never a bracketed placeholder or metadata tag.\n'
    '9. Do not claim the FPO has certifications, buyers, awards, land, '
    'staff, turnover, machinery, products, infrastructure (ETP, STP, '
    'ZLD, rooftop solar, diesel genset, rainwater harvesting, air '
    'pollution controls, cold chain), or utility backups that are not '
    'present in the FACTS block "Products planned", "Key machinery", '
    '"Utilities / infrastructure" sections, or the knowledge base. If '
    'the utilities list says "no utility items entered", treat those '
    'systems as NOT IN SCOPE — do not describe them as planned.\n'
    '9a. NEVER INFER HISTORY OR ACTIVITIES FROM THE FPO NAME. BUG-03 '
    '(KAU §6): a FPO called "Arecanut (Areca Nut) Farming Producer '
    'Company" that aggregates only black pepper DOES NOT have a '
    '"historical focus on arecanut and raw spice trade" — the name is '
    'a legacy label, not an activity. The ONLY sources for the FPO\'s '
    'history, past commodities, past activities, or track record are '
    '(a) the "FPO track record" block in the FACTS section (declared '
    'turnover, baseline turnover, existing products, existing market '
    'coverage, previous experience) and (b) the "Primary commodity" + '
    '"Products planned" entries. Do NOT read sector / commodity / '
    'activity cues from the FPO name, email domain, or project title '
    'under any circumstance.\n'
    '9b. QUOTE RAW-MATERIAL QUANTITIES VERBATIM. BUG-13 (KAU §6): the '
    '"Raw materials" FACTS block lists the FPO\'s declared annual '
    'requirement per raw material with its unit. Technical, Market and '
    'Environmental chapters MUST quote these numbers verbatim and MUST '
    'NOT recompute input quantities from output × recovery %, process '
    'yield, or any other derivation. If the FACTS block says "4,070 t '
    'paddy / yr", write "4,070 tonnes of paddy per year" — never '
    '"approximately 3,780 t" because 3,780 × 92% recovery ≈ 3,478 t '
    'rice. The AI\'s role is to describe the process, not to redo '
    'the arithmetic.\n'
    '9d. OVERALL PROJECT RISK — MUST APPEAR IN EXEC SUMMARY AND CONCLUSION. '
    'BUG-05 (KAU §6): the FACTS block\'s "Overall project risk '
    'classification" section carries the calc engine\'s overall class '
    '(LOW / MODERATE / HIGH / NOT_ASSESSED). The Executive Summary MUST '
    'state the overall class once in one sentence (e.g. "The project '
    'carries an overall MODERATE risk rating, driven primarily by [the '
    'highest-rated per-category class]"). The Conclusion MUST do the '
    'same and MUST NOT describe the project as "strong", "attractive", '
    '"compelling" or any similarly positive term if the overall class is '
    'HIGH — a bank reviewer will see those adjectives as inconsistent '
    'with the risk rating they already read on the first page. If the '
    'overall class is NOT_ASSESSED, state that risks are entered but not '
    'yet scored and the FPO must complete the scoring before submission.\n'
    '9c. STATUTORY STATUS — QUOTE, NEVER UPGRADE. BUG-08 (KAU §6): the '
    '"Statutory compliance list" FACTS block gives the real-time status '
    'of every statutory item ("Available", "Applied", "Under review", '
    '"Proposed to obtain", "Approved", "Rejected", "Not applicable", '
    '"Status not disclosed"). The Implementation Plan, Promoter Profile, '
    'and Compliance chapters MUST quote these statuses verbatim and '
    'MUST NOT (a) claim an "upgrade" or "renewal" of a licence unless '
    'status reads "Available" or "Approved"; (b) imply the FPO holds a '
    'licence whose status is "Proposed to obtain"; (c) describe a "Not '
    'applicable" item as planned. If the compliance list is empty, DO '
    'NOT invent any registration — write that statutory approvals need '
    'to be mapped out before implementation.\n'
    '10. PROVENANCE OF ASSUMPTIONS. The "Rates actually used by the calc '
    'engine" section lists every rate the engine applied, with each row '
    'tagged as either "project-entered — overrides platform default of X%" '
    'or "platform default — not overridden by this project". QUOTE THE '
    'ACTUAL VALUE on each row, and reflect its provenance in prose. '
    'Examples: "the FPO\'s own loan interest rate of 6%" (for project-entered '
    'rows) or "at the platform\'s default 12% discount rate" (for '
    'platform-default rows). NEVER call a rate a "fallback" or a "default" '
    'if the row is tagged project-entered — doing so misrepresents what '
    'the project actually assumed.\n'
    '11. NEUTRAL BANK-APPRAISAL LANGUAGE. This is a professional DPR for '
    'bank / scheme appraisal — write in formal, analytical, evidence-based '
    'prose. Do NOT use promotional adjectives: "highly bankable", '
    '"state-of-the-art", "uniquely positioned", "transformative", '
    '"compelling", "exceptional", "unmatched", "extraordinary", "robust", '
    '"impressive", "outstanding", "lucrative". Do NOT recommend loan '
    'sanction, subsidy approval, or project approval — the final appraisal '
    'decision rests with the concerned bank or implementing agency. '
    'Present indicators (DSCR, IRR, NPV, payback) as calculated values '
    'and let the reviewer draw conclusions.\n'
    '12. HEADLINE-RATIO BUDGET per chapter (STRICT — post-processor will '
    'strip excess):\n'
    '    - Financial Analysis: full set of eight indicators (revenue, '
    'EBITDA, PAT, IRR, NPV, DSCR, payback, break-even).\n'
    '    - Executive Summary: EXACTLY three ratios in one viability '
    'sentence (DSCR + IRR + payback). No others.\n'
    '    - Conclusion: at most TWO ratios in one passing phrase.\n'
    '    - Market Analysis, SWOT, Implementation Plan, Environmental '
    'Impact: at most ONE ratio, only when directly relevant.\n'
    '    - Project Background, Promoter Profile, Technical Feasibility, '
    'Risk Analysis: ZERO ratios. These chapters MUST NOT mention IRR, '
    'NPV, DSCR, payback, break-even, Y1 revenue, EBITDA, or PAT at all '
    '— write about the chapter\'s own topic (sector context, promoter '
    'identity, process, risks) without quoting financial indicators.\n'
    '    A post-process scrubber will delete any ratio sentence beyond '
    'these caps before the narrative ships to the PDF, so staying inside '
    'the budget is the only way to control which content survives.\n'
    '13. "Not available" HANDLING. NEVER write the literal phrase "not '
    'available" in your output. The FACTS block uses explicit state '
    'phrases that you must echo verbatim where relevant: '
    '"No subsidy proposed in this project", "N/A — self-funded project '
    '(no term loan to service)", "Not disclosed by the FPO", "Not provided '
    'by the FPO", or "Not available (projection not yet computed)". If a '
    'field reads one of these, use the exact phrase in prose or do not '
    'mention the field at all. Treat "Not available" in the FACTS block '
    'ONLY as "projection not yet computed" — never paraphrase it as a '
    'policy or scheme being unavailable.\n'
    '14. SUBSIDY. If the FACTS block "Government subsidy/grant" line '
    'shows a value, you MUST reference it in the Financial Analysis / '
    'Means-of-Finance narrative — including the scheme name and '
    'implementing agency if the FACTS block provides them. If the line '
    'reads "No subsidy proposed in this project", state exactly that '
    '("No government subsidy or grant is proposed in this project") — '
    'never write that subsidy details are "not available" or "pending", '
    'and never speculate about which schemes the FPO could apply for.\n'
    '15. SELF-FUNDED / NO-DEBT PROJECTS. If the FACTS block "Has term loan" '
    'line reads "No", DO NOT quote DSCR, minimum DSCR, debt-service '
    'coverage, interest-coverage, or payback-of-loan ratios anywhere in '
    'the narrative — the FACTS block will have already marked those as '
    'N/A. The Executive Summary\'s mandatory three-ratio sentence '
    '(DSCR + IRR + payback) is REPLACED by a two-ratio sentence '
    '(IRR + payback) for a self-funded project. Describe the financing '
    'as fully internal / promoter / grant-funded without debt service.\n'
    '16. CURRENCY SYMBOL. Always write monetary amounts with the `₹` '
    'symbol — "₹ 7,50,000" or "₹ 1.25 crore". Never write "Rs.", "Rs ", '
    '"INR", or "Rupees". Every number already appears in the FACTS block '
    'and PDF tables with `₹`; the prose MUST match so a bank reviewer '
    'sees consistent currency formatting across the document.\n'
    '17. Start directly with the first sentence of the narrative.'
)


# Prompt block used for LENIENT chapters (Tech Feasibility, Environmental
# Impact). Per KAU 2026-09-26: these sections benefit from the AI drawing on
# general industry knowledge and open-source technical/environmental standards.
# The AI may write expansively and use `[TO BE FILLED: <hint>]` placeholders
# where an FPO-specific detail is needed — editors will complete them before
# submission. Neutral bank-appraisal tone still enforced.
_LENIENT_RULES = (
    'OUTPUT RULES (lenient — this chapter allows general knowledge):\n'
    '1. Output ONLY the finished narrative prose — nothing else.\n'
    '2. NO markdown headers (###, ##), NO bullet lists, NO numbered lists, '
    'NO markdown italics (*word* / _word_). The PDF renders asterisks as '
    'raw characters.\n'
    '3. NO meta-commentary like "Paragraph count:", "Tone:", "Final Polish:" '
    'or references to this brief itself.\n'
    '4. NO restating the chapter title as the first line.\n'
    '5. Write in flowing paragraphs separated by a blank line.\n'
    '6. DO NOT cite the knowledge base inline. Never write "[KB #ID]", '
    '"Sources: KB #...", "Grounded in:" or any similar footer. BUG-27 '
    '(KAU §6): no per-chapter Sources footer is rendered any more; '
    'provenance is tracked in the admin AI Content Health panel.\n'
    '7. KNOWLEDGE SOURCE: You may combine the PROJECT FACTS block, the '
    'knowledge base entries, AND your own general knowledge of industry '
    'best practice / open-source technical standards / environmental norms. '
    'Prefer the FACTS block for anything project-specific, but you are '
    'encouraged to elaborate with domain expertise the FACTS block does '
    'not cover.\n'
    '8. PLACEHOLDERS ALLOWED SPARINGLY. Where a GENUINELY FPO-specific '
    'detail is required (vendor name, consent date, officer name) but is '
    'not in the FACTS block or knowledge base, you MAY write '
    '`[TO BE FILLED: <short hint>]` — but the PDF stripper removes these '
    'before the document is handed to a reviewer, so the surrounding '
    'sentence must still make sense if the bracket were deleted. Prefer to '
    'rewrite the sentence in the passive voice ("the FPO will apply for '
    'KSPCB consent") over inserting a placeholder. Never use the older '
    '`[X ...]`, `[Name of ...]`, `[insert ...]` forms. Keep placeholders '
    'under 3 per chapter.\n'
    '9. Do not fabricate FPO-specific claims (certifications, buyers, '
    'awards, land, staff, turnover figures, machinery, products, '
    'infrastructure like ETP / STP / ZLD / rooftop solar / diesel genset '
    '/ rainwater harvesting). If a system is NOT in the FACTS block\'s '
    '"Utilities / infrastructure" section, describe it as a '
    'recommended/typical approach the FPO should consider — never state '
    'it as planned or budgeted. Use the FACTS block or leave the detail '
    'generic.\n'
    '9a. NEVER INFER HISTORY OR ACTIVITIES FROM THE FPO NAME. The ONLY '
    'sources for the FPO\'s history, past commodities, or track record '
    'are the FACTS block\'s "FPO track record" section and its "Primary '
    'commodity" line. Do not read activity cues from the FPO name, '
    'email, or project title (BUG-03, KAU §6).\n'
    '10. NO METADATA TAGS. Never emit `[system_default]`, `[KB #n]`, '
    '`(system)` or similar metadata markers in the output.\n'
    '11. PROVENANCE OF ASSUMPTIONS. The "Rates actually used by the calc '
    'engine" section tags each rate as either project-entered (overrides '
    'platform default) or platform default. Quote the actual value and '
    'reflect its provenance in prose — e.g. "the FPO\'s own 6% loan rate" '
    'or "at the platform\'s default 12% discount rate". Do not call a '
    'rate a "fallback" when the row is tagged project-entered.\n'
    '12. NEUTRAL BANK-APPRAISAL LANGUAGE. Formal, analytical, evidence-based '
    'prose. Do NOT use promotional adjectives: "highly bankable", '
    '"state-of-the-art", "uniquely positioned", "transformative", '
    '"compelling", "exceptional", "robust", "impressive". Do NOT recommend '
    'loan sanction or project approval.\n'
    '13. STAY ON YOUR CHAPTER\'S TOPIC. The eight headline financial '
    'indicators (revenue, EBITDA, PAT, IRR, NPV, DSCR, payback, '
    'break-even) belong to Financial Analysis — this chapter may '
    'reference at MOST ONE of them when directly relevant, and must '
    'not list the full set.\n'
    '14. CURRENCY SYMBOL. Always write monetary amounts with the `₹` '
    'symbol — "₹ 7,50,000" or "₹ 1.25 crore". Never write "Rs.", "Rs ", '
    '"INR", or "Rupees".\n'
    '15. "Not available" HANDLING. NEVER write the literal phrase "not '
    'available" in your output. The FACTS block uses explicit state '
    'phrases ("No subsidy proposed in this project", "N/A — self-funded '
    'project", "Not disclosed by the FPO", "Not provided by the FPO") — '
    'echo them verbatim where relevant, or omit the sentence entirely. '
    'Do not paraphrase a missing value as "subsidy details are not '
    'available" or "turnover not available".\n'
    '16. Start directly with the first sentence of the narrative.'
)


# Expanded briefs for lenient chapters — encourage the AI to actually
# use its global knowledge on process technology / environmental standards.
_LENIENT_CHAPTER_BRIEFS = {
    'technical_feasibility': (
        'Cover, in professional consulting-report depth: (a) the process '
        'technology chosen and why it suits this commodity + Kerala context '
        '(reference the FACTS block for chosen machinery), (b) an outline of '
        'the process flow with major unit operations, (c) raw material '
        'sourcing plan with realistic seasonality + storage considerations, '
        '(d) plant and machinery selection rationale, (e) utility '
        'requirements (power load, water, fuel, cold chain) with typical '
        'industry ranges where FPO-specific numbers are not yet known, '
        '(f) quality control approach and applicable statutory clearances '
        '(FSSAI, BIS, HACCP as relevant to the commodity). Draw on '
        'general industry best practice to add depth beyond the FACTS block, '
        'and mark FPO-specific gaps with `[TO BE FILLED: <hint>]`. '
        '800-1200 words.'
    ),
    'environmental_impact': (
        'Cover, in professional consulting-report depth: (a) anticipated '
        'environmental aspects and impacts of the chosen process (effluent '
        'volume + typical BOD/COD load ranges, air emissions, solid waste '
        'streams), (b) pollution control measures — ETP / STP sizing '
        'guidance, air pollution controls, solid-waste segregation, '
        '(c) statutory clearances required (Kerala State Pollution Control '
        'Board consent-to-establish + consent-to-operate, FSSAI, local body '
        'NOC, Consent for Green/Orange/Red category as applicable), '
        '(d) climate-resilience measures (rainwater harvesting, solar, '
        'energy efficiency), (e) occupational safety and worker welfare. '
        'Use industry norms and open-source environmental standards where '
        'FPO-specific numbers are not yet known, and mark those gaps with '
        '`[TO BE FILLED: <hint>]`. 700-1000 words.'
    ),
}


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
        # DPR-10 (UAT): include chapter key in reference_id so admin usage
        # table can trace which chapter failed on which model.
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
            reference_id=f'{project.id}:{chapter}',
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
    text, scrubber_hits = scrub_placeholders(text, chapter=chapter)

    # Round-7 fallback (2026-10-05): make the Executive Summary viability
    # sentence deterministic. Gemini sometimes drops the DSCR+IRR+payback
    # line even when the brief says it's mandatory (observed in v18/v20).
    # If the chapter ships with no headline ratio mention at all, append
    # a synthesised viability sentence from calc_result so a bank
    # reviewer always sees the summary.
    text = _ensure_exec_viability_sentence(text, chapter, calc_result)

    # Convert USD → INR using the configured rate, then record + apply the
    # spend against the monthly cap (auto-disables if breached).
    # DPR-10 (UAT): include chapter key in reference_id so admin usage table
    # shows which model wrote each chapter — critical for tracing a fallback
    # that produced wrong quantities to the specific chapter + model combo.
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
        reference_id=f'{project.id}:{chapter}',
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

    Kept separate from the LLM call so the same shape works for every
    provider (Claude / Gemini / GPT / mock). Providers that already emit
    their own title get it de-duped naturally by the diff view — the label
    is a short prefix.

    BUG-27 (KAU §6): the earlier version appended 'Sources: KB #4, KB #10,
    ...' to every chapter. Every chapter cited the same bucket because
    kb_entries was computed once for the whole generation, so the IDs
    weren't real per-chapter citations — just the full retrieval set
    repeated 11 times. KAU reviewer saw it as noise. The IDs still live
    on DPRAIContent.candidate_regen_kb_ids / active_kb_ids where admin
    can inspect provenance, but we no longer render them on-page.
    """
    # Chapter label removed — the PDF template renders <h2> for each chapter,
    # so echoing the label at the top of the body would duplicate it.
    # Strip common Gemini prompt-echoes seen in practice: leading title,
    # leading '###', '**' bold markdown, trailing "Grounded in:" that some
    # runs regenerate on their own inside the body.
    body = _strip_prompt_echoes(body, chapter)
    return body.strip()


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
    # DPR-20 (UAT) — markdown italics (`*word*` / `_word_`) were rendering as
    # literal asterisks in the PDF. Strip the single-char markers while
    # preserving the enclosed word. Must not match bold `**word**` — that was
    # already handled above and consumed by the time we get here.
    text = re.sub(r'(?<![\*\w])\*(?!\*)([^\*\n]+?)\*(?!\*)', r'\1', text)
    text = re.sub(r'(?<![_\w])_(?!_)([^_\n]+?)_(?!_)', r'\1', text)
    # DPR-03 (UAT) — strip stray `[system_default]` tags that Gemini sometimes
    # echoes from the FACTS block header rather than paraphrasing in prose.
    text = re.sub(r'\s*\[system_default\]', '', text, flags=re.IGNORECASE)
    # DPR-03 (UAT) — strip inline `[KB #n]` / `[KB#n]` citations from the body.
    # BUG-27 (KAU §6): the chapter no longer renders a Sources footer either,
    # so these inline markers are purely noise.
    text = re.sub(r'\s*\[KB\s*#?\d+\]', '', text, flags=re.IGNORECASE)
    # DPR-03 (UAT) — scrub vendor / version strings the LLM occasionally
    # borrows from FACTS-block headers ("Kefitech 2026-09-19 basis") or
    # internal comments. These do not belong in a bank-facing document.
    text = re.sub(
        r'\s*(?:,\s*)?Kefi\s*Tech\s*\d{4}-\d{2}-\d{2}(?:\s*basis)?',
        '', text, flags=re.IGNORECASE,
    )
    text = re.sub(
        r'\s*(?:,\s*)?Kefitech\s*\d{4}-\d{2}-\d{2}(?:\s*basis)?',
        '', text, flags=re.IGNORECASE,
    )
    # DPR Round-2 retest (2026-10-04) — Gemini sometimes writes "Rs." or "INR"
    # instead of the ₹ symbol every table + the FACTS block uses, which reads
    # inconsistent across the document. Normalise. Order matters:
    # "Rs." first (most common), then "INR", then bare "Rs" with trailing
    # space, then "Rupees" at word boundary (don't eat 'Rupees Mandi').
    text = re.sub(r'\bRs\.\s*(?=\d)', '₹ ', text)
    text = re.sub(r'\bINR\s*(?=\d)', '₹ ', text)
    text = re.sub(r'\bRs\s+(?=\d)', '₹ ', text)
    text = re.sub(r'\bRupees\s+(?=\d)', '₹ ', text, flags=re.IGNORECASE)

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
    text = text.strip()
    # DPR Round-3 retest (2026-10-04) — prompt-only ratio caps drifted
    # between regenerations. Enforce the per-chapter headline-ratio budget
    # deterministically. Same mechanism as the Rs./₹ normaliser.
    text = _cap_ratio_sentences(text, chapter)
    return text


# Chapter → maximum number of headline-ratio KEYWORD MATCHES allowed.
# Round-5 (2026-10-05): switched from sentence-count to keyword-count
# after retest flagged "Y1 revenue of ₹X and Year 1 EBITDA of ₹Y" (one
# sentence, two keywords) slipping past a sentence-level cap of 1.
#
# Values match the tester's own "ratios counted per chapter" convention:
#   Exec Summary = 3   → one viability sentence citing DSCR + IRR + payback
#   Conclusion   = 2   → one closing phrase with up to two ratios
#   Market / SWOT /
#   Implementation /
#   Environmental = 1  → single relevant mention max
#   Background / Promoter / Technical / Risk = 0
#   Financial Analysis = None (uncapped — home chapter)
_RATIO_SENTENCE_CAP = {
    'financial_analysis':     None,
    'executive_summary':      3,
    'conclusion':             2,
    'market_analysis':        1,
    'swot':                   1,
    'implementation_plan':    1,
    'environmental_impact':   1,
    'project_background':     0,
    'promoter_profile':       0,
    'technical_feasibility':  0,
    'risk_analysis':          0,
}

# Signatures that strongly identify a headline-ratio mention. We keep
# the list focused on the eight indicators plus phrase variants Gemini
# actually produced in UAT runs so false positives are rare on prose
# like "revenue model" or "net present cost".
#
# Round-5 widening (2026-10-05): tester flagged "Year 1 revenue" and
# "Year 1 EBITDA" slipping past the capper. Earlier regex only caught
# "Y1 revenue" / "year one revenue" / "annual revenue of". Also added
# the "cash flow" / "turnover" / "sales" / "PAT" variants that follow
# the Y/Year prefix.
_RATIO_SIGNATURE_RE = __import__('re').compile(
    r'\b(?:'
    r'IRR|internal\s+rate\s+of\s+return'
    r'|NPV|net\s+present\s+value'
    r'|DSCR|debt[\s-]+service(?:\s+coverage)?(?:\s+ratio)?'
    r'|EBITDA'
    r'|PAT|profit\s+after\s+tax'
    r'|payback'
    r'|break[\s-]?even'
    # "Y1 revenue", "Y 1 revenue", "Year 1 revenue", "year one revenue",
    # "Year 1 EBITDA", "Year 1 PAT", "Year 1 profit", "Year 1 cash flow",
    # "Year 1 turnover" / "sales" — any digit 1-9.
    # Round-10 plurals (2026-10-05): "revenues", "profits", "turnovers"
    # slipped past in v30 SWOT + Environmental. The plural noun forms
    # are now accepted via a trailing `s?` on each.
    r'|(?:Y|year|Yr)\s*(?:[1-9]|one|two|three|four|five)'
    r'\s+(?:revenues?|EBITDA|PAT|profits?|cash\s+flows?|turnovers?|sales|operating\s+costs?|outputs?|productions?)'
    # Round-6 widening (2026-10-05): tester flagged "annual turnover is
    # projected at ₹X in the first operating year" slipping past.
    # Previous pattern required "annual turnover OF ₹X"; dropped the
    # "of" tether. Added "first (operating) year" / "first year of
    # operation" / "first full year" phrasings — these are all common
    # Gemini synonyms for "Year 1".
    r'|(?:annual|total)\s+(?:revenues?|turnovers?|EBITDA|sales|incomes?|outputs?|productions?|profits?)\b'
    # Round-7 (2026-10-05): widened "first operating year" patterns to
    # also catch "initial operating year" / "initial year of operation"
    # — tester flagged these slipping past in v20 SWOT. Also made the
    # separator tolerant of hyphens so "first-year break-even" / "first-
    # year revenue" variants are recognised (break-even itself was
    # already caught via the standalone break-even keyword; this adds
    # recognition when the ratio phrase lives on a hyphenated noun).
    r'|(?:first|initial)[\s-]+(?:operating|full)[\s-]+year'
    r'|(?:first|initial)[\s-]+year[\s-]+of[\s-]+(?:operation|production|sales|business)'
    # "first-year revenue", "initial-year EBITDA", "first year sales"
    r'|(?:first|initial)[\s-]+year[\s-]+(?:revenues?|EBITDA|PAT|profits?|turnovers?|sales|operating\s+costs?|outputs?)'
    r')\b',
    __import__('re').IGNORECASE,
)


def _cap_ratio_sentences(text: str, chapter: str) -> str:
    """Keep ratio mentions within the chapter's budget, strip the rest.

    Round-5 (2026-10-05) change: cap is now a count of RATIO-KEYWORD
    MATCHES (not sentences). Tester flagged that one sentence packing
    two keywords ("Y1 revenue of ₹X and Year 1 EBITDA of ₹Y") slipped
    past the sentence-level cap of 1 because it was still one sentence.
    Switched to keyword counting so Executive Summary's combined
    viability sentence (three keywords in one line) still fits its cap
    of 3, but other chapters' multi-ratio sentences get stripped
    entirely when they would exceed the budget.

    Semantics per cap value:
      None → no cap (Financial Analysis)
      0    → any ratio sentence stripped (no mentions at all)
      N>0  → up to N keyword matches may survive across the whole
             chapter. If a single sentence contains more matches than
             the remaining budget, the entire sentence is dropped —
             partial strips risked breaking prose.

    Sentence splitting is simple — on `.`, `!`, `?` followed by whitespace
    + capital letter. Good enough for DPR prose; a false merge only
    means a slightly-too-long sentence survives, which is harmless.
    """
    cap = _RATIO_SENTENCE_CAP.get(chapter)
    if cap is None:
        return text

    import re
    pieces = re.split(r'(?<=[.!?])\s+(?=[A-Z"\'(])', text)

    kept_matches = 0
    seen_ratio_sentence = False
    out: list[str] = []
    for sentence in pieces:
        matches_in_sentence = len(_RATIO_SIGNATURE_RE.findall(sentence))
        if matches_in_sentence == 0:
            out.append(sentence)
            continue
        # cap=0 chapters: strip every ratio sentence outright.
        if cap == 0:
            continue
        # Round-5 fix (2026-10-05): for cap>0 chapters, ALWAYS keep the
        # first ratio sentence even when it holds more keywords than
        # the cap allows. v14 Executive Summary showed what the alternate
        # rule costs: Gemini packed four keywords (DSCR + IRR + payback
        # + break-even) into one viability sentence, cap=3 dropped the
        # whole sentence, and the chapter shipped with no headline
        # viability line at all. A slightly-over-cap first mention
        # reads better than silence. Subsequent ratio sentences still
        # go through the strict budget check so repetition is caught.
        if not seen_ratio_sentence:
            out.append(sentence)
            kept_matches += matches_in_sentence
            seen_ratio_sentence = True
            continue
        if kept_matches + matches_in_sentence <= cap:
            out.append(sentence)
            kept_matches += matches_in_sentence
        # else: drop the whole sentence — this is the "no partial retain"
        # branch for 2nd+ ratio sentences only.

    stripped = ' '.join(s.strip() for s in out if s.strip())
    stripped = re.sub(r'\n{3,}', '\n\n', stripped)
    return stripped


# Round-11 (2026-10-05): the fallback is ONLY concerned with the three
# viability ratios (DSCR, IRR, payback). Earlier versions also counted
# NPV / debt-service / EBITDA / revenue mentions as "quantified
# viability", which falsely passed cases like "applying a 12.00% discount
# rate for net present value calculations" and "demonstrates strong debt
# service capabilities and investment recovery profiles". Tester's call
# was explicit: fire the fallback unless DSCR, IRR, or payback appears
# next to its own figure — don't count NPV / discount / tax / depreciation
# rate sentences.
_VIABILITY_QUANTIFIED_RE = __import__('re').compile(
    r'\b(?:DSCR|IRR|internal\s+rate\s+of\s+return|payback(?:\s+period)?)\b'
    r'[^.!?]{0,40}'                 # same-sentence, up to 40 chars after keyword
    r'\d',
    __import__('re').IGNORECASE,
)


def _text_has_quantified_ratio(text: str) -> bool:
    """True if `text` contains a VIABILITY ratio (DSCR / IRR / payback)
    next to its own numeric figure, in the same sentence.

    Used by `_ensure_exec_viability_sentence` to distinguish between
    (a) a real quantified viability line like "DSCR of 4.88, IRR 68%,
    payback 1.56 years" and (b) prose that only mentions a non-
    viability metric with numbers (NPV with discount rate, EBITDA
    margin, project cost, tax rate) which does not satisfy the
    "viability line" requirement.

    Scope narrowed in round-11 per tester feedback — NPV / debt-
    service / revenue / discount / tax mentions no longer count as
    viability. The chapter is viability-complete only when at least
    one of the three core metrics (DSCR, IRR, payback) is quantified
    with a nearby figure.
    """
    import re
    # Strip KB citations so "KB #4" / "KB #10" don't contribute digits.
    stripped = re.sub(r'KB\s*#\s*\d+', '', text, flags=re.IGNORECASE)
    return bool(_VIABILITY_QUANTIFIED_RE.search(stripped))


def _ensure_exec_viability_sentence(text: str, chapter: str, calc_result) -> str:
    """Append a deterministic viability sentence to Executive Summary when
    the LLM didn't emit one.

    Round-7 (2026-10-05): v18/v20 shipped Exec Summary with no DSCR /
    IRR / payback mention at all even though the brief marked it
    mandatory. The capper can only preserve what Gemini writes; this
    guard fills the gap so a bank reviewer always sees the headline
    numbers.

    Round-8 (2026-10-05): v22 shipped a figure-less viability line
    ("confirm the primary debt service and cost recovery metrics") —
    the keyword 'debt service' was present but no numeric value
    followed. Fallback was skipped, reviewer saw no actual figures.
    Fallback now requires a QUANTIFIED ratio mention — a ratio keyword
    followed within 80 chars (same sentence) by a digit — before
    treating the viability line as present.

    Fires only for `executive_summary`. The synthesised sentence is
    derived from the same calc_result the FACTS block used, so numbers
    reconcile with the Financial Analysis table + §10 Financial
    Appraisal.
    """
    if chapter != 'executive_summary' or calc_result is None:
        return text
    # Strip the trailing "Sources: KB #..." footer before checking —
    # otherwise the digit in "KB #4" counts as a quantified ratio value
    # within the 80-char window of any ratio keyword in the body and
    # the fallback mistakenly skips. See v22 regression (2026-10-05).
    import re as _re
    check_text = _re.sub(
        r'\n\s*Sources\s*:\s*KB\s*#.*$',
        '', text, flags=_re.IGNORECASE | _re.DOTALL,
    )
    if _text_has_quantified_ratio(check_text):
        return text

    ratios = getattr(calc_result, 'ratios', None)
    if ratios is None:
        return text

    irr = getattr(ratios, 'irr_pct', None)
    dscr = getattr(ratios, 'dscr_avg', None)
    payback = getattr(ratios, 'payback_period_years', None)

    bits: list[str] = []
    if dscr is not None:
        bits.append(f'a DSCR of {dscr}')
    if irr is not None:
        bits.append(f'an IRR of {irr}%')
    if payback is not None:
        bits.append(f'a payback period of {payback} years')
    if not bits:
        return text

    if len(bits) == 1:
        trio = bits[0]
    elif len(bits) == 2:
        trio = f'{bits[0]} and {bits[1]}'
    else:
        trio = f'{bits[0]}, {bits[1]}, and {bits[2]}'
    sentence = f'The project shows {trio}.'

    # Insert BEFORE the "Sources:" citation footer if one is present —
    # otherwise append at the end.
    import re
    sources_match = re.search(r'\n\n*Sources:\s*KB\s*#', text)
    if sources_match:
        pos = sources_match.start()
        return f'{text[:pos].rstrip()}\n\n{sentence}{text[pos:]}'
    return f'{text.rstrip()}\n\n{sentence}'


# Per-chapter guidance — what specific sub-topics to cover + target length.
# Keeps prompts consistent and lets each chapter carry its own scope without
# ballooning the base prompt template. Length figures roughly match the
# IIFPT reference DPR (Documents/Dpr-rcd-response/Rice-based-Product-Dpr.pdf).
_CHAPTER_BRIEF = {
    'executive_summary': (
        'Cover the project rationale in one sentence, the FPO and its promoter '
        'context, proposed capacity and product mix, total project cost with '
        'means-of-finance summary, and — MANDATORY, non-optional — one '
        'viability sentence that cites DSCR, IRR, AND payback period '
        'together. Target form: "The project shows a DSCR of {X.XX}, '
        'an IRR of {YY.YY}%, and a payback period of {Z.ZZ} years." '
        'Replace the braces with the actual values from the FACTS '
        'block. The Executive Summary is INVALID if this three-ratio '
        'viability sentence is missing; do NOT substitute Debt:Equity, '
        'NPV, break-even, or EBITDA for the viability line. BUG-05 '
        '(KAU §6) — ALSO MANDATORY: state the overall project risk '
        'class in one sentence after the viability line, quoting the '
        'exact class from the "Overall project risk classification" '
        'FACTS section (LOW / MODERATE / HIGH / NOT_ASSESSED) and '
        'naming the per-category driver when it is HIGH or MODERATE. '
        'Do not re-list revenue / EBITDA / PAT / NPV / break-even / Y1 '
        'figures elsewhere in the chapter — the Financial Analysis '
        'chapter carries those. 400-600 words.'
    ),
    'project_background': (
        'Cover the sector context (national + Kerala production, demand trend, '
        'value-addition opportunity for the commodity), the local landscape '
        '(district-level cluster, existing processing capacity gap), why this '
        'FPO is well positioned, and how the project aligns with a specific '
        'scheme or policy from the knowledge base. 600-800 words.'
    ),
    'promoter_profile': (
        "Cover the FPO's legal identity + registration status, its member base "
        '(total member farmers, women members, geographic spread), governance / '
        'board composition (total directors + women directors + meeting frequency), '
        'CEO name / qualification / experience, women shareholding %, total farming '
        'area covered, member landholding pattern, and Project Steering Committee '
        'composition (if constituted). THEN — DPR-10 UAT MANDATE — cover the '
        'FPO\'s TRACK RECORD using the "FPO track record" section of the FACTS '
        'block: declared annual turnover, baseline current turnover, current '
        'production, existing installed capacity + utilisation %, existing '
        'products / services, certifications held, market coverage, employees '
        'on roll, previous experience, and major operational challenges. '
        'Quote each of these verbatim where the FACTS block supplies a value. '
        'If a field reads "Not provided by the FPO" or "Not available (projection '
        'not yet computed)", echo the exact phrase in prose — never write '
        '"past turnover / track record is not available" or anything similar '
        'that implies the data isn\'t supplied when the FACTS block has it. '
        '500-700 words.'
    ),
    'market_analysis': (
        'Cover demand drivers for the primary commodity + secondary products, '
        'target customer segments (B2B, retail, institutional), competitor '
        'landscape in the FPO\'s catchment, pricing benchmarks (describe '
        'market price ranges / seasonality — do NOT re-quote Y1 revenue, '
        'break-even sales or any Financial Analysis figure), planned '
        'marketing / distribution channels, and expected off-take '
        'arrangements. Reference AT MOST ONE headline ratio (e.g. a passing '
        'mention of break-even if directly relevant to a market-pricing '
        'point) — never two. 600-900 words.'
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
        'and climate risks the project faces. For EACH risk in the FACTS '
        'block "Risks + FPO-authored mitigations" section, write one short '
        'paragraph that (a) summarises the risk description verbatim, '
        '(b) states the probability × impact rating when scored (or notes '
        '"not yet scored" when draft), and (c) quotes the FPO\'s own '
        'entered mitigation strategy verbatim — do NOT paraphrase, do NOT '
        'substitute your own mitigation idea. If existing measures are '
        'listed, include them too. Group by risk category. If no risks '
        'were entered, write a short generic sector-risk discussion and '
        'end by recommending the FPO populate the §2.3.22 Risk Register. '
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
        'Summarise, in neutral bank-appraisal language, the overall case '
        'for the project — how its technical feasibility, market position, '
        'financing structure, and identified risks fit together. BUG-05 '
        '(KAU §6) — MANDATORY: state the overall project risk class '
        'quoting the exact class from the "Overall project risk '
        'classification" FACTS section, and if that class is HIGH or '
        'MODERATE, name the per-category driver(s) and acknowledge the '
        'need for additional covenants / risk management clauses — do '
        'NOT describe the project as "strong", "attractive" or '
        '"compelling" when the risk class is HIGH. You may reference '
        'AT MOST two headline ratios (pick DSCR and IRR, or DSCR and '
        'payback) in a single passing phrase — never list the full '
        'ratio set and never quote revenue / EBITDA / PAT / NPV / '
        'break-even values; the Financial Analysis chapter carries all '
        'of those. Note any material assumptions from the Key Assumptions '
        'Used table + any limitations. Do NOT recommend loan sanction, '
        'subsidy approval or project approval — final appraisal is the '
        'concerned bank\'s / implementing agency\'s decision. Do NOT use '
        'promotional language ("highly bankable", "state-of-the-art", '
        '"transformative", "compelling", etc.). Present the evidence and '
        'let the reviewer conclude. 300-500 words.'
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
    # Lenient chapters get a longer, more expansive brief; others use the
    # standard tight brief. Falls back to a generic prompt for unknown keys.
    if chapter in _LENIENT_CHAPTERS:
        brief = _LENIENT_CHAPTER_BRIEFS.get(
            chapter, _CHAPTER_BRIEF.get(chapter, 'Write 500-700 words of professional narrative.')
        )
        rules = _LENIENT_RULES
    else:
        brief = _CHAPTER_BRIEF.get(chapter, 'Write 500-700 words of professional narrative.')
        rules = _HARD_RULES

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
        f'{rules}'
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

    # KAU 2026-09-19 P2.3 — after every full-DPR generation, run the
    # cross-chapter consistency check. Never raises; writes warnings to
    # DPRAIContent.consistency_warnings so the FE + admin viewer can
    # surface drift/mismatch badges without a second round-trip.
    try:
        from .consistency_check import check_project_chapters
        consistency_summary = check_project_chapters(project, result=calc_result)
    except Exception:  # noqa: BLE001 — the check is opportunistic; never block the return
        consistency_summary = {}

    return {
        'generated': generated,
        'skipped': skipped,
        'failed': failed,
        'consistency_warnings': {
            ch: [w.__dict__ for w in warns]
            for ch, warns in consistency_summary.items()
        },
    }
