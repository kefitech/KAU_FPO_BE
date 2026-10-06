"""
Fallback augmentation for the chatbot — KAU suggestion #2.

When the chatbot can't answer (no KB match, or Gemini's refusal template
fires), rewrite the generic refusal into something useful:

  1. Detect the user's INTENT from the original message (product,
     scheme, registration, expert, training, weather, ...).
  2. Replace the generic "contact KAU support" line with an intent-
     specific pointer to the platform page that actually handles it.
  3. Append a district footer (KVK + sub-admin) if we know the caller's
     district — either from their profile or an FE hint.

If we can't determine an intent OR a district, we degrade to the
original generic refusal so the reply is never worse than what Gemini
produced.
"""

from apps.core.utils.constants import get_district_name


# Single canonical refusal — used by _fallback_reply(), the Gemini prompt
# (case C), and anywhere else the chatbot has to say "I don't know". Three
# different wordings pre-fix (BUG-12) made the UX feel inconsistent.
SUPPORT_EMAIL = 'de@kau.in'

GENERIC_REFUSAL_EN = (
    "Sorry, I couldn't answer that from what I know. "
    "Please rephrase your question, or contact KAU support at "
    f"{SUPPORT_EMAIL} for help."
)
GENERIC_REFUSAL_ML = (
    "ക്ഷമിക്കണം, എനിക്കറിയാവുന്നതിൽ നിന്ന് ഉത്തരം തരാൻ കഴിഞ്ഞില്ല. "
    "ദയവായി മറ്റൊരു രീതിയിൽ ചോദിക്കുക, അല്ലെങ്കിൽ "
    f"{SUPPORT_EMAIL}-ൽ KAU സപ്പോർട്ടിനെ ബന്ധപ്പെടുക."
)


def generic_refusal(lang: str = 'en') -> str:
    return GENERIC_REFUSAL_ML if lang == 'ml' else GENERIC_REFUSAL_EN


# Text that we consider a "refusal / can't help" reply. We match on any of
# these phrases so the augmentation still triggers whether Gemini or the
# extractive fallback produced the reply. Case-insensitive.
_REFUSAL_MARKERS = (
    "that's not something i can help",
    "i couldn't find an answer",
    "i couldn't answer that",
    "please rephrase",
    SUPPORT_EMAIL,
    'kau സപ്പോർട്ട്',
    'സഹായിക്കാൻ കഴിയാത്ത',
    'ഉത്തരം തരാൻ കഴിഞ്ഞില്ല',
)


def _looks_like_refusal(text: str) -> bool:
    if not text:
        return False
    lower = text.lower()
    return any(marker in lower for marker in _REFUSAL_MARKERS)


# ─────────────────────────────────────────────────────────────────────
# Intent detection — cheap keyword match against the user's message.
# First match wins, so keep the more specific intents at the top.
# ─────────────────────────────────────────────────────────────────────

_INTENTS = [
    # Scheme first — its keywords are more specific than product's "available".
    ('scheme', {
        'keywords': (
            'scheme', 'subsidy', 'subsidies', 'grant', 'grants',
            'financial support', 'funding', 'loan',
        ),
        'en': (
            "Sorry, I couldn't find a scheme that matches. "
            "Browse the Schemes & Subsidies hub for the latest KAU-listed programs."
        ),
        'ml': (
            "ക്ഷമിക്കണം, പൊരുത്തപ്പെടുന്ന പദ്ധതി കണ്ടെത്താൻ കഴിഞ്ഞില്ല. "
            "KAU-യുടെ Schemes & Subsidies പേജിൽ പുതിയ പദ്ധതികൾ കാണാം."
        ),
    }),
    ('product', {
        'keywords': (
            # explicit product / trade terms
            'product', 'buy', 'sell', 'sale', 'sold', 'stock',
            'listing', 'listed', 'market hub', 'kg', 'quintal',
            'seller', 'buyer', 'wholesale', 'purchase',
            # buy-side idioms
            'who has', 'who sells', 'who is selling', 'anyone selling',
            'looking for', 'want to buy', 'need to buy',
            'availability', 'in stock',
        ),
        'en': (
            "Sorry, I couldn't find a matching product listing. "
            "Browse the Market Hub or the FPO Products page to see what's available right now."
        ),
        'ml': (
            "ക്ഷമിക്കണം, ഈ ഉൽപ്പന്നത്തിനുള്ള ലിസ്റ്റിംഗ് കണ്ടെത്താൻ കഴിഞ്ഞില്ല. "
            "നിലവിലുള്ള ഉൽപ്പന്നങ്ങൾ കാണാൻ Market Hub അല്ലെങ്കിൽ FPO Products പേജ് സന്ദർശിക്കുക."
        ),
    }),
    ('expert', {
        'keywords': (
            'expert', 'agronomist', 'consultant', 'advisor', 'advice',
            'specialist', 'consultation', 'book an expert',
        ),
        'en': (
            "Sorry, I couldn't find a matching expert. "
            "Search the Expert Directory to book a KAU-approved specialist."
        ),
        'ml': (
            "ക്ഷമിക്കണം, പൊരുത്തപ്പെടുന്ന വിദഗ്ധനെ കണ്ടെത്താൻ കഴിഞ്ഞില്ല. "
            "KAU-അംഗീകൃത വിദഗ്ധരെ ബുക്ക് ചെയ്യാൻ Expert Directory സന്ദർശിക്കുക."
        ),
    }),
    ('training', {
        'keywords': (
            'training', 'workshop', 'course', 'class', 'session',
            'learn', 'teach', 'lesson',
        ),
        'en': (
            "Sorry, I couldn't find a matching training. "
            "Check the Trainings page on your dashboard for upcoming CBBO/KAU sessions."
        ),
        'ml': (
            "ക്ഷമിക്കണം, പൊരുത്തപ്പെടുന്ന പരിശീലനം കണ്ടെത്താൻ കഴിഞ്ഞില്ല. "
            "വരാനിരിക്കുന്ന സെഷനുകൾക്ക് Trainings പേജ് പരിശോധിക്കുക."
        ),
    }),
    ('registration', {
        'keywords': (
            'register', 'registration', 'sign up', 'signup', 'apply',
            'application', 'join', 'onboard', 'create fpo', 'new fpo',
        ),
        'en': (
            "Sorry, I couldn't answer that from what I know. "
            "For FPO registration, use the Register FPO wizard on the platform."
        ),
        'ml': (
            "ക്ഷമിക്കണം, എനിക്കറിയാവുന്നതിൽ നിന്ന് ഉത്തരം തരാൻ കഴിഞ്ഞില്ല. "
            "FPO രജിസ്ട്രേഷനായി Register FPO wizard ഉപയോഗിക്കുക."
        ),
    }),
    ('tier', {
        'keywords': ('tier', 'assessment', 'rating', 'grade', 'upgrade tier'),
        'en': (
            "Sorry, I couldn't find an answer. "
            "Head to the Tier Assessment page on your FPO dashboard to see or take the yearly assessment."
        ),
        'ml': (
            "ക്ഷമിക്കണം, ഉത്തരം കണ്ടെത്താൻ കഴിഞ്ഞില്ല. "
            "വാർഷിക അസസ്‌മെന്റ് കാണാൻ FPO Dashboard-ലെ Tier Assessment പേജിലേക്ക് പോകുക."
        ),
    }),
    ('dpr', {
        'keywords': ('dpr', 'project report', 'detailed project report', 'business plan'),
        'en': (
            "Sorry, I couldn't answer that from KAU content. "
            "For DPR generation, open the DPR Projects page on your FPO dashboard."
        ),
        'ml': (
            "ക്ഷമിക്കണം, ഉത്തരം കണ്ടെത്താൻ കഴിഞ്ഞില്ല. "
            "DPR-നായി FPO Dashboard-ലെ DPR Projects പേജ് സന്ദർശിക്കുക."
        ),
    }),
]


def _detect_intent(message: str) -> dict | None:
    """Return the intent-info dict for the first matching intent, or None."""
    if not message:
        return None
    lower = message.lower()
    for _name, info in _INTENTS:
        if any(k in lower for k in info['keywords']):
            return info
    return None


def _rewrite_refusal_line(reply_text: str, intent_line: str) -> str:
    """Replace the whole refusal block with `intent_line`.

    Assumption: when Gemini or the extractive fallback returns a refusal,
    the ENTIRE reply is the refusal template — not one sentence of a
    longer answer. That's how our prompt is structured (case C). So it's
    safe to swap the full text for the intent line.
    """
    return intent_line.strip()


def _user_district(user, hint: str = '') -> str | None:
    """Best-effort resolution of the user's district code.

    Priority:
      1. FPO manager → their FPO.district
      2. Sub-admin   → their SubAdminDistrictAssignment.district
      3. Government / CBBO / expert profile with a district field
      4. Explicit `hint` from the FE (query param on the chat request)
    Returns None if we don't know.
    """
    if not user or not user.is_authenticated:
        return hint or None

    # 1. FPO manager
    from apps.database.models.fpo import FPO
    fpo = FPO.objects.filter(primary_user=user, is_deleted=False).only('district').first()
    if fpo and fpo.district:
        return fpo.district

    # 2. Sub-admin
    assignment = getattr(user, 'district_assignment', None)
    if assignment and assignment.district:
        return assignment.district

    # 3. Government / CBBO profiles
    govt = getattr(user, 'govt_profile', None)
    if govt and getattr(govt, 'assigned_districts', None):
        return govt.assigned_districts[0]   # first of possibly several districts

    return hint or None


def _kvk_for_district(district_code: str):
    """Return the active KVKLink row for the given district, or None."""
    from apps.database.models import KVKLink
    return (
        KVKLink.objects
        .filter(district=district_code, is_active=True, is_deleted=False)
        .first()
    )


def _sub_admin_contact(district_code: str) -> str | None:
    """Return a display-friendly string of the sub-admin(s) for the district,
    or None if nobody's assigned. Never dumps raw emails to the reply —
    just names, so we don't leak PII to random public users."""
    from django.contrib.auth.models import Group, User
    try:
        group = Group.objects.get(name='sub_admin')
    except Group.DoesNotExist:
        return None
    users = (
        User.objects
        .filter(
            groups=group, is_active=True,
            district_assignment__district=district_code,
            district_assignment__is_deleted=False,
        )
        .order_by('first_name', 'email')[:3]
    )
    names = [f'{u.first_name} {u.last_name}'.strip() or u.email for u in users]
    if not names:
        return None
    return ', '.join(names)


def build_footer(district_code: str, lang: str) -> str:
    """Build a 1–3 line footer for the given district. Never returns empty
    when a district is known — falls back to KVK-only or sub-admin-only
    if the other half is missing."""
    kvk = _kvk_for_district(district_code)
    officer = _sub_admin_contact(district_code)
    district_label = get_district_name(district_code, language=lang) or district_code

    lines = []
    if lang == 'ml':
        lines.append(f'ക്രോപ്പ് സംബന്ധിച്ച ചോദ്യങ്ങൾക്ക് {district_label} ജില്ലയിലെ വിഭവങ്ങൾ ഉപയോഗിക്കാം:')
    else:
        lines.append(f'For {district_label} district, you can also reach out to:')

    if kvk:
        bits = [f'• {kvk.name}']
        if kvk.contact_email:
            bits.append(kvk.contact_email)
        if kvk.contact_phone:
            bits.append(kvk.contact_phone)
        if kvk.url:
            bits.append(kvk.url)
        lines.append('  '.join(bits))
    if officer:
        prefix = 'KAU സബ്-അഡ്മിൻ' if lang == 'ml' else 'KAU Sub-Admin'
        lines.append(f'• {prefix}: {officer}')

    return '\n'.join(lines) if len(lines) > 1 else ''


def augment_reply(reply_text: str, user, hint: str, lang: str, user_message: str = '') -> str:
    """Rewrite a refusal reply into something actionable.

    1. If the reply doesn't look like a refusal, return unchanged.
    2. Detect the user's INTENT from `user_message` and replace the
       generic refusal sentence with an intent-specific pointer.
    3. Append the district footer (KVK + sub-admin) if a district can
       be resolved from the user's profile or `hint`.
    """
    if not _looks_like_refusal(reply_text):
        return reply_text

    result = reply_text

    # Step 1 — intent rewrite
    intent = _detect_intent(user_message)
    if intent:
        line = intent.get(lang) or intent['en']
        result = _rewrite_refusal_line(result, line)

    # Step 2 — district footer
    district = _user_district(user, hint=hint)
    if district:
        footer = build_footer(district, lang)
        if footer:
            result = f'{result.rstrip()}\n\n{footer}'

    return result
