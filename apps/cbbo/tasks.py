"""
Training session Celery tasks
=============================
- send_training_reminders: hourly; within 24 hours of a session's start it
  reminds the official who recorded it, the FPO's primary user and every
  active team member, by email and in-app, once per session.
"""
import logging
from datetime import datetime, timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)

DEFAULT_START_TIME = (9, 0)  # sessions recorded without a time count as 09:00
FPO_TRAININGS_LINK = '/fpo/trainings'
CREATOR_TRAININGS_LINK = {'government': '/government/training', 'cbbo': '/cbbo/training'}


def session_start(session):
    """Aware datetime the session starts; blank or malformed time falls back to 09:00."""
    try:
        hour, minute = map(int, (session.time or '').split(':')[:2])
    except (ValueError, AttributeError):
        hour, minute = DEFAULT_START_TIME
    return timezone.make_aware(datetime.combine(session.date, datetime.min.time().replace(hour=hour, minute=minute)))


def _send(user, context):
    from apps.notifications.services import send_notification

    for channel in ('email', 'in_app'):
        if channel == 'email' and not user.email:
            continue
        try:
            send_notification(user=user, code='fpo_training_reminder', channel=channel, context=context)
        except Exception:
            logger.exception(f"Failed to queue training reminder ({channel}) for user {user.pk}")


@shared_task(name='apps.cbbo.tasks.send_training_reminders')
def send_training_reminders():
    from apps.core.services.fpo_permission import fpo_notification_recipients
    from apps.database.models.cbbo import TrainingSession
    from apps.fpo.api.training import NO_CREATOR, creator_roles

    now = timezone.now()
    today = timezone.localdate()
    candidates = (
        TrainingSession.objects
        .filter(is_deleted=False, is_active=True, reminder_sent=False,
                date__gte=today, date__lte=today + timedelta(days=1))
        .select_related('fpo', 'fpo__primary_user', 'cbbo')
    )
    count = 0
    for session in candidates:
        start = session_start(session)
        if start - now > timedelta(hours=24):
            continue  # more than a day away — a later hourly run will catch it
        if start < now - timedelta(hours=1):
            continue  # already under way; too late to remind

        context = {
            'fpo_name': session.fpo.name,
            'topic': session.topic,
            'trainer_name': session.trainer_name or 'TBD',
            'date': str(session.date),
            'time': session.time or 'TBD',
            'venue': session.venue or 'TBD',
        }
        # The official who recorded it, linked to their own portal's page.
        role = creator_roles([session.cbbo_id]).get(session.cbbo_id, NO_CREATOR)['role']
        creator_context = dict(context)
        if role in CREATOR_TRAININGS_LINK:
            creator_context['link'] = CREATOR_TRAININGS_LINK[role]
        _send(session.cbbo, creator_context)
        # The FPO's primary user and every active team member.
        fpo_context = dict(context, link=FPO_TRAININGS_LINK)
        for member in fpo_notification_recipients(session.fpo):
            if member.pk != session.cbbo_id:
                _send(member, fpo_context)

        session.reminder_sent = True
        session.save(update_fields=['reminder_sent'])
        count += 1
    logger.info(f"Sent {count} training session reminders")
    return count
