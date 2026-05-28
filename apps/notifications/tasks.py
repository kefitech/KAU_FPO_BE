"""
Notification Celery Tasks
=========================

Async delivery tasks. The dispatcher creates a NotificationLog entry
(status=pending) and queues this task. The task handles actual delivery
and updates the log status to sent/failed.

Retry logic: max 3 attempts, exponential backoff (2m, 10m, 30m).
"""

import logging
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=120,  # 2 minutes
    name='notifications.deliver',
)
def deliver_notification(self, log_id: int, channel_settings_id: int):
    """
    Deliver a pending notification.

    Args:
        log_id              : NotificationLog.id
        channel_settings_id : NotificationChannelSettings.id (for config)
    """
    from apps.database.models import NotificationLog, NotificationChannelSettings
    from .services import _get_backend
    from .utils import decrypt_config

    try:
        log = NotificationLog.objects.select_related(
            'user', 'template_code', 'language'
        ).get(pk=log_id)
    except NotificationLog.DoesNotExist:
        logger.error(f"NotificationLog {log_id} not found — skipping.")
        return

    if log.status == NotificationLog.Status.SENT:
        return  # Already delivered (duplicate task fire)

    try:
        channel_settings = NotificationChannelSettings.objects.get(pk=channel_settings_id)
    except NotificationChannelSettings.DoesNotExist:
        log.status         = NotificationLog.Status.FAILED
        log.failure_reason = f"Channel settings {channel_settings_id} not found"
        log.save(update_fields=['status', 'failure_reason'])
        return

    # Decrypt sensitive config values before passing to backend
    config = decrypt_config(channel_settings.config)

    log.status = NotificationLog.Status.RETRYING if log.retry_count > 0 else log.status
    log.save(update_fields=['status'])

    backend = _get_backend(log.channel, config)
    success = backend.send(
        recipient = log.recipient,
        subject   = log.rendered_subject,
        body      = log.rendered_body,
        log       = log,
    )

    if not success and log.can_retry:
        # Exponential backoff: 2min → 10min → 30min
        delays = [120, 600, 1800]
        delay  = delays[min(log.retry_count - 1, len(delays) - 1)]
        raise self.retry(countdown=delay)


@shared_task(name='notifications.retry_failed')
def retry_failed_notifications():
    """
    Periodic task — retries all failed notifications that still have attempts left.
    Run via Celery Beat every 30 minutes.
    """
    from apps.database.models import NotificationLog, NotificationChannelSettings

    failed = NotificationLog.objects.filter(
        status=NotificationLog.Status.FAILED,
        retry_count__lt=3,
    ).select_related('template_code')

    count = 0
    for log in failed:
        try:
            channel_settings = NotificationChannelSettings.objects.get(
                channel=log.channel, is_active=True
            )
            deliver_notification.delay(log.id, channel_settings.id)
            count += 1
        except NotificationChannelSettings.DoesNotExist:
            continue

    logger.info(f"Queued {count} failed notifications for retry")
    return count
