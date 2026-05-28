"""
In-App Notification Backend
============================

Saves notifications to the InAppNotification table.
Frontend fetches these via GET /api/notifications/inbox/.

Config shape expected:
    {
        "max_per_user": 100,
        "auto_expire_days": 30
    }
"""

import logging
from django.utils import timezone

from .base import BaseNotificationBackend

logger = logging.getLogger(__name__)


class InAppBackend(BaseNotificationBackend):

    def send(self, recipient: str, subject: str, body: str, log) -> bool:
        from apps.database.models import InAppNotification

        max_per_user     = int(self.settings.get('max_per_user', 100))
        auto_expire_days = int(self.settings.get('auto_expire_days', 30))

        try:
            InAppNotification.objects.create(
                user  = log.user,
                log   = log,
                title = subject or body[:100],
                body  = body,
            )

            # Enforce max_per_user — delete oldest beyond the limit
            user_notifs = InAppNotification.objects.filter(
                user=log.user
            ).order_by('-created_at')

            overflow_ids = list(
                user_notifs.values_list('id', flat=True)[max_per_user:]
            )
            if overflow_ids:
                InAppNotification.objects.filter(id__in=overflow_ids).delete()

            log.status  = log.__class__.Status.SENT
            log.sent_at = timezone.now()
            log.save(update_fields=['status', 'sent_at'])

            logger.info(f"In-app notification saved for user {log.user_id}")
            return True

        except Exception as exc:
            log.status         = log.__class__.Status.FAILED
            log.failure_reason = str(exc)
            log.retry_count   += 1
            log.save(update_fields=['status', 'failure_reason', 'retry_count'])
            logger.error(f"In-app notification failed for user {log.user_id}: {exc}")
            return False
