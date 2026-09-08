"""
DPR §Staleness — mark AI chapters stale when their upstream data changes.

Per KAU RCD B.5: when a user edits section data that a chapter narrative
depends on, the chapter should surface an amber "Content may be stale —
regenerate?" banner. This module provides the helper called by the section
save flow (via signals — see apps/fpo/signals.py).

Design:
    `CHAPTER_UPSTREAM_SECTIONS` (in ai_content.py) maps chapter → list of
    section keys that feed it. We invert that here at import time to build
    a section_key → list of chapter reverse index for O(1) marking.

    `mark_upstream_chapters_stale(project, section_key, reason)`:
        1. Look up chapters that depend on this section
        2. For each, set is_stale=True + stale_reason (only if the chapter
           has an active version — no point staling an empty chapter)
        3. Bulk update to avoid N queries

Author: Athul Gopan (Kefi Tech Solutions)
"""
from __future__ import annotations

from typing import Iterable

from django.utils import timezone

from apps.database.models import DPRAIContent, DPRProject
from apps.database.models.dpr.ai_content import CHAPTER_UPSTREAM_SECTIONS


# Reverse index: section_key → [chapter_key, ...]
# Built once at import time. If a section feeds no chapter (e.g. a purely
# structural section) it simply won't appear as a key here — mark call is
# a no-op which is correct behaviour.
SECTION_TO_CHAPTERS: dict[str, list[str]] = {}
for _chapter, _sections in CHAPTER_UPSTREAM_SECTIONS.items():
    for _s in _sections:
        SECTION_TO_CHAPTERS.setdefault(_s, []).append(_chapter)


def mark_upstream_chapters_stale(
    project: DPRProject,
    section_key: str,
    reason: str = '',
) -> int:
    """Mark all chapters that depend on `section_key` as stale.

    Returns the number of rows updated. Only chapters with existing active
    text are marked — an empty chapter can't be "stale" (nothing to compare
    against). This avoids surprising the user with a banner on chapters
    they haven't generated yet.
    """
    chapters = SECTION_TO_CHAPTERS.get(section_key, [])
    if not chapters:
        return 0

    default_reason = reason or f'{section_key} section updated {timezone.now().date()}'
    truncated_reason = default_reason[:200]  # matches model max_length

    # Only rows that have user_edited content — an empty chapter isn't
    # actually stale (nothing has been generated to become out-of-date).
    # We can't cheaply express "user_edited != ''" in a bulk update
    # condition without .exclude — use it for clarity.
    return (
        DPRAIContent.objects
        .filter(project=project, chapter__in=chapters)
        .exclude(user_edited='')
        .update(is_stale=True, stale_reason=truncated_reason)
    )


def clear_staleness(project: DPRProject, chapters: Iterable[str] | None = None) -> int:
    """Clear the stale flag on given chapters (or all chapters of a project).

    Called from `narrative.generate_chapter()` / accept-view after a fresh
    candidate replaces the active text — but those callers already toggle
    the flag on the row directly. This helper is kept for admin recovery
    (e.g. "user has reviewed all narratives, clear all stale flags").
    """
    qs = DPRAIContent.objects.filter(project=project, is_stale=True)
    if chapters is not None:
        qs = qs.filter(chapter__in=list(chapters))
    return qs.update(is_stale=False, stale_reason='')
