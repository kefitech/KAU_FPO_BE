"""
DPR Pre-Flight Blockers — normalise `_pre_final_validation` output into a
UI-friendly shape and filter by applicability.

Usage (from the pre-flight endpoint):
    from apps.fpo.services.dpr.blockers import get_blockers
    result = get_blockers(project)
    # → {'can_generate': bool, 'blockers': [{message, target, ...}, ...]}

Every entry has:
    * message         — human-readable text (from _pre_final_validation)
    * target          — 'wizard' | 'ai-content'  (drives FE navigation)
    * section_key     — wizard section slug when target='wizard'   (e.g. 'finance')
    * section_label   — display label for the section             (e.g. 'Finance')
    * chapter         — AI chapter key when target='ai-content'   (e.g. 'promoter_profile')

Applicability filter:
    Blockers whose section is Hidden by the DPR applicability matrix
    (KAU RCD A.1 Level 1) are dropped — no point telling the FPO to fix
    a section the admin has explicitly turned off for their component mix.
    AI-content blockers are never filtered (they don't live in the wizard).

Author: Athul Gopan (Kefi Tech Solutions)
"""
from __future__ import annotations

from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# Mapping tables — raw chapter/check codes → wizard section keys
# ─────────────────────────────────────────────────────────────────────────────

# Chain-consistency `check` field → wizard section key + display label.
# Keep in sync with checks in apps/fpo/services/dpr/chain_consistency.py.
_CHECK_TO_SECTION: dict[str, tuple[str, str]] = {
    'products_vs_revenue':          ('products',     'Products & Services'),
    'raw_material_vs_production':   ('raw-material', 'Raw Material'),
    'raw_material_opex_missing':    ('finance',      'Finance (Operating Costs)'),
    'machinery_vs_production':      ('machinery',    'Plant & Machinery'),
    'manpower_vs_production':       ('hr',           'HR & Organisation'),
    'utilities_vs_production':      ('utilities',    'Utilities & Waste'),
    'salaries_vs_manpower':         ('finance',      'Finance (Operating Costs)'),
}

# String chapter values used directly by _pre_final_validation (not chain
# consistency check codes) — the §E revenue_assumption emitter uses 'finance'.
_SECTION_LABELS: dict[str, str] = {
    'finance': 'Finance',
}

# AI chapter keys — human-readable labels for the banner text.
_AI_CHAPTER_LABELS: dict[str, str] = {
    'executive_summary':    'Executive Summary',
    'project_background':   'Project Background',
    'promoter_profile':     'Promoter Profile',
    'market_analysis':      'Market Analysis',
    'technical_feasibility':'Technical Feasibility',
    'financial_analysis':   'Financial Analysis',
    'implementation_plan':  'Implementation Plan',
    'swot':                 'SWOT Analysis',
    'environmental_impact': 'Environmental Impact',
    'conclusion':           'Conclusion',
    'risk_analysis':        'Risk Analysis',
}


# ─────────────────────────────────────────────────────────────────────────────
# Enrichment
# ─────────────────────────────────────────────────────────────────────────────

def _classify(raw: dict) -> dict:
    """Turn a raw `_pre_final_validation` entry into a UI-friendly blocker."""
    reason = raw.get('reason', '')
    chapter = raw.get('chapter', '')
    check = raw.get('check')

    # Case A — chain_consistency emitter (has `check` field)
    if check and check in _CHECK_TO_SECTION:
        section_key, section_label = _CHECK_TO_SECTION[check]
        return {
            'message':       reason,
            'target':        'wizard',
            'section_key':   section_key,
            'section_label': section_label,
        }

    # Case B — AI content emitter (chapter is an AI chapter key)
    if chapter in _AI_CHAPTER_LABELS:
        return {
            'message':       reason,
            'target':        'ai-content',
            'chapter':       chapter,
            'chapter_label': _AI_CHAPTER_LABELS[chapter],
        }

    # Case C — direct section slug (currently only 'finance' from §E emitter)
    if chapter in _SECTION_LABELS:
        return {
            'message':       reason,
            'target':        'wizard',
            'section_key':   chapter,
            'section_label': _SECTION_LABELS[chapter],
        }

    # Fallback — unknown chapter (defensive). Surface as generic blocker so
    # the FPO at least sees the message; no jump link because we can't map it.
    return {
        'message':       reason or 'Unknown blocker',
        'target':        'unknown',
        'section_label': chapter or '—',
    }


# ─────────────────────────────────────────────────────────────────────────────
# Applicability filter
# ─────────────────────────────────────────────────────────────────────────────

def _applicability_visible_sections(project) -> set[str]:
    """Section keys the wizard shows for this project (per applicability
    matrix + always-mandatory overrides). Falls back to "all sections
    visible" if the rule engine can't run for any reason."""
    try:
        from apps.fpo.services.dpr.rule_engine import visible_sections
        return set(visible_sections(project))
    except Exception:  # noqa: BLE001 — best-effort, never break pre-flight
        return set()  # empty = no filter applied (fail-open)


# ─────────────────────────────────────────────────────────────────────────────
# Public entrypoint
# ─────────────────────────────────────────────────────────────────────────────

def get_blockers(project) -> dict[str, Any]:
    """Return the DPR pre-flight status for one project.

    Shape:
        {
            'can_generate': bool,
            'blockers': [enriched-blocker-dict, ...],
        }
    """
    from apps.fpo.services.dpr.pdf import _pre_final_validation

    raw = _pre_final_validation(project)
    enriched = [_classify(e) for e in raw]

    # Applicability filter — drop wizard blockers pointing at hidden sections.
    # AI-content blockers pass through unfiltered (they live outside the matrix).
    visible = _applicability_visible_sections(project)
    if visible:
        filtered = []
        for b in enriched:
            if b['target'] == 'wizard' and b.get('section_key') not in visible:
                continue  # section is Hidden — admin decided not to require it
            filtered.append(b)
    else:
        filtered = enriched

    return {
        'can_generate': len(filtered) == 0,
        'blockers':     filtered,
    }
