"""
Chatbot — Celery periodic tasks.

`purge_anonymous_conversations` — every night at 03:00 IST, remove anonymous
ChatConversations (and their messages via CASCADE) older than 30 days.
Authenticated conversations are kept until the user deletes their account,
per the retention plan in context/CHATBOT_PLAN.md.

Wire the schedule in `config/celery.py`:
    'purge-anonymous-chat-conversations': {
        'task': 'apps.chatbot.tasks.purge_anonymous_conversations',
        'schedule': crontab(hour=3, minute=0),
    },

Author: Athul Gopan (Kefi Tech Solutions)
"""
from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone


logger = logging.getLogger(__name__)

# Anonymous conversations older than this are purged nightly. Keep short —
# widget session_ids live in localStorage which is per-browser-tab-ish, so
# 30 days is generous. Auth'd users' history is exempt.
_ANON_RETENTION_DAYS = 30


@shared_task(name='apps.chatbot.tasks.purge_anonymous_conversations')
def purge_anonymous_conversations() -> int:
    """Delete anonymous ChatConversations older than the retention window.

    Returns:
        Number of conversations deleted (their messages cascade).
    """
    # Deferred import — celery beat runs this before Django's app registry
    # is guaranteed populated during autodiscovery on some deploy paths.
    from apps.database.models import ChatConversation

    cutoff = timezone.now() - timedelta(days=_ANON_RETENTION_DAYS)
    qs = ChatConversation.objects.filter(user__isnull=True, started_at__lt=cutoff)
    count = qs.count()
    if count:
        qs.delete()
        logger.info('chatbot retention: purged %d anonymous conversations older than %d days',
                    count, _ANON_RETENTION_DAYS)
    return count
