"""
Chatbot answer cache (2026-10-09, approved by Athul).

Stores successful Gemini chatbot answers in Redis and replays them for
repeat questions — instant (~50ms), free, and still served during a
Gemini outage because the cache check runs BEFORE the generator.

Correctness rules (see the message API for context):
  * Key includes the user ROLE — an answer built from admin-scoped KB
    entries must never be replayed to a public user.
  * Key includes each retrieved entry's id + updated_at — editing or
    re-syncing a KB entry automatically orphans every answer built on
    its old text. No manual invalidation needed.
  * Only STANDALONE questions are cached (callers must not cache when
    the conversation has prior turns — follow-ups are context-bound).
  * The PRE-augmentation Gemini text is stored; per-user district
    contact footers are re-applied on replay by the caller's _reply().

TTL: settings.CHATBOT_ANSWER_CACHE_TTL (seconds, default 24h).
Setting it to 0 disables the cache entirely (kill switch, no deploy).
"""

import hashlib
import logging
import re
from typing import Optional

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

_WS_RE = re.compile(r'\s+')


def _ttl() -> int:
    return int(getattr(settings, 'CHATBOT_ANSWER_CACHE_TTL', 86400))


def _normalise(question: str) -> str:
    """Collapse whitespace/case and trailing punctuation so trivial
    variants ('What documents are needed??') share one key. Deliberately
    conservative — no stemming/semantics, exact wording still matters."""
    q = _WS_RE.sub(' ', (question or '').strip().lower())
    return q.rstrip('?!. ')


def make_key(question: str, role: Optional[str], lang: str, entries) -> str:
    entry_sig = ';'.join(
        f'{e.id}:{getattr(e, "updated_at", "")}'
        for e in sorted(entries, key=lambda e: e.id)
    )
    raw = '\x1f'.join([
        _normalise(question),
        role or 'public',
        lang or 'en',
        entry_sig,
    ])
    return 'chatbot:ans:' + hashlib.sha256(raw.encode('utf-8')).hexdigest()


def get_cached(question: str, role: Optional[str], lang: str, entries) -> Optional[dict]:
    """Return {'text': ..., 'model': ...} or None. Never raises."""
    if _ttl() <= 0:
        return None
    try:
        return cache.get(make_key(question, role, lang, entries))
    except Exception:  # noqa: BLE001 — cache outage must never break chat
        logger.warning('chatbot answer cache read failed', exc_info=True)
        return None


def store(question: str, role: Optional[str], lang: str, entries,
          text: str, model: str) -> None:
    """Store a successful Gemini answer. Never raises."""
    ttl = _ttl()
    if ttl <= 0 or not text:
        return
    try:
        cache.set(
            make_key(question, role, lang, entries),
            {'text': text, 'model': model},
            timeout=ttl,
        )
    except Exception:  # noqa: BLE001
        logger.warning('chatbot answer cache write failed', exc_info=True)
