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
from typing import Optional

from apps.database.models import DPRConfig


# DPRConfig keys the calc engine reads. Order matches presentation order
# in the Key Assumptions table. `label` is what shows up on the PDF row.
# `override_field` — if set, this names the Finance-section field that lets
# the FPO override the platform default on a per-project basis. The calc
# engine reads the project value first and only falls back to DPRConfig
# when the project field is None.
_SYSTEM_RATE_KEYS: list[tuple[str, str, Decimal, Optional[str]]] = [
    ('discount_rate_pct',                  'NPV discount rate',            Decimal('12'),    None),
    ('tax_rate_pct',                       'Corporate tax rate',           Decimal('25.17'), None),
    ('inflation_rate_pct',                 'General inflation / OPEX escalator', Decimal('6'), 'inflation_rate_pct'),
    ('loan_interest_rate_default_pct',     'Loan interest rate',           Decimal('10.5'),  'rate_of_interest_pct'),
    ('depreciation_rate_building_pct',     'Buildings — SLM depreciation', Decimal('10'),    None),
    ('depreciation_rate_machinery_pct',    'Plant & machinery — SLM depreciation', Decimal('15'), None),
    # KAU review 2026-10-08 Pattern 12: this one rate serves the equipment,
    # vehicles AND electrification/utilities classes — label must match the
    # depreciation table instead of saying "Equipment & vehicles" alone.
    ('depreciation_rate_equipment_pct',    'Equipment, furniture, vehicles & utilities — SLM depreciation', Decimal('15'), None),
    ('project_cost_variance_pct',          'Project cost variance tolerance', Decimal('10'), None),
]


@dataclass
class Assumption:
    """One rate used in the compute.

    `key`   — DPRConfig key
    `label` — human label shown on PDF + admin
    `value` — the Decimal actually used at compute time. When the project
              overrode via Finance section, this is the FPO's number; else
              it's the DPRConfig / code-default.
    `platform_default` — the DPRConfig / code default (what the engine
              would have used had the project not overridden).
    `overridden` — True when the FPO's per-project override is in use.
    """
    key: str
    label: str
    value: Decimal
    platform_default: Decimal = Decimal('0')
    overridden: bool = False


def _project_override(project, override_field: Optional[str]) -> Optional[Decimal]:
    """Return the project-level override for a rate if the FPO entered one.

    Only reads from `project.section_finance.<field>`. Returns None when the
    project / section / field is missing OR when the value is None.
    """
    if not project or not override_field:
        return None
    fin = getattr(project, 'section_finance', None)
    if fin is None:
        return None
    val = getattr(fin, override_field, None)
    if val is None:
        return None
    try:
        return Decimal(str(val))
    except (TypeError, ValueError, ArithmeticError):
        return None


def collect_system_assumptions(project=None) -> list[Assumption]:
    """Return every rate the calc engine uses — project overrides win.

    When `project` is passed in, each row reports the FPO's own value where
    the project overrode via Finance section. The platform_default field is
    always populated so callers can show "project value X% overrides
    platform default Y%" in prose or in a mini-table.

    DPR-10 (UAT): the testing team flagged that the Key Assumptions table
    was labelling EVERY rate as 'KAU DPR platform default' even for
    projects that supplied their own loan interest rate. The LLM then
    narrated 'the term loan interest is structured around a fallback rate
    of 10.50%' for a project running on 6%. Returning the actual value
    with an explicit `overridden` flag fixes both the PDF table and the
    FACTS block the narrative reads from.
    """
    rows: list[Assumption] = []
    for cfg_key, label, code_default, override_field in _SYSTEM_RATE_KEYS:
        platform_default = DPRConfig.get_decimal(cfg_key, code_default)
        override = _project_override(project, override_field)
        # BUG-19 (KAU Section 6): only mark as "overrides platform default"
        # when the project value is actually DIFFERENT from the default. A
        # project that enters 10.50% matching the default should read as
        # "10.50% (platform default)", not the self-contradicting
        # "Project-entered 10.50% overrides the platform default of 10.50%".
        if override is not None and override != platform_default:
            rows.append(Assumption(
                key=cfg_key, label=label,
                value=override,
                platform_default=platform_default,
                overridden=True,
            ))
        else:
            rows.append(Assumption(
                key=cfg_key, label=label,
                value=platform_default,
                platform_default=platform_default,
                overridden=False,
            ))
    return rows
