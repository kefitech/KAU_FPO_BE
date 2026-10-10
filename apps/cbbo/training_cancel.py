"""
Cancelling a training session (CBBO officer or government official)
===================================================================
A cancelled session is a soft-deleted one with a reason: the FPO portal lists
it under "Cancelled" and its members are told (in-app; email to the primary).
Both portals' cancel views call cancel_training_session().
"""
import logging

from rest_framework import serializers

logger = logging.getLogger(__name__)

CANCEL_REASON_MAX_CHARS = 300  # the cancel dialog shows the same limit
FPO_TRAININGS_LINK = '/fpo/trainings'


class CancelSessionSerializer(serializers.Serializer):
    reason = serializers.CharField(
        required=False, allow_blank=True, max_length=CANCEL_REASON_MAX_CHARS,
        error_messages={'max_length': f'Reason must be {CANCEL_REASON_MAX_CHARS} characters or fewer.'},
    )


def cancel_training_session(session, user, reason=''):
    """Soft-delete `session` as a cancellation by `user`, store the reason and notify the FPO."""
    session.cancellation_reason = (reason or '').strip()
    session.save(update_fields=['cancellation_reason'])
    session.soft_delete(user=user)
    _notify_fpo_cancelled(session, user)
    return session


def _notify_fpo_cancelled(session, cancelled_by):
    from apps.core.services.fpo_permission import fpo_notification_recipients
    from apps.notifications.services import send_notification

    fpo = session.fpo
    context = {
        'fpo_name': fpo.name,
        'topic': session.topic,
        'date': str(session.date),
        'time': session.time or 'TBD',
        'venue': session.venue or 'TBD',
        'reason': session.cancellation_reason or 'No reason given',
        'cancelled_by': cancelled_by.get_full_name() or cancelled_by.username,
        'link': FPO_TRAININGS_LINK,
    }
    for member in fpo_notification_recipients(fpo):
        try:
            send_notification(user=member, code='fpo_training_cancelled', channel='in_app', context=context)
        except Exception:
            logger.exception(f"Failed to queue cancellation in-app for user {member.pk}, session {session.pk}")
    if fpo.primary_user and fpo.primary_user.email:
        try:
            send_notification(user=fpo.primary_user, code='fpo_training_cancelled', channel='email', context=context)
        except Exception:
            logger.exception(f"Failed to queue cancellation email for session {session.pk}")
