"""
District-aware fallback contacts for the chatbot — KAU suggestion #2.

When the chatbot can't answer (no KB match, or Gemini's refusal template
fires), we append a short footer directing the user to:

  1. The KVK of their district (KVKLink row with matching district code).
  2. The name of any active sub-admin(s) covering their district.

If we can't determine a district (anonymous public user with no hint),
we skip the district-specific block and keep the generic KAU support line.
"""

import re

from apps.core.utils.constants import get_district_name


# Text that we consider a "refusal / can't help" reply. We match on any of
# these phrases so the augmentation still triggers whether Gemini or the
# extractive fallback produced the reply. Case-insensitive.
_REFUSAL_MARKERS = (
    "that's not something i can help",
    "i couldn't find an answer",
    "please rephrase",
    'de@kau.in',
    'kau സപ്പോർട്ട്',
    'സഹായിക്കാൻ കഴിയാത്ത',
)


def _looks_like_refusal(text: str) -> bool:
    if not text:
        return False
    lower = text.lower()
    return any(marker in lower for marker in _REFUSAL_MARKERS)


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
    if govt and getattr(govt, 'assigned_district', ''):
        return govt.assigned_district

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


def augment_reply(reply_text: str, user, hint: str, lang: str) -> str:
    """If `reply_text` looks like a refusal, append the district footer."""
    if not _looks_like_refusal(reply_text):
        return reply_text
    district = _user_district(user, hint=hint)
    if not district:
        return reply_text
    footer = build_footer(district, lang)
    if not footer:
        return reply_text
    # Preserve one blank line between the original reply and the footer.
    return f'{reply_text.rstrip()}\n\n{footer}'
