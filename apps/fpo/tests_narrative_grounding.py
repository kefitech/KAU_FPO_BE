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


if __name__ == '__main__':
    # Convenience: run directly with `python -m apps.fpo.tests_narrative_grounding`
    # after `django.setup()`.
    import django
    django.setup()
    unittest.main(verbosity=2)
