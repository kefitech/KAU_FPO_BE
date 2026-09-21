"""
DPR provenance helpers — track which values were user-entered vs
platform-configured (`system_default`) vs AI-inferred.

Purpose: KAU 2026-09-19 AI review (AI.docx) asked that DPR values
"remain distinguishable" between:
    - user-entered   → the FPO typed / uploaded the value
    - system_default → came from a KAU DPRConfig row (rates, thresholds)
    - ai_inferred    → the AI produced it (currently unused; slot kept
                        so Phase 4b AI-fill can adopt it without a refactor)

Where this feeds:
    - `apps.fpo.services.dpr.narrative.format_calc_facts_for_prompt()` —
       tags each FACTS-block rate line with the source so the LLM can
       mention provenance in prose ("using the platform's default 12%
       discount rate…" rather than asserting it as a project-specific
       fact).
    - `apps.fpo.services.dpr.pdf.key_assumptions_rows()` — surfaces every
       system_default rate used in the compute as a "Key Assumptions"
       mini-table just before the Limitations chapter.

The list of KAU-configurable rate keys mirrors what
`calculation.py` reads via `DPRConfig.get_decimal(...)`; if a new
DPRConfig-backed rate is introduced there, add it here too so it shows
up in the FACTS block + Key Assumptions table.

Author: Athul Gopan (Kefi Tech Solutions)
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from apps.database.models import DPRConfig


# DPRConfig keys the calc engine reads. Order matches presentation order
# in the Key Assumptions table. `label` is what shows up on the PDF row.
_SYSTEM_RATE_KEYS: list[tuple[str, str, Decimal]] = [
    ('discount_rate_pct',                  'NPV discount rate',            Decimal('12')),
    ('tax_rate_pct',                       'Corporate tax rate',           Decimal('25.17')),
    ('inflation_rate_pct',                 'General inflation / OPEX escalator', Decimal('6')),
    ('loan_interest_rate_default_pct',     'Loan interest rate (fallback)', Decimal('10.5')),
    ('depreciation_rate_building_pct',     'Buildings — SLM depreciation', Decimal('10')),
    ('depreciation_rate_machinery_pct',    'Plant & machinery — SLM depreciation', Decimal('15')),
    ('depreciation_rate_equipment_pct',    'Equipment & vehicles — SLM depreciation', Decimal('15')),
    ('project_cost_variance_pct',          'Project cost variance tolerance', Decimal('10')),
]


@dataclass
class Assumption:
    """One system-default rate used in the compute.
    `key`   — DPRConfig key
    `label` — human label shown on PDF + admin
    `value` — the Decimal used at compute time (from DPRConfig; falls back
              to the code default if the row is missing)
    `overridden` — True when the FPO's per-project override is used instead
                   of DPRConfig (only relevant for the 6 Finance §Cat I
                   escalation rates today). Reserved slot — the current
                   FACTS block doesn't render an override-badge yet, but
                   the model row is ready for it.
    """
    key: str
    label: str
    value: Decimal
    overridden: bool = False


def collect_system_assumptions() -> list[Assumption]:
    """Return every system-default rate the calc engine uses.

    Values snapshotted from DPRConfig at call time (same read path as
    the calc engine — see `calculation.py`), with the code-default as
    a fallback so a missing config row still renders a plausible number
    rather than blowing up.
    """
    rows: list[Assumption] = []
    for cfg_key, label, code_default in _SYSTEM_RATE_KEYS:
        value = DPRConfig.get_decimal(cfg_key, code_default)
        rows.append(Assumption(key=cfg_key, label=label, value=value))
    return rows
