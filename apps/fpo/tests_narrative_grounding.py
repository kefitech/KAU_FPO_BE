"""
Test suite for the DPR AI narrative grounding pipeline (KAU 2026-09-19 fix).

Covers the four helpers added to apps.fpo.services.dpr.narrative:
    - scrub_placeholders() — regex-based placeholder cleanup
    - format_calc_facts_for_prompt() — FACTS block builder
    - build_prompt() — end-to-end prompt shape
    - generate_all_narratives() — order-enforcement when compute() fails

Uses `SimpleNamespace` project/FPO mocks + fake dataclass CalculationResult
so no Postgres/PostGIS test DB is required — tests run against pure Python
functions. Real live-Gemini coverage happens via the sample DPR regen (P1.8),
not here.

Run:
    source venv/bin/activate && \
    DJANGO_SETTINGS_MODULE=config.settings.development \
    python -m pytest apps/fpo/tests_narrative_grounding.py -v
    # or
    source venv/bin/activate && python -c "
    import django; django.setup()
    import unittest
    from apps.fpo.tests_narrative_grounding import *
    unittest.main(module='apps.fpo.tests_narrative_grounding', exit=False, verbosity=2)
    "
"""
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from apps.fpo.services.dpr import narrative
from apps.fpo.services.dpr.calculation import (
    CalculationResult,
    CostMofVariance,
    FinancialRatios,
    MeansOfFinanceBreakdown,
    ProfitLoss,
    ProfitLossRow,
    ProjectCostBreakdown,
)


# ─────────────────────────────────────────────────────────────────────────────
# scrub_placeholders — pure function
# ─────────────────────────────────────────────────────────────────────────────

class ScrubPlaceholdersTests(unittest.TestCase):
    """Every placeholder shape KAU flagged in AI.docx should be caught and
    replaced. Our own [KB #N] citations must survive intact."""

    def test_catches_bracket_x_amount_placeholders(self):
        """[X MT per day], [X%], [Rs. X Lakhs] etc. get replaced."""
        text = 'Capacity is [X MT per day] and turnover is [Rs. X Lakhs].'
        cleaned, hits = narrative.scrub_placeholders(text)
        self.assertNotIn('[X MT per day]', cleaned)
        self.assertNotIn('[Rs. X Lakhs]', cleaned)
        self.assertIn('Not available', cleaned)
        raw_matches = {h['raw'] for h in hits}
        self.assertEqual(raw_matches, {'[X MT per day]', '[Rs. X Lakhs]'})

    def test_catches_name_of_placeholders(self):
        """[Name of the CEO], [Name of Producer Company Limited] get replaced."""
        text = 'The FPO [Name of Producer Company Limited] and CEO [Name of the CEO].'
        cleaned, hits = narrative.scrub_placeholders(text)
        self.assertNotIn('[Name of', cleaned)
        self.assertEqual(cleaned.count('Not available'), 2)
        self.assertEqual(len(hits), 2)

    def test_catches_kau_review_specific_placeholders(self):
        """CIN Number / Location/Taluk / number of active farmer members /
        turnover FY 2021-22 — the exact shapes KAU flagged in AI.docx."""
        text = (
            'CIN: [CIN Number]. Location: [Location/Taluk]. '
            '[number of active farmer members] members. '
            'Turnover [turnover FY 2021-22].'
        )
        cleaned, hits = narrative.scrub_placeholders(text)
        for placeholder in (
            '[CIN Number]', '[Location/Taluk]',
            '[number of active farmer members]', '[turnover FY 2021-22]',
        ):
            self.assertNotIn(placeholder, cleaned)
        self.assertEqual(len(hits), 4)

    def test_catches_projected_and_todo(self):
        text = 'Refer [projected annual turnover] and [TODO get quotation] and [Placeholder for capacity].'
        cleaned, hits = narrative.scrub_placeholders(text)
        for placeholder in ('[projected', '[TODO', '[Placeholder'):
            self.assertNotIn(placeholder, cleaned)
        self.assertEqual(len(hits), 3)

    def test_preserves_kb_citations(self):
        """`[KB #12]` shape MUST survive — that's our own inline citation format."""
        text = 'See [KB #12] and [KB #100] for context; but replace [X ...].'
        cleaned, hits = narrative.scrub_placeholders(text)
        self.assertIn('[KB #12]', cleaned)
        self.assertIn('[KB #100]', cleaned)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]['raw'], '[X ...]')

    def test_aggregates_repeated_hits_by_count(self):
        """Five identical placeholders → 1 hit entry with count=5."""
        text = '[Name of the CEO] said [Name of the CEO] again. Also [Name of the CEO].'
        cleaned, hits = narrative.scrub_placeholders(text)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]['raw'], '[Name of the CEO]')
        self.assertEqual(hits[0]['count'], 3)

    def test_no_placeholders_returns_no_hits(self):
        text = 'A clean paragraph mentioning Rs 5,93,60,000 with cite [KB #7].'
        cleaned, hits = narrative.scrub_placeholders(text)
        self.assertEqual(cleaned, text)
        self.assertEqual(hits, [])


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers — fake project + fake CalculationResult
# ─────────────────────────────────────────────────────────────────────────────

def _fake_project(
    title='Test project',
    fpo_name='Test FPO',
    *,
    # KAU 2026-09-19 §Promoter Profile — new DPRProject fields
    ceo_name='', ceo_qualification='', ceo_experience_years=None,
    total_area_acreage=None, women_shareholding_pct=None,
    landholding_summary='', board_meeting_frequency='',
    psc_members=None,
    # FPO membership snapshot — new pull-throughs into FACTS
    total_members=None, female_members=None,
    total_directors=None, women_directors=None,
):
    """SimpleNamespace project that quacks like a DPRProject for the pieces
    narrative.py touches. No DB required."""
    fpo = SimpleNamespace(
        id=1, name=fpo_name,
        total_members=total_members,
        female_members=female_members,
        total_directors=total_directors,
        women_directors=women_directors,
    )
    return SimpleNamespace(
        id=1,
        title=title,
        fpo=fpo,
        fpo_id=1,
        primary_commodity=None,
        primary_commodity_id=None,
        ceo_name=ceo_name,
        ceo_qualification=ceo_qualification,
        ceo_experience_years=ceo_experience_years,
        total_area_acreage=total_area_acreage,
        women_shareholding_pct=women_shareholding_pct,
        landholding_summary=landholding_summary,
        board_meeting_frequency=board_meeting_frequency,
        psc_members=psc_members or [],
    )


def _make_calc_result(
    *,
    cost_total=Decimal('9500000'),
    mof_total=Decimal('9500000'),
    promoter=Decimal('3800000'),
    term_loan=Decimal('4275000'),
    subsidy=Decimal('1425000'),
    wc_loan=Decimal('0'),
    y1_revenue=Decimal('21000000'),
    y1_opex=Decimal('11000000'),
    y1_ebitda=Decimal('10000000'),
    y1_pat=Decimal('2235000'),
    irr=Decimal('19.4'),
    npv=Decimal('6840000'),
    dscr_avg=Decimal('1.85'),
    dscr_min=Decimal('1.42'),
    payback=Decimal('4.2'),
    break_even=1,
) -> CalculationResult:
    """Build a fully-populated CalculationResult for the facts-formatter tests.

    Values mirror the "Wayanad Spice Growers turmeric" persona so KAU-facing
    examples reproduce.
    """
    cost = ProjectCostBreakdown(total=cost_total, by_field={})
    mof = MeansOfFinanceBreakdown(total=mof_total, by_field={
        'mof_promoters_contribution': promoter,
        'mof_bank_term_loan': term_loan,
        'mof_working_capital_loan': wc_loan,
        'mof_subsidy_grant': subsidy,
    })
    variance = CostMofVariance(
        cost_total=cost_total, mof_total=mof_total,
        delta=mof_total - cost_total, pct=Decimal('0'),
        threshold_pct=Decimal('10'), exceeds_threshold=False,
    )
    profit_loss = ProfitLoss(
        projection_years=10,
        rows=[ProfitLossRow(
            year=1, revenue=y1_revenue, operating_cost=y1_opex,
            ebitda=y1_ebitda, depreciation=Decimal('0'), ebit=y1_ebitda,
            interest=Decimal('0'), pbt=y1_ebitda, tax=Decimal('0'), pat=y1_pat,
        )],
        total_pat=y1_pat,
        cumulative_pat_by_year={1: y1_pat},
    )
    ratios = FinancialRatios(
        discount_rate_pct=Decimal('12'),
        npv=npv, irr_pct=irr, irr_converged=True,
        dscr_rows=[], dscr_min=dscr_min, dscr_avg=dscr_avg,
        payback_period_years=payback, break_even_year=break_even,
    )
    return CalculationResult(
        projection_years=10, cost=cost, mof=mof, variance=variance,
        profit_loss=profit_loss, ratios=ratios,
    )


# ─────────────────────────────────────────────────────────────────────────────
# format_calc_facts_for_prompt
# ─────────────────────────────────────────────────────────────────────────────

class FormatCalcFactsTests(unittest.TestCase):
    """The FACTS block is what the LLM quotes verbatim — any drift here
    means silently changing the DPR narrative for every FPO."""

    def test_facts_block_contains_all_required_labels(self):
        """Every FACTS label KAU reviewers rely on must be present."""
        facts = narrative.format_calc_facts_for_prompt(_fake_project(), _make_calc_result())
        for label in (
            'PROJECT FACTS',
            'Project title:', 'FPO / promoter:', 'Primary commodity:',
            'Total project cost:', 'Total means of finance:',
            'Promoter contribution:', 'Bank / term loan:',
            'Working capital loan:', 'Subsidy / grant:',
            'Debt : Equity ratio:',
            'Y1 revenue:', 'Y1 operating cost:', 'Y1 EBITDA:', 'Y1 PAT:',
            'IRR:', 'NPV', 'Average DSCR:',
            'Payback period', 'Break-even year:',
            'END FACTS',
        ):
            self.assertIn(label, facts, f'Missing FACTS label: {label!r}')

    def test_debt_equity_rendered_as_simplified_ratio(self):
        """Debt:Equity must render as `x.xx : 1`, matching the PDF fix."""
        result = _make_calc_result(
            term_loan=Decimal('4275000'),
            promoter=Decimal('3800000'),
        )
        facts = narrative.format_calc_facts_for_prompt(_fake_project(), result)
        # 4275000 / 3800000 = 1.125 → rounds to 1.12
        self.assertIn('1.12 : 1', facts)

    def test_debt_equity_when_no_equity_is_not_available(self):
        """Zero equity → division-by-zero avoided; renders as 'Not available'."""
        result = _make_calc_result(
            term_loan=Decimal('4000000'),
            promoter=Decimal('0'),
        )
        facts = narrative.format_calc_facts_for_prompt(_fake_project(), result)
        self.assertIn('Debt : Equity ratio:        Not available', facts)

    def test_missing_values_render_as_not_available_not_bracketed(self):
        """When a value is None (e.g. IRR failed to converge), we render
        `Not available` — never `[X]` or `[projected ...]`."""
        result = _make_calc_result(irr=None)
        facts = narrative.format_calc_facts_for_prompt(_fake_project(), result)
        self.assertIn('IRR:                        Not available', facts)
        self.assertNotIn('[X', facts)
        self.assertNotIn('[projected', facts)

    def test_facts_block_is_deterministic_for_same_result(self):
        """Same project + same CalculationResult → byte-identical output.
        Non-determinism here would break KAU's ability to reproduce a DPR."""
        result = _make_calc_result()
        p = _fake_project()
        a = narrative.format_calc_facts_for_prompt(p, result)
        b = narrative.format_calc_facts_for_prompt(p, result)
        self.assertEqual(a, b)

    def test_indian_comma_formatting_on_project_cost(self):
        """95 lakh should render `₹ 95,00,000.00`, not `₹ 9,500,000.00`
        (Indian numbering system, matching the PDF)."""
        result = _make_calc_result(cost_total=Decimal('9500000'))
        facts = narrative.format_calc_facts_for_prompt(_fake_project(), result)
        self.assertIn('₹ 95,00,000.00', facts)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3 — Promoter Profile fields flow into the FACTS block
# ─────────────────────────────────────────────────────────────────────────────

class PromoterProfileFactsTests(unittest.TestCase):
    """KAU 2026-09-19 §Promoter Profile added 8 new fields on DPRProject so
    the narrative stops emitting [Name of the CEO] / [PSC] / [area]. Verify
    every one of them lands in the FACTS block with a labelled line."""

    def test_ceo_details_appear_when_provided(self):
        project = _fake_project(
            ceo_name='Rajan Nair', ceo_qualification='B.Sc Agri, MBA',
            ceo_experience_years=12,
        )
        facts = narrative.format_calc_facts_for_prompt(project, _make_calc_result())
        self.assertIn('CEO name:                   Rajan Nair', facts)
        self.assertIn('CEO qualification:          B.Sc Agri, MBA', facts)
        self.assertIn('CEO experience:             12 years', facts)

    def test_ceo_missing_renders_not_available_not_bracketed(self):
        """Empty CEO fields → 'Not available' in prose. Never [Name of the CEO]."""
        project = _fake_project()  # all defaults blank/None
        facts = narrative.format_calc_facts_for_prompt(project, _make_calc_result())
        self.assertIn('CEO name:                   Not available', facts)
        self.assertNotIn('[Name of', facts)
        self.assertNotIn('[CEO', facts)

    def test_fpo_membership_pulled_from_fpo_row(self):
        """total_members / female_members / director counts come from FPO."""
        project = _fake_project(
            total_members=250, female_members=110,
            total_directors=9, women_directors=4,
        )
        facts = narrative.format_calc_facts_for_prompt(project, _make_calc_result())
        self.assertIn('250 members', facts)
        self.assertIn('110 women members', facts)
        self.assertIn('9 directors (4 women)', facts)

    def test_board_meeting_frequency_renders_display_value_not_key(self):
        """'quarterly' key → 'Quarterly' display label in the FACTS block."""
        project = _fake_project(board_meeting_frequency='quarterly')
        facts = narrative.format_calc_facts_for_prompt(project, _make_calc_result())
        self.assertIn('Board meeting frequency:    Quarterly', facts)

    def test_psc_members_list_renders_one_line_per_member(self):
        """PSC JSON list → one bullet per member in a multi-line block."""
        project = _fake_project(psc_members=[
            {'name': 'Dr. Rajan', 'role': 'Chair', 'affiliation': 'KAU'},
            {'name': 'Anitha Kumari', 'role': 'Member', 'affiliation': 'NABARD'},
        ])
        facts = narrative.format_calc_facts_for_prompt(project, _make_calc_result())
        self.assertIn('Dr. Rajan — Chair (KAU)', facts)
        self.assertIn('Anitha Kumari — Member (NABARD)', facts)

    def test_psc_empty_renders_not_constituted(self):
        project = _fake_project(psc_members=[])
        facts = narrative.format_calc_facts_for_prompt(project, _make_calc_result())
        self.assertIn('Not constituted / Not available', facts)

    def test_area_acreage_and_landholding_flow_through(self):
        project = _fake_project(
            total_area_acreage=Decimal('487.50'),
            women_shareholding_pct=Decimal('44.00'),
            landholding_summary='70% smallholders under 2 acres',
        )
        facts = narrative.format_calc_facts_for_prompt(project, _make_calc_result())
        self.assertIn('Total area covered:         487.50 acres', facts)
        self.assertIn('Women shareholding:         44.00%', facts)
        self.assertIn('Landholding pattern:        70% smallholders under 2 acres', facts)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2 — Provenance markers in FACTS block
# ─────────────────────────────────────────────────────────────────────────────

class ProvenanceFactsTests(unittest.TestCase):
    """KAU 2026-09-19 P2.1: the FACTS block must tag DPRConfig-driven rates
    as [system_default] so the LLM can mention provenance in prose instead
    of asserting them as project-specific."""

    def test_discount_rate_row_carries_system_default_tag(self):
        facts = narrative.format_calc_facts_for_prompt(_fake_project(), _make_calc_result())
        self.assertIn('Discount rate used:', facts)
        self.assertIn('[system_default]', facts)

    def test_system_assumptions_block_is_appended(self):
        """The 'System-default assumptions used by the calc engine' sub-block
        must appear so both the LLM AND the KAU reviewer see every rate."""
        facts = narrative.format_calc_facts_for_prompt(_fake_project(), _make_calc_result())
        self.assertIn('--- System-default assumptions used by the calc engine ---', facts)
        # A handful of the expected DPRConfig rate labels
        for label in (
            'NPV discount rate:',
            'Corporate tax rate:',
            'Loan interest rate (fallback):',
            'Buildings — SLM depreciation:',
            'Plant & machinery — SLM depreciation:',
        ):
            self.assertIn(label, facts, f'missing system assumption row: {label!r}')

    def test_new_hard_rule_10_present(self):
        """The provenance HARD RULE (rule 10) must be in every prompt so the
        LLM knows to mention [system_default] provenance in prose."""
        prompt = narrative.build_prompt(_fake_project(), 'executive_summary', [], calc_facts='x')
        self.assertIn('PROVENANCE', prompt)
        self.assertIn('[system_default]', prompt)

    def test_new_hard_rule_11_neutral_language_present(self):
        """KAU 2026-09-19 P6.4: HARD RULE 11 must forbid promotional
        adjectives + recommendation language. Locked in via the prompt
        so future prompt refactors can't silently regress."""
        prompt = narrative.build_prompt(_fake_project(), 'conclusion', [], calc_facts='x')
        self.assertIn('NEUTRAL BANK-APPRAISAL LANGUAGE', prompt)
        # A couple of the specific promotional adjectives KAU flagged
        self.assertIn('highly bankable', prompt)
        self.assertIn('state-of-the-art', prompt)
        # Must forbid loan-sanction recommendation
        self.assertIn('loan sanction', prompt)


# ─────────────────────────────────────────────────────────────────────────────
# build_prompt
# ─────────────────────────────────────────────────────────────────────────────

class BuildPromptTests(unittest.TestCase):
    """build_prompt() is the surface every chapter's generation runs through.
    The KAU 2026-09-19 fix hinges on the FACTS block landing above the
    knowledge_base block, and the anti-placeholder rules being at the end."""

    def test_prompt_contains_facts_block_when_provided(self):
        prompt = narrative.build_prompt(
            _fake_project(), 'executive_summary', [], calc_facts='FAKE_FACTS_MARKER',
        )
        self.assertIn('FAKE_FACTS_MARKER', prompt)

    def test_prompt_contains_new_hard_rules(self):
        """The 3 anti-hallucination rules (7, 8, 9) MUST be in the prompt —
        if they aren't, the fix is silently un-shipped."""
        prompt = narrative.build_prompt(
            _fake_project(), 'executive_summary', [], calc_facts='x',
        )
        self.assertIn('GROUNDING', prompt)
        self.assertIn('NO PLACEHOLDER TOKENS', prompt)
        self.assertIn('certifications', prompt)

    def test_prompt_no_longer_encourages_bracketed_placeholders(self):
        """The OLD prompt rule 7 said write '[projected annual turnover]'.
        The new prompt must forbid exactly that phrase pattern."""
        prompt = narrative.build_prompt(
            _fake_project(), 'executive_summary', [], calc_facts='x',
        )
        self.assertNotIn('natural placeholder', prompt)

    def test_prompt_calls_compute_when_no_calc_facts_provided(self):
        """Backwards-compat: passing calc_facts=None triggers compute() so
        older callers still work."""
        with patch(
            'apps.fpo.services.dpr.narrative.compute',
            return_value=_make_calc_result(),
        ) as m_compute:
            narrative.build_prompt(_fake_project(), 'executive_summary', [])
            self.assertEqual(m_compute.call_count, 1)


# ─────────────────────────────────────────────────────────────────────────────
# generate_all_narratives — order enforcement
# ─────────────────────────────────────────────────────────────────────────────

class GenerateAllNarrativesOrderingTests(unittest.TestCase):
    """KAU 2026-09-19: narrative generation MUST wait for a successful
    compute() and refuse to proceed if the calc engine can't produce a
    validated financial model."""

    def test_refuses_when_compute_raises(self):
        """If compute() blows up, no chapter should attempt LLM generation."""
        project = _fake_project()
        with patch(
            'apps.fpo.services.dpr.narrative.compute',
            side_effect=RuntimeError('calc engine kaput'),
        ):
            with self.assertRaises(narrative.NarrativeError) as ctx:
                narrative.generate_all_narratives(project)
            self.assertIn('calculation engine failed', str(ctx.exception))

    def test_computes_once_and_reuses_facts_across_chapters(self):
        """compute() should be called exactly once even though there are
        many chapters — avoiding N compute() passes was an explicit goal."""
        project = _fake_project()
        # DPRAIContent.objects.filter(...) is the skip_existing check — stub it
        # out so no DB round-trip happens.
        with patch(
            'apps.fpo.services.dpr.narrative.compute',
            return_value=_make_calc_result(),
        ) as m_compute, patch(
            'apps.fpo.services.dpr.narrative.generate_chapter',
            return_value=None,
        ) as m_gen, patch(
            'apps.fpo.services.dpr.narrative.DPRAIContent.objects',
            new_callable=MagicMock,
        ) as m_qs:
            m_qs.filter.return_value.first.return_value = None
            narrative.generate_all_narratives(project, skip_existing=False)
            # Exactly one compute() call for the whole run, regardless of N chapters
            self.assertEqual(m_compute.call_count, 1)
            # And every generate_chapter call received the pre-computed facts
            self.assertGreater(m_gen.call_count, 0)
            for call in m_gen.call_args_list:
                self.assertIn('calc_facts', call.kwargs)
                self.assertIsNotNone(call.kwargs['calc_facts'])


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2.3 — Cross-chapter consistency check
# ─────────────────────────────────────────────────────────────────────────────

class ConsistencyCheckTests(unittest.TestCase):
    """KAU 2026-09-19 P2.3: numeric mentions across chapters must agree with
    the calc-engine `CalculationResult`. Consistency check extracts numbers
    around metric keywords and classifies matches as ok / drift / mismatch."""

    def _result(self):
        return _make_calc_result(
            cost_total=Decimal('12685000'),
            mof_total=Decimal('12500000'),
            promoter=Decimal('3750000'),
            term_loan=Decimal('7500000'),
            irr=Decimal('19.4'),
            npv=Decimal('243482731.36'),
            dscr_avg=Decimal('30.06'),
            dscr_min=Decimal('19.76'),
            payback=Decimal('0.35'),
        )

    def test_clean_text_produces_zero_warnings(self):
        from apps.fpo.services.dpr.consistency_check import (
            check_chapter_text, expected_metrics,
        )
        text = (
            'The project has a Debt : Equity ratio of 2.00 : 1 and an '
            'average DSCR of 30.06 over the loan tenure. NPV works out '
            'to ₹ 24,34,82,731.36 with a payback period of 0.35 years.'
        )
        warns = check_chapter_text(text, expected_metrics(self._result()))
        self.assertEqual(warns, [])

    def test_dscr_min_reference_is_accepted(self):
        """The narrative may legitimately quote either DSCR avg (30.06) OR
        DSCR min (19.76) — both are valid; neither should be flagged."""
        from apps.fpo.services.dpr.consistency_check import (
            check_chapter_text, expected_metrics,
        )
        text = 'The minimum DSCR of 19.76 comfortably exceeds the 1.5x lender threshold.'
        warns = check_chapter_text(text, expected_metrics(self._result()))
        self.assertEqual([w.metric for w in warns], [])

    def test_mof_component_reference_is_accepted(self):
        """"Means of finance" keyword window may reference the total OR any
        component — promoter, bank, WC, subsidy — none should flag."""
        from apps.fpo.services.dpr.consistency_check import (
            check_chapter_text, expected_metrics,
        )
        text = 'The means of finance breakdown starts with a promoter contribution of ₹ 37,50,000.00.'
        warns = check_chapter_text(text, expected_metrics(self._result()))
        self.assertEqual(warns, [])

    def test_hard_mismatch_is_flagged(self):
        from apps.fpo.services.dpr.consistency_check import (
            check_chapter_text, expected_metrics,
        )
        # Wrong project cost — off by 27% from real value.
        text = 'The total project cost of ₹ 92,00,000.00 will be structured across the sources.'
        warns = check_chapter_text(text, expected_metrics(self._result()))
        self.assertEqual(len(warns), 1)
        self.assertEqual(warns[0].kind, 'mismatch')
        self.assertEqual(warns[0].metric, 'Project cost')

    def test_drift_within_tolerance_is_flagged_as_drift(self):
        from apps.fpo.services.dpr.consistency_check import (
            check_chapter_text, expected_metrics,
        )
        # NPV expected 243482731.36; found 244000000 — 0.21% off — within 0.5%
        # so this should NOT flag. Test with a real 1% drift instead.
        text = 'The projected NPV of ₹ 24,58,00,000.00 shows the value creation.'
        warns = check_chapter_text(text, expected_metrics(self._result()))
        self.assertEqual([w.kind for w in warns], ['drift'])

    def test_metric_with_no_calc_value_is_silently_skipped(self):
        """When calc has no IRR (didn't converge), any 'IRR' mention in
        text stays quiet — otherwise every DPR would light up warnings."""
        from apps.fpo.services.dpr.consistency_check import (
            check_chapter_text, expected_metrics,
        )
        result = _make_calc_result(irr=None)
        text = 'The IRR was not solvable given the cash-flow profile.'
        warns = check_chapter_text(text, expected_metrics(result))
        # IRR line skipped; other metrics not triggered by this text
        self.assertEqual([w.metric for w in warns if w.metric == 'IRR'], [])


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2.2 — Single-source-of-truth regression
# ─────────────────────────────────────────────────────────────────────────────

class TemplateSingleSourceTests(unittest.TestCase):
    """KAU 2026-09-19 P2.2: the PDF template must never do arithmetic —
    every rendered number should be a direct read of `r.<field>` on
    `CalculationResult` and passed through the `|money` filter. This test
    grep-lints the template file to fail if anyone later re-introduces
    inline computation that could shadow the calc engine.

    Not just style — KAU explicitly flagged that "the same figure must
    not be independently generated or reconstructed" across chapters.
    Silent drift caused by a stray `|add:` would violate that.
    """

    _TEMPLATE = 'apps/fpo/templates/dpr/report.html'

    def _read_template(self) -> str:
        import os
        # Anchor to project root — the tests_narrative_grounding file lives
        # at apps/fpo/tests_narrative_grounding.py, so climb two dirs up.
        here = os.path.dirname(os.path.abspath(__file__))
        root = os.path.abspath(os.path.join(here, '..', '..'))
        path = os.path.join(root, self._TEMPLATE)
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()

    def test_template_has_no_arithmetic_filters(self):
        """Fail if the template uses arithmetic filters like `|add:` /
        `|widthratio` / `|multiply` — these enable inline drift."""
        import re
        text = self._read_template()
        # Django's stock arithmetic filters that could shadow calc engine.
        offenders = re.findall(
            r'\|\s*(add|subtract|multiply|divide|widthratio|floatformat)\s*:',
            text,
        )
        # `|floatformat:0` for display precision is allowed — the money
        # filter used everywhere is Indian-comma-formatting, no arithmetic.
        # If someone adds `|floatformat` for numeric display, it's still
        # a signal to review manually.
        self.assertEqual(
            offenders, [],
            f'Template arithmetic filters detected in {self._TEMPLATE}: {offenders}. '
            'All numeric values must be pre-computed by CalculationResult; the '
            'template should only format via `|money`. See KAU 2026-09-19 P2.2.',
        )

    def test_template_only_reads_from_r_or_derived_context(self):
        """Every numeric-looking token in the body should originate from
        a `{{ r.* }}` read or a pre-computed context key
        (mof_breakdown_rows / cost_breakdown_rows / key_assumptions_rows /
        debt_equity_ratio_display), NOT from a hand-typed number.

        This is a soft check — literal digits in class names / mm sizes /
        column counts etc. are legitimate. We only assert the shape of the
        `{{ … }}` interpolations.
        """
        import re
        text = self._read_template()
        # All `{{ … }}` interpolations in the file.
        interps = re.findall(r'\{\{\s*([^}]+?)\s*\}\}', text)

        # Deny-list: interpolations that hard-code a number.
        # Allowed: r.*, project.*, fpo.*, generated_at, version_*,
        # cost_breakdown_rows, mof_breakdown_rows, technologies_with_flow,
        # pdf_products, pdf_hero_image, pdf_ai, chart_*, years, y, row.*,
        # cls.*, forloop.*, key_assumptions_rows, debt_equity_ratio_display.
        # Match anything starting with a bare digit — that would be a
        # hard-coded number displayed in the DPR body.
        bad = [i for i in interps if re.match(r'^\d', i)]
        self.assertEqual(
            bad, [],
            f'Template contains hard-coded numeric interpolations: {bad}. '
            'These should be pre-computed on CalculationResult so a single '
            'source of truth remains authoritative.',
        )


# ─────────────────────────────────────────────────────────────────────────────
# Phase 6.6 — Cross-chain operational consistency
# ─────────────────────────────────────────────────────────────────────────────

class ChainConsistencyTests(unittest.TestCase):
    """Kefitech 2026-09-19 P6.6: check_operational_chain() flags structural
    holes in the project plan (production ↔ raw material ↔ machinery ↔
    manpower ↔ utilities). Skips early-stage drafts."""

    def _blank_project(self, y1_revenue=Decimal('0')):
        """SimpleNamespace project with a section_finance carrying a single
        revenue_assumptions row and blank opex fields. All section_*
        managers are missing so every _section_has_rows check returns
        False by design."""
        ra = SimpleNamespace(
            annual_sales_revenue=y1_revenue,
            year1_sales_quantity=Decimal('0'),
            expected_selling_price=Decimal('0'),
        )
        fin = SimpleNamespace(
            revenue_assumptions=SimpleNamespace(all=lambda: [ra]),
            op_raw_material=Decimal('0'),
            op_salaries_wages=Decimal('0'),
            op_electricity=Decimal('0'),
            op_water=Decimal('0'),
            op_fuel=Decimal('0'),
        )
        return SimpleNamespace(section_finance=fin)

    def test_low_revenue_draft_produces_no_warnings(self):
        """Under the ₹10L Y1 revenue threshold, don't drown the FPO in
        chain warnings — the plan is still in draft."""
        from apps.fpo.services.dpr.chain_consistency import check_operational_chain
        p = self._blank_project(y1_revenue=Decimal('500000'))
        self.assertEqual(check_operational_chain(p), [])

    def test_high_revenue_no_products_flags_error(self):
        """₹5 Cr revenue but no products / raw material / machinery →
        multiple errors (all severity='error') to block a final render."""
        from apps.fpo.services.dpr.chain_consistency import check_operational_chain
        p = self._blank_project(y1_revenue=Decimal('50000000'))
        warns = check_operational_chain(p)
        errors = [w for w in warns if w.severity == 'error']
        checks_flagged = {w.check for w in errors}
        self.assertIn('products_vs_revenue', checks_flagged)
        self.assertIn('raw_material_vs_production', checks_flagged)
        self.assertIn('machinery_vs_production', checks_flagged)

    def test_high_revenue_zero_utilities_flags_warning(self):
        """₹5 Cr revenue + zero utility opex → warning, not error."""
        from apps.fpo.services.dpr.chain_consistency import check_operational_chain
        p = self._blank_project(y1_revenue=Decimal('50000000'))
        warns = check_operational_chain(p)
        util_warns = [w for w in warns if w.check == 'utilities_vs_production']
        self.assertEqual(len(util_warns), 1)
        self.assertEqual(util_warns[0].severity, 'warning')


if __name__ == '__main__':
    # Convenience: run directly with `python -m apps.fpo.tests_narrative_grounding`
    # after `django.setup()`.
    import django
    django.setup()
    unittest.main(verbosity=2)
