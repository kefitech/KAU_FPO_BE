"""
DPR §Knowledge Retrieval — selects relevant knowledge base entries for a project.

Per KAU RCD A.2: AI-generated narratives must be grounded in authoritative
sources (KAU PoP, schemes, SOPs, statutory portals, AGMARKNET). Phase 5's
narrative generator will call this service to gather relevant KB entries,
pack them into the Claude API context, and record the IDs used per chapter
for traceability.

Retrieval philosophy:
    An entry MATCHES a project when EACH of its filter dimensions is either
    blank (universal) OR contains the project's value. That lets one table
    hold state-wide statutory rules (blank commodity, blank component) side
    by side with commodity-specific PoP notes (turmeric only) without any
    kind of separate index or scoring model.

    Multi-dimensional narrowing is applied in this order:
      1. `is_active=True` — never surface superseded / deactivated entries
      2. `language` match (fall back to English if requested language absent)
      3. `section_keys` — either blank OR contains the target section key
      4. `commodities` — either empty M2M OR contains project's primary
      5. `components` — either empty M2M OR intersects project's components
      6. `business_types` — either empty M2M OR intersects project's business

Ranking:
    Ties are broken by specificity — entries with MORE non-empty filters win
    (they were authored specifically for this narrower slice). This runs at
    the Python layer rather than SQL because Django can't express a
    "M2M row count" predicate portably.

Caller contract:
    `get_context_for_project(project, section_key, language='en', limit=20)`
    returns an ordered list of `DPRKnowledgeEntry` instances. Callers should
    read `.content` for the text and `.id` for the traceability record.

Author: Athul Gopan (Kefi Tech Solutions)
"""
from __future__ import annotations

from typing import List, Optional

from django.db.models import Prefetch, Q

from apps.database.models import DPRKnowledgeEntry, DPRProject


# Retrieval never returns more than this by default — packing dozens of
# entries into the Claude prompt wastes tokens and dilutes relevance. Callers
# needing more can pass `limit=` explicitly.
DEFAULT_LIMIT = 20


def _project_context(project: DPRProject) -> dict:
    """Extract retrieval anchors from a DPR project.

    Returns a dict with:
      - commodity_id: primary commodity FK id (or None)
      - component_ids: list of DPRComponent ids in this project
      - business_type_ids: list of DPRNatureOfBusiness ids

    Kept as a helper so the same shape can be reused if we ever want to
    retrieve for a hypothetical (not-yet-saved) project.
    """
    commodity_id = project.primary_commodity_id

    # Components live on DPRSectionComponents (M2M to DPRComponent). Might
    # not exist yet on very-early-draft projects — treat missing section as
    # zero components.
    component_ids: List[int] = []
    section_components = getattr(project, 'section_components', None)
    if section_components:
        component_ids = list(
            section_components.components.values_list('id', flat=True)
        )

    # Nature of business — M2M `natures` on DPRSectionNatureOfBusiness.
    # Same caveat about section possibly not existing on early drafts.
    business_type_ids: List[int] = []
    section_nob = getattr(project, 'section_nature_of_business', None)
    if section_nob:
        business_type_ids = list(
            section_nob.natures.values_list('id', flat=True)
        )

    return {
        'commodity_id': commodity_id,
        'component_ids': component_ids,
        'business_type_ids': business_type_ids,
    }


def _base_queryset(section_key: Optional[str], language: str):
    """Active-and-language-scoped queryset before dimensional filtering."""
    qs = DPRKnowledgeEntry.objects.filter(is_active=True)

    # Language: strict match, or fall back to English so a Malayalam request
    # against a mostly-English KB still returns useful content. Callers that
    # need strict monolingual behaviour can filter downstream.
    if language and language != 'en':
        qs = qs.filter(Q(language=language) | Q(language='en'))
    else:
        qs = qs.filter(language='en')

    # Section keys — JSONField list contains the section OR is empty (universal).
    # `contains=[key]` on a JSONField list matches when the list contains
    # exactly that element; `exact=[]` matches empty (universal) entries.
    if section_key:
        qs = qs.filter(
            Q(section_keys__contains=[section_key]) | Q(section_keys=[])
        )

    # Prefetch M2Ms so the specificity ranking (which counts non-empty M2Ms)
    # doesn't cause a query per entry.
    return qs.prefetch_related('commodities', 'components', 'business_types')


def _matches_dimensions(
    entry: DPRKnowledgeEntry,
    commodity_id: Optional[int],
    component_ids: List[int],
    business_type_ids: List[int],
) -> bool:
    """Per-entry test: entry matches iff each dimension is empty OR overlaps.

    Uses the prefetched M2M caches — no DB access inside this function.
    """
    entry_commodities = {c.id for c in entry.commodities.all()}
    if entry_commodities and (commodity_id is None or commodity_id not in entry_commodities):
        return False

    entry_components = {c.id for c in entry.components.all()}
    if entry_components and not (entry_components & set(component_ids)):
        return False

    entry_business = {b.id for b in entry.business_types.all()}
    if entry_business and not (entry_business & set(business_type_ids)):
        return False

    return True


def _specificity_score(entry: DPRKnowledgeEntry, section_key: Optional[str]) -> int:
    """Higher = more narrowly targeted → ranked earlier.

    Each non-empty filter dimension adds 1. A commodity-specific PoP note
    with a component filter and a section filter scores 3; a generic
    statutory rule with no filters at all scores 0.
    """
    score = 0
    if entry.commodities.all():
        score += 1
    if entry.components.all():
        score += 1
    if entry.business_types.all():
        score += 1
    if section_key and entry.section_keys:
        score += 1
    return score


def get_context_for_project(
    project: DPRProject,
    section_key: Optional[str] = None,
    language: str = 'en',
    limit: int = DEFAULT_LIMIT,
) -> List[DPRKnowledgeEntry]:
    """Return relevant KB entries for a project + section, most specific first.

    Args:
        project: The DPR project seeking narrative content.
        section_key: DPR section being generated (e.g. 'market'). Optional —
            omit to retrieve project-wide entries (e.g. for executive summary).
        language: Preferred content language ('en' or 'ml'). Falls back to
            English if the target language has no matching entries.
        limit: Maximum entries returned. Default 20 keeps prompt size sane.

    Returns:
        List of `DPRKnowledgeEntry` instances, ordered most-specific first.
        Empty list if nothing matches — callers should handle gracefully
        (narrative can still be generated, just less grounded).
    """
    ctx = _project_context(project)
    qs = _base_queryset(section_key, language)

    matches = [
        e for e in qs
        if _matches_dimensions(
            e,
            ctx['commodity_id'],
            ctx['component_ids'],
            ctx['business_type_ids'],
        )
    ]

    # Rank: specificity DESC, then newest first, then id DESC for stability.
    matches.sort(
        key=lambda e: (_specificity_score(e, section_key), e.ingested_at, e.id),
        reverse=True,
    )
    return matches[:limit]


def get_context_ids(entries: List[DPRKnowledgeEntry]) -> List[int]:
    """Extract just the IDs from a retrieval result — for traceability writes."""
    return [e.id for e in entries]


def format_for_prompt(entries: List[DPRKnowledgeEntry]) -> str:
    """Format entries as a plain-text block ready to inject into a Claude prompt.

    Each entry appears as:
        [KB #<id>] <title> — <source>
        <content>

    Callers should include the block wrapped in an XML tag so Claude knows
    it's reference material rather than user input, e.g.:
        <knowledge_base>{format_for_prompt(entries)}</knowledge_base>
    """
    if not entries:
        return '(no knowledge base entries matched — narrative will use general knowledge only)'
    lines: List[str] = []
    for e in entries:
        header = f'[KB #{e.id}] {e.title} — {e.source_name}'
        if e.source_url:
            header += f' ({e.source_url})'
        lines.append(header)
        lines.append(e.content.strip())
        lines.append('')  # blank separator
    return '\n'.join(lines).rstrip()
