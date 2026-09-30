"""
Inbox notification categories
==============================
In-app notifications carry no category column — the only "type" signal is
the event code (InAppNotification.log.template_code.code, e.g.
'claim_approved'). Codes are consistently prefixed by module, so the inbox
groups them by prefix here. A code that matches no prefix (or a legacy row
with no template link) falls into 'other'.

Adding a new notification code: if its prefix isn't listed below it shows up
under 'other' — add the prefix to the right category.
"""
from django.db.models import Q

OTHER = 'other'

# (category key, code prefixes) — list order is the tab display order.
CATEGORIES: list[tuple[str, tuple[str, ...]]] = [
    ('application',     ('application_', 'info_')),
    ('claims',          ('claim_',)),
    ('dpr',             ('dpr_',)),
    ('recommendations', ('recommendation_', 'model_')),
    ('expert',          ('expert_',)),
    ('training',        ('fpo_training_', 'training_')),
    ('marketplace',     ('inquiry_',)),
]

CATEGORY_KEYS = [key for key, _ in CATEGORIES] + [OTHER]

_CODE_FIELD = 'log__template_code__code'


def category_for_code(code: str | None) -> str:
    if code:
        for key, prefixes in CATEGORIES:
            if code.startswith(prefixes):
                return key
    return OTHER


def _prefix_q(prefixes) -> Q:
    q = Q()
    for prefix in prefixes:
        q |= Q(**{f'{_CODE_FIELD}__startswith': prefix})
    return q


def category_q(category: str) -> Q:
    """Filter on InAppNotification for one category key (caller validates the key)."""
    if category == OTHER:
        known = _prefix_q(p for _, prefixes in CATEGORIES for p in prefixes)
        return ~known | Q(**{f'{_CODE_FIELD}__isnull': True})
    return _prefix_q(dict(CATEGORIES)[category])
