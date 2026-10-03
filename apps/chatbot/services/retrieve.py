"""
Retrieval: pick the top-N knowledge base entries relevant to a user's
question, scoped by their audience and boosted by their current page.

Audience filtering is a HARD filter (never leak cross-role content).
Page match is a boost (nice-to-have, but ordering still works without it).

Two-stage design:
  1. audience filter + Postgres FTS score -> shortlist
  2. optional page-glob boost re-ranks the shortlist
"""

from fnmatch import fnmatch
from typing import List, Optional

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db.models import F, Q

from apps.database.models import ChatKnowledgeEntry, AUDIENCE_PUBLIC, AUDIENCE_ALL


# Weighted search vector -- matches the GIN index defined on the model,
# so Postgres can use the index for @@ operations. Keep in sync with
# apps.database.models.chatbot.ChatKnowledgeEntry.Meta.indexes.
_SEARCH_VECTOR = (
    SearchVector('topic',    weight='A', config='english')
    + SearchVector('keywords', weight='B', config='english')
    + SearchVector('body_en',  weight='C', config='english')
)


def _audience_filter(user_role: Optional[str]) -> Q:
    """Return the queryset filter that scopes entries to this user's audience.

    Args:
        user_role: the user's Django Group name (e.g. 'fpo_manager'),
                   or None for anonymous / not-logged-in users.

    Rules:
        - Anonymous  -> only 'public' entries.
        - Logged in  -> 'all' entries + entries tagged with the user's role.
                        NOT 'public' entries -- those are aimed at the
                        landing/marketing surface, not the portal.
    """
    if not user_role:
        return Q(audiences__contains=[AUDIENCE_PUBLIC])
    return Q(audiences__contains=[AUDIENCE_ALL]) | Q(audiences__contains=[user_role])


def _has_malayalam(text: str) -> bool:
    """True if the string contains any Malayalam Unicode codepoints."""
    return any('ഀ' <= c <= 'ൿ' for c in text)


def retrieve(
    query: str,
    user_role: Optional[str] = None,
    current_path: Optional[str] = None,
    limit: int = 3,
) -> List[ChatKnowledgeEntry]:
    """Retrieve the top-`limit` KB entries for a user's question.

    Args:
        query:        the user's question.
        user_role:    Django Group name or None.
        current_path: current FE route (e.g. '/fpo/dashboard'). Used only
                      for boost, not as a filter -- entries that don't
                      declare pages are still eligible.
        limit:        how many entries to return.

    Returns a list of ChatKnowledgeEntry (not a queryset). The caller
    concatenates them for the QA model's context.
    """
    if not query or not query.strip():
        return []

    # Postgres text search needs a config matching the query language. The
    # English parser stems/lower-cases/removes English stopwords — it does
    # the wrong thing with Malayalam text and often matches on accidental
    # fragments ('ha', 'ki', ...) returning irrelevant generic entries
    # (KAU #4 QA bug — Malayalam queries got "Public market hub", "What
    # is KAU-FPO Platform", "Switch language"). For Malayalam queries use
    # `simple` which keeps tokens literal — most of the KB is English so
    # we'll usually return an empty list → fallback refusal fires, which
    # is a correct failure, not a confusing one.
    config = 'simple' if _has_malayalam(query) else 'english'
    ts_query = SearchQuery(query, config=config, search_type='websearch')
    vector = _SEARCH_VECTOR if config == 'english' else (
        SearchVector('topic',    weight='A', config='simple')
        + SearchVector('keywords', weight='B', config='simple')
        + SearchVector('body_en',  weight='C', config='simple')
    )

    qs = (
        ChatKnowledgeEntry.objects
        .filter(is_active=True, is_deleted=False)
        .filter(_audience_filter(user_role))
        .annotate(rank=SearchRank(vector, ts_query))
        # NB: we oversample here (3x) then re-rank client-side by page match.
        # Cheap because the FTS index makes the shortlist fast.
        .filter(rank__gt=0.0)
        .order_by('-rank', 'display_order')[: limit * 3]
    )

    entries = list(qs)

    if current_path:
        def _matches_page(entry: ChatKnowledgeEntry) -> bool:
            pages = entry.pages or []
            return any(fnmatch(current_path, pat) for pat in pages)

        # Stable re-sort: entries matching the current page float to the top,
        # preserving FTS-rank order within each group.
        entries.sort(key=lambda e: (0 if _matches_page(e) else 1,))

    return entries[:limit]
