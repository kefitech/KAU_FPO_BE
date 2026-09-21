"""
DPR cross-chapter consistency check (KAU AI review 2026-09-19 §P2.3).

Runs after `generate_all_narratives()` (or standalone). For each of ~8
canonical financial metrics (project cost, MoF, debt:equity ratio, IRR,
NPV, DSCR average, payback, break-even), extract every numeric mention
from each chapter's active narrative text and compare against the
`CalculationResult`.

Two failure kinds:
  - **mismatch** — a number attributed to a canonical metric doesn't
    match the calc-engine value even after normalising for units.
    Example: exec summary says "DSCR of 25.4" when the calc says 30.06.
  - **drift**  — the narrative used a rounded / approximated form
    (e.g. "roughly ₹1.27 crore" instead of the precise ₹1,26,85,000).
    Tolerable but flagged so KAU reviewers can spot which chapters
    took stylistic liberties.

Warnings land on `DPRAIContent.consistency_warnings` (list of dicts);
the FE + admin viewer surface them.

Deliberately NARROW scope: only 8 metrics, no generic number-hunting
across all sentences. Avoids false positives on industry statistics,
KB citations or year references.

Author: Athul Gopan (Kefi Tech Solutions)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Optional

from apps.database.models import DPRAIContent, DPRProject
from apps.fpo.services.dpr.calculation import CalculationResult, compute


# ─────────────────────────────────────────────────────────────────────────────
# Expected-values snapshot
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ExpectedMetric:
    """One canonical metric from the calc engine.

    `values` — every value the narrative may legitimately quote under this
    metric's keyword window. Multiple entries allowed because e.g. "Means
    of finance" is a keyword that plausibly precedes the MoF total OR any
    single component (promoter contribution, bank loan, subsidy) — all
    valid quotes. The classifier accepts the closest-matching entry;
    mismatch fires only if the extracted number is far from ALL of them.

    `unit` is a hint used to normalise regex hits — 'money' hits get
    stripped of ₹/commas, '%' hits get the % stripped, 'ratio' hits
    like '1.50 : 1' are parsed specially.
    """
    label: str
    values: list[Decimal]
    unit: str            # 'money' / 'pct' / 'ratio' / 'years' / 'year'
    tolerance_pct: Decimal = Decimal('1.5')  # per-metric drift tolerance in %

    @property
    def primary(self) -> Optional[Decimal]:
        """The canonical value — first non-None in `values`. Used for warning display."""
        for v in self.values:
            if v is not None:
                return v
        return None

    @property
    def has_any_value(self) -> bool:
        return any(v is not None for v in self.values)


def _debt_equity_ratio(mof_by_field: dict) -> Optional[Decimal]:
    debt = mof_by_field.get('mof_bank_term_loan') or Decimal('0')
    equity = mof_by_field.get('mof_promoters_contribution') or Decimal('0')
    if not isinstance(debt, Decimal):
        debt = Decimal(str(debt))
    if not isinstance(equity, Decimal):
        equity = Decimal(str(equity))
    if equity <= 0:
        return None
    return (debt / equity).quantize(Decimal('0.01'))


def _filter_none(vals: list[Optional[Decimal]]) -> list[Decimal]:
    return [v for v in vals if v is not None]


def expected_metrics(result: CalculationResult) -> list[ExpectedMetric]:
    """Pull the ~8 canonical metrics we consistency-check against.

    Each metric carries every value a chapter could legitimately quote
    under its keyword window — so "DSCR" is allowed to be either the
    average OR the minimum without triggering a mismatch, and "Means of
    finance" accepts the total OR any breakdown line.
    """
    ratios = result.ratios
    mof_bf = result.mof.by_field
    y1 = result.profit_loss.rows[0] if result.profit_loss and result.profit_loss.rows else None
    return [
        ExpectedMetric(
            'Project cost',
            _filter_none([result.cost.total]),
            'money',
        ),
        ExpectedMetric(
            'Means of finance',
            _filter_none([
                result.mof.total,
                mof_bf.get('mof_promoters_contribution'),
                mof_bf.get('mof_bank_term_loan'),
                mof_bf.get('mof_working_capital_loan'),
                mof_bf.get('mof_subsidy_grant'),
            ]),
            'money',
        ),
        ExpectedMetric(
            'Debt:Equity',
            _filter_none([_debt_equity_ratio(mof_bf)]),
            'ratio',
        ),
        ExpectedMetric(
            'IRR',
            _filter_none([ratios.irr_pct if ratios else None]),
            'pct',
        ),
        ExpectedMetric(
            'NPV',
            _filter_none([ratios.npv if ratios else None]),
            'money',
        ),
        ExpectedMetric(
            'DSCR',
            _filter_none([
                ratios.dscr_avg if ratios else None,
                ratios.dscr_min if ratios else None,
            ]),
            'ratio',
            tolerance_pct=Decimal('2'),
        ),
        ExpectedMetric(
            'Payback',
            _filter_none([ratios.payback_period_years if ratios else None]),
            'years',
            tolerance_pct=Decimal('5'),
        ),
        ExpectedMetric(
            'Y1 PAT',
            _filter_none([y1.pat if y1 else None]),
            'money',
        ),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Extractors — surface numbers from a chapter's prose that a metric
# mention could plausibly refer to. Each returns Decimal + the excerpt
# window so the warning row can show WHERE in the text the drift lives.
# ─────────────────────────────────────────────────────────────────────────────

# Money — ₹ (with or without space), optional Indian-comma groups, decimals.
# Captures the numeric part; the ₹ sign is fixed so we don't misinterpret
# member counts or year numbers as money.
_MONEY_RE = re.compile(r'₹\s*([0-9][0-9,]*(?:\.[0-9]+)?)')
# Percentages — number followed by %, capture the number. Discount / IRR / etc.
_PCT_RE   = re.compile(r'(?<![A-Za-z])([0-9]+(?:\.[0-9]+)?)\s*%')
# Debt:Equity ratio — "x.xx : 1", "x : 1", "x.x:1"; captures LHS.
_RATIO_RE = re.compile(r'([0-9]+(?:\.[0-9]+)?)\s*:\s*1')
# Bare number close to a keyword — used for DSCR / payback where the
# narrative might say "DSCR of 30.06" or "payback of 4.2 years".
_BARE_NUM = r'([0-9]+(?:\.[0-9]+)?)'


def _strip_indian_commas(s: str) -> Decimal:
    return Decimal(s.replace(',', ''))


def _to_decimal(s: str) -> Optional[Decimal]:
    try:
        return Decimal(s.replace(',', ''))
    except Exception:
        return None


# Keyword windows for each metric — text before the number that anchors
# the hit to a specific metric. Prevents matching random money mentions
# as "project cost".
_METRIC_KEYWORDS: dict[str, list[str]] = {
    'Project cost':     ['project cost', 'total project cost', 'capital outlay',
                          'total capital', 'total cost', 'capital cost'],
    'Means of finance': ['means of finance', 'total means of finance',
                          'total mof', 'financing structure totals'],
    'Debt:Equity':      ['debt : equity', 'debt to equity', 'debt-equity',
                          'de ratio', 'd:e', 'debt/equity'],
    'IRR':              ['irr', 'internal rate of return'],
    'NPV':              ['npv', 'net present value'],
    'DSCR':             ['dscr', 'debt service coverage', 'debt-service coverage'],
    'Payback':          ['payback', 'payback period'],
    'Y1 PAT':           ['year 1 pat', 'y1 pat', 'first-year pat', 'first year pat',
                          'year one pat', 'net profit after tax', 'y1 net profit'],
}

# How far after a keyword to search for the number — a narrow window so
# "DSCR" followed 200 chars later by an unrelated 30.06 doesn't false-match.
_WINDOW_CHARS = 100


def _find_metric_hits(text: str, metric: ExpectedMetric) -> list[tuple[Decimal, str]]:
    """Return (value, excerpt) pairs where `text` mentions this metric.
    An empty list means the chapter didn't reference this metric at all —
    perfectly fine; skip the check for it in that chapter."""
    keywords = _METRIC_KEYWORDS.get(metric.label, [])
    if not keywords:
        return []
    hits: list[tuple[Decimal, str]] = []
    lower = text.lower()

    for kw in keywords:
        start = 0
        while True:
            idx = lower.find(kw, start)
            if idx == -1:
                break
            window_start = idx
            window_end = min(len(text), idx + len(kw) + _WINDOW_CHARS)
            window = text[window_start:window_end]

            value = _extract_value_from_window(window, metric.unit)
            if value is not None:
                # Excerpt for the warning display — the window is a good
                # human-readable anchor and short enough to render in FE.
                excerpt = window.replace('\n', ' ').strip()[:180]
                hits.append((value, excerpt))
            start = idx + len(kw)
    return hits


def _extract_value_from_window(window: str, unit: str) -> Optional[Decimal]:
    """Pull the first plausible number out of the window given the unit hint."""
    if unit == 'money':
        m = _MONEY_RE.search(window)
        if m:
            return _to_decimal(m.group(1))
        return None
    if unit == 'pct':
        m = _PCT_RE.search(window)
        if m:
            return _to_decimal(m.group(1))
        return None
    if unit == 'ratio':
        m = _RATIO_RE.search(window)
        if m:
            return _to_decimal(m.group(1))
        # Fallback: some LLMs write "DSCR of 30.06" without a colon — bare number.
        m = re.search(_BARE_NUM, window)
        if m:
            return _to_decimal(m.group(1))
        return None
    if unit in ('years', 'year'):
        # "4.2 years" or plain number
        m = re.search(_BARE_NUM + r'\s*years?', window)
        if m:
            return _to_decimal(m.group(1))
        m = re.search(_BARE_NUM, window)
        if m:
            return _to_decimal(m.group(1))
        return None
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Comparison
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Warning:
    metric: str
    expected: str
    found: str
    kind: str          # 'mismatch' or 'drift'
    excerpt: str


def _classify_against_candidates(
    candidates: list[Decimal], found: Decimal, tolerance_pct: Decimal,
) -> tuple[Optional[str], Optional[Decimal]]:
    """Compare `found` against every candidate expected value; pick the
    closest one and return (kind, closest_candidate). `kind` is None when
    the found value matches ANY candidate within tolerance."""
    best_kind: Optional[str] = 'mismatch'
    best_candidate: Optional[Decimal] = None
    for expected in candidates:
        if expected == found:
            return (None, expected)
        if expected == 0:
            # Non-zero found against zero expected — mismatch, but keep
            # scanning for a better candidate.
            if best_kind == 'mismatch' and best_candidate is None:
                best_candidate = expected
            continue
        diff_pct = (abs(found - expected) / abs(expected)) * Decimal('100')
        if diff_pct <= Decimal('0.5'):
            # As-good-as exact.
            return (None, expected)
        if diff_pct <= tolerance_pct:
            # Drift wins over mismatch when scanning; upgrade if we haven't
            # already found an exact match.
            if best_kind == 'mismatch':
                best_kind = 'drift'
                best_candidate = expected
        # else: keep best_kind='mismatch' with best_candidate = first candidate
        if best_candidate is None:
            best_candidate = expected
    return (best_kind, best_candidate)


# KB citation regex — we strip [KB #NN] / [KB #100] etc. from the text
# BEFORE running the metric extraction. Otherwise the DSCR-keyword window
# lands on a "Sources: KB #23, KB #22, ..." trailing footer and reads the
# citation IDs as bogus DSCR values.
_KB_CITATION_RE = re.compile(r'\[KB\s*#\d+\]')
# Same for the "Sources: KB #N, KB #M" footer we render at the end of each
# assembled chapter (see _assemble_chapter_text) — mask the whole line.
_SOURCES_FOOTER_RE = re.compile(r'Sources:\s*(?:KB\s*#\d+,?\s*)+\.?', re.IGNORECASE)


def _strip_citations(text: str) -> str:
    """Remove [KB #N] tokens + 'Sources: KB #…' footer so numeric extraction
    doesn't misinterpret citation IDs as financial values."""
    text = _SOURCES_FOOTER_RE.sub(' ', text)
    text = _KB_CITATION_RE.sub(' ', text)
    return text


def check_chapter_text(text: str, expected: Iterable[ExpectedMetric]) -> list[Warning]:
    """Compare each metric mention in `text` against the ExpectedMetric.
    Empty result means the chapter is consistent (or doesn't mention any
    of the canonical metrics)."""
    text = _strip_citations(text)
    warnings: list[Warning] = []
    for m in expected:
        if not m.has_any_value:
            # Skip metrics whose calc values are all unavailable (e.g. IRR
            # didn't converge) — flagging every mention of "IRR" in that
            # case would be noise.
            continue
        # Dedup within a metric — a single sentence may match two synonym
        # keywords ("project cost" + "total cost") and produce identical
        # hits. Key on the raw value alone; if the same number is
        # extracted twice under the same metric, one warning is enough.
        seen: set[str] = set()
        for found_value, excerpt in _find_metric_hits(text, m):
            key = str(found_value)
            if key in seen:
                continue
            seen.add(key)
            kind, matched = _classify_against_candidates(
                m.values, found_value, m.tolerance_pct,
            )
            if kind is None:
                continue
            warnings.append(Warning(
                metric=m.label,
                expected=str(matched) if matched is not None else str(m.primary),
                found=str(found_value),
                kind=kind,
                excerpt=excerpt,
            ))
    return warnings


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def check_project_chapters(
    project: DPRProject,
    result: Optional[CalculationResult] = None,
) -> dict[str, list[Warning]]:
    """Run the consistency check on every DPRAIContent chapter of `project`
    and persist the results to `DPRAIContent.consistency_warnings`.

    Returns a `{chapter_key: [Warning, ...]}` summary so the caller
    (generate_all_narratives, admin API) can log the outcome.
    Empty chapters (no active/user_edited text) are skipped silently.

    Called at the end of `generate_all_narratives()` so the FE badge
    lights up on the next GET without a separate refresh step. Also
    safe to call standalone — e.g. from a Django shell to re-audit
    an existing project without regenerating.
    """
    if result is None:
        result = compute(project)
    expected = expected_metrics(result)

    summary: dict[str, list[Warning]] = {}
    for row in DPRAIContent.objects.filter(project=project):
        text = row.user_edited or row.candidate_regen or ''
        if not text:
            # No narrative to check — clear any stale warnings.
            if row.consistency_warnings:
                row.consistency_warnings = []
                row.save(update_fields=['consistency_warnings'])
            continue

        warnings = check_chapter_text(text, expected)
        row.consistency_warnings = [w.__dict__ for w in warnings]
        row.save(update_fields=['consistency_warnings'])
        if warnings:
            summary[row.chapter] = warnings
    return summary
