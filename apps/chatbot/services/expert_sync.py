"""
Expert directory → chatbot knowledge base sync (2026-10-09).

Chatbot tester run (chatbot questions and answers 1.xlsx) showed every
expert-related question drawing the generic refusal — the experts live in
the DB (apps/database/models/schemes.py Expert) but, unlike FPOs /
products / zones / PoPs, were never mirrored into ChatKnowledgeEntry.

PRIVACY RULE: the Expert row carries email + phone, but those are NEVER
written into the KB — the entry instead explains how contact works
(enquiry / booking through the Experts page). The LLM cannot leak what
it is never shown, so "give me Dr X's personal mobile number" gets a
helpful redirect, not a number and not a shrug.

Mirrors the fpo_sync pattern: build/upsert/delete + full-rebuild helper;
post_save/post_delete wiring lives in apps.chatbot.signals.
"""

import logging

logger = logging.getLogger(__name__)

# Experts are browseable by FPOs and visible on the public directory, so
# the same broad audience set the FPO entries use.
DEFAULT_AUDIENCES = ['public', 'fpo_manager', 'cbbo', 'government', 'expert']
DEFAULT_DISPLAY_ORDER = 950

_HOW_TO_CONTACT = (
    'Direct phone numbers and personal email addresses of experts are not '
    'shared through this assistant. To reach an expert: open the Experts '
    'page, open their profile, and either send an enquiry (they receive it '
    'by email and respond) or book an appointment by choosing one of their '
    'available time slots. The expert is notified of every enquiry and '
    'booking request.'
)

_GENERAL_TOPIC = 'Experts — how to contact an expert & book an appointment'


def build_expert_entry(expert) -> dict | None:
    """Build the KB entry dict for one expert. None = not listable."""
    if not expert.is_active or getattr(expert, 'is_deleted', False):
        return None

    from apps.core.utils.constants import get_district_name
    district = ''
    if expert.district:
        try:
            district = get_district_name(expert.district) or expert.district
        except Exception:  # noqa: BLE001
            district = expert.district

    expertise = expert.primary_expertise
    if expert.secondary_expertise:
        expertise += f'; also {expert.secondary_expertise}'

    body = (
        f'{expert.name_en} is an expert on the KAU-FPO platform. '
        f'Designation: {expert.designation}, {expert.organisation}. '
        f'Area of expertise: {expertise}. '
        + (f'District: {district}. ' if district else '')
        + _HOW_TO_CONTACT
    )

    keywords = ' '.join(filter(None, [
        expert.name_en, expert.name_ml,
        expert.primary_expertise, expert.secondary_expertise,
        expert.designation, expert.organisation, district,
        'expert contact enquiry book appointment phone number',
    ]))

    return {
        'topic':    f'Expert: {expert.name_en} — profile & how to contact',
        'body_en':  body,
        'keywords': keywords,
    }


def upsert_expert_entry(expert) -> tuple[bool, bool]:
    """Sync one expert's chatbot entry. Returns (created, deleted)."""
    from apps.database.models import ChatKnowledgeEntry

    entry = build_expert_entry(expert)
    topic_prefix = f'Expert: {expert.name_en} — '

    if not entry:
        deleted = ChatKnowledgeEntry.objects.filter(
            topic__startswith=topic_prefix,
        ).delete()[0]
        return (False, bool(deleted))

    _obj, was_new = ChatKnowledgeEntry.objects.update_or_create(
        topic=entry['topic'],
        defaults={
            'body_en':       entry['body_en'],
            'keywords':      entry['keywords'],
            'audiences':     DEFAULT_AUDIENCES,
            'pages':         [],
            'is_active':     True,
            'display_order': DEFAULT_DISPLAY_ORDER,
        },
    )
    return (was_new, False)


def delete_expert_entries(expert_name: str) -> int:
    from apps.database.models import ChatKnowledgeEntry
    qs = ChatKnowledgeEntry.objects.filter(
        topic__startswith=f'Expert: {expert_name} — ',
    )
    count = qs.count()
    qs.delete()
    return count


def upsert_general_entry() -> None:
    """One curated entry answering the action-style questions the testers
    logged ('book an appointment with Dr X at 10 AM') plus the booking
    lifecycle questions on the Expert sheet."""
    from apps.database.models import ChatKnowledgeEntry

    body = (
        _HOW_TO_CONTACT + ' '
        'The assistant itself cannot create, change or cancel bookings — '
        'appointments are made on the Experts page by picking an available '
        'slot on the expert\'s calendar. A booking request starts as '
        'Pending; the expert then Confirms or Rejects it, you can Cancel '
        'it before the appointment, and after it takes place it is marked '
        'Completed. You and the expert are both notified at each step, '
        'and a reminder is sent before a confirmed appointment.'
    )
    ChatKnowledgeEntry.objects.update_or_create(
        topic=_GENERAL_TOPIC,
        defaults={
            'body_en':       body,
            'keywords':      ('expert contact enquiry book booking appointment '
                              'schedule slot pending confirmed rejected cancelled '
                              'completed reminder phone number email'),
            'audiences':     DEFAULT_AUDIENCES,
            'pages':         ['/fpo/*', '/experts*'],
            'is_active':     True,
            'display_order': DEFAULT_DISPLAY_ORDER - 1,
        },
    )


def sync_all_experts() -> dict:
    """Full rebuild — used by the seed script and the signal fallback."""
    from apps.database.models.schemes import Expert
    created = updated = skipped = 0
    experts = Expert.objects.filter(is_deleted=False)
    for expert in experts:
        c, d = upsert_expert_entry(expert)
        if c: created += 1
        elif not d: updated += 1
        else: skipped += 1
    upsert_general_entry()
    return {
        'created':  created,
        'updated':  updated,
        'skipped':  skipped,
        'total_experts_processed': experts.count(),
    }
