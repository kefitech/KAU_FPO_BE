"""
Chatbot — canned small-talk / greeting handler.

Very short messages ("hi", "hello", "thanks", "help", "who are you", etc.)
don't need Gemini or a full RAG retrieval — they just need a friendly,
role-aware reply. Handling them here avoids:
  1. Wasted API tokens (greetings would burn budget)
  2. The "no KB entries found" fallback that today reads as a robotic
     "I couldn't find an answer" for a simple hello
  3. Latency — canned responses are instant

Contract:
    handle_small_talk(message, user_role, lang) -> str | None
    Returns None when the message ISN'T small-talk → caller runs the full
    RAG + Gemini path. Returns the canned reply text otherwise.

Adding a new pattern: append to _PATTERNS below. Keep keywords lowercase.
Adding a new role or greeting locale: add to _ROLE_GREETING and _LOCALE
maps.

Author: Athul Gopan (Kefi Tech Solutions)
"""
from __future__ import annotations

import re
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Patterns — checked in order. First match wins. Keywords are lowercase.
# The regex flags: word-boundaries so 'hi' matches 'hi' and 'hi there' but
# NOT 'high yields' or 'this'. Same idea for the others.
# ─────────────────────────────────────────────────────────────────────────────

_PATTERNS: list[tuple[str, re.Pattern]] = [
    # Greetings
    ('greeting', re.compile(
        r'^\s*(hi|hello|hey|hola|namaste|namaskaram|good\s+(morning|afternoon|evening|day))'
        r'[\s.!?]*$',
        re.IGNORECASE,
    )),
    # Malayalam greetings — nested to keep pattern list flat.
    ('greeting', re.compile(r'^\s*(ഹായ്|നമസ്കാരം|ഹലോ|സുപ്രഭാതം)[\s.!?]*$')),

    # Thanks
    ('thanks', re.compile(
        r'^\s*(thanks|thank\s+you|thx|ty|got\s+it|ok\s+thanks|okay\s+thanks)'
        r'[\s.!?]*$',
        re.IGNORECASE,
    )),
    ('thanks', re.compile(r'^\s*(നന്ദി|ശരി)[\s.!?]*$')),

    # Who are you / capability
    ('what_are_you', re.compile(
        r'\b(who|what)\s+(are\s+you|is\s+this|can\s+you\s+do|do\s+you\s+do)\b',
        re.IGNORECASE,
    )),

    # Broad help ask — "help", "help me"
    ('help', re.compile(r'^\s*(help(\s+me)?|need\s+help)[\s.!?]*$', re.IGNORECASE)),
]


# ─────────────────────────────────────────────────────────────────────────────
# Reply templates — per (intent, role, lang). Falls back to the 'public'
# copy when a role-specific one isn't defined.
# ─────────────────────────────────────────────────────────────────────────────

# Format: replies[intent][lang][role] = reply text
# Role 'default' catches any role without a specific entry.
_REPLIES: dict[str, dict[str, dict[str, str]]] = {
    'greeting': {
        'en': {
            'public':      "Hi! I can help you with questions about registering your FPO, browsing products in the market hub, or contacting KAU. What would you like to know?",
            'fpo_manager': "Hi! Ask me anything about the DPR wizard, uploading documents, tier assessment, marketplace, or the page you're on.",
            'government':  "Hi! I can help with the government portal — approving FPO applications, district reports, and jurisdiction settings.",
            'cbbo':        "Hi! Ask me about your assigned FPOs, verification tasks, or training records.",
            'expert':      "Hi! I can help you with your availability, bookings, and expert profile.",
            'external_buyer': "Hi! Ask me about browsing FPO products, submitting inquiries, or verifying your buyer account.",
            'super_admin': "Hi! I can help with any admin function — user management, KB entries, AI service configuration, or any page you're on.",
            'sub_admin':   "Hi! Ask me about the sub-admin functions you've been assigned — approvals, reports, and FPO applications.",
            'default':     "Hi! How can I help you today?",
        },
        'ml': {
            'default': "നമസ്‌കാരം! ഞാൻ എങ്ങനെ സഹായിക്കാൻ കഴിയും?",
            'fpo_manager': "നമസ്‌കാരം! DPR wizard, documents, tier assessment, marketplace എന്നിവയെക്കുറിച്ച് എന്നോട് ചോദിക്കാം.",
        },
    },

    'thanks': {
        'en': {
            'default': "You're welcome! Anything else I can help with?",
        },
        'ml': {
            'default': "സ്വാഗതം! മറ്റെന്തെങ്കിലും സഹായം വേണോ?",
        },
    },

    'what_are_you': {
        'en': {
            'default':
                "I'm the KAU-FPO help assistant. I answer questions about registering your FPO, "
                "using the DPR wizard, browsing the market hub, and other platform features — "
                "grounded in the KAU knowledge base so my answers stay accurate. What would you like to know?",
        },
        'ml': {
            'default':
                "ഞാൻ KAU-FPO സഹായി ആണ്. FPO രജിസ്ട്രേഷൻ, DPR wizard, market hub, "
                "മറ്റ് പ്ലാറ്റ്ഫോം സവിശേഷതകൾ എന്നിവയെക്കുറിച്ചുള്ള ചോദ്യങ്ങൾക്ക് ഞാൻ ഉത്തരം നൽകുന്നു.",
        },
    },

    'help': {
        'en': {
            'public':      "Sure — I can help with FPO registration, buyer account verification, market hub browsing, and how to contact KAU. Just ask a question.",
            'fpo_manager': "Sure — I can help with any DPR wizard step, document upload, tier assessment, team management, marketplace, or expert booking. What's blocking you?",
            'default':     "Sure — what specifically can I help with? Try asking about a page or a task.",
        },
        'ml': {
            'default': "സഹായിക്കാം — ഏത് വിഷയത്തിലാണ് സഹായം വേണ്ടത്?",
        },
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Public entrypoint
# ─────────────────────────────────────────────────────────────────────────────

def _lookup_reply(intent: str, role: Optional[str], lang: str) -> str:
    """Get the best matching reply for (intent, role, lang) with fallbacks."""
    lang_bucket = _REPLIES[intent].get(lang) or _REPLIES[intent].get('en') or {}
    # Anonymous users (role=None) get the 'public' copy; otherwise use the
    # role-specific string. Falls back to 'default' if neither is defined.
    key = role or 'public'
    return (
        lang_bucket.get(key)
        or lang_bucket.get('default')
        or lang_bucket.get('public')
        or "Hi!"
    )


def handle_small_talk(
    message: str,
    user_role: Optional[str] = None,
    lang: str = 'en',
) -> Optional[str]:
    """Return a canned reply if `message` looks like small-talk. Else None.

    Called at the very top of the chatbot API view — before FTS retrieval
    or Gemini. Zero cost, sub-millisecond response. Keeps greetings from
    burning API budget and from producing the awkward "no KB entries
    found" fallback.
    """
    if not message:
        return None
    stripped = message.strip()
    if not stripped:
        return None

    # Cheap length filter — anything longer than "good morning everybody"
    # is very unlikely to be a bare greeting. Skip regex work altogether.
    if len(stripped) > 60:
        return None

    for intent, pattern in _PATTERNS:
        if pattern.search(stripped):
            return _lookup_reply(intent, user_role, lang)

    return None
