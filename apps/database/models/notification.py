"""
Notification System Models
==========================

Three tables:
- NotificationChannelSettings : credentials + config per channel (email, sms, in_app, etc.)
- NotificationLog             : audit trail for every notification sent
- InAppNotification           : user inbox (only for in_app channel)

Architecture:
    send_notification() → dispatcher → channel backend → NotificationLog
                                                       → InAppNotification (in_app only)

Adding a new channel (WhatsApp, Push etc.) = add a row in NotificationChannelSettings.
No model changes needed.

Author: Athul Gopan (Kefi Tech Solutions)
Created: 07-05-2026
"""

from django.db import models
from django.conf import settings

from apps.core.models.base import TimeStampedModel
from .language import NotificationTemplateCode, Language


class NotificationChannelSettings(TimeStampedModel):
    """
    Credentials and configuration for each notification channel.

    One row per channel. Admin configures via admin panel.
    The `config` JSONField holds channel-specific settings — each channel
    has a different shape (see examples below).

    Email config shape:
        {
            "host": "smtp.gmail.com",
            "port": 587,
            "username": "noreply@kau.in",
            "password": "<encrypted>",
            "from_email": "noreply@kau.in",
            "from_name": "KAU-FPO Platform",
            "use_tls": true
        }

    SMS (MSG91) config shape:
        {
            "api_key": "<encrypted>",
            "sender_id": "KAUFPO",
            "base_url": "https://api.msg91.com/api/v5/"
        }

    In-App config shape:
        {
            "max_per_user": 100,
            "auto_expire_days": 30
        }

    WhatsApp (future) config shape:
        {
            "api_key": "<encrypted>",
            "phone_number_id": "...",
            "business_account_id": "..."
        }
    """

    class Channel(models.TextChoices):
        EMAIL    = 'email',    'Email'
        SMS      = 'sms',      'SMS'
        IN_APP   = 'in_app',   'In-App Notification'
        PUSH     = 'push',     'Push Notification'
        WHATSAPP = 'whatsapp', 'WhatsApp'

    channel = models.CharField(
        max_length=20,
        unique=True,
        choices=Channel.choices,
        help_text="Notification channel this config applies to"
    )

    is_active = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Enable or disable this channel globally"
    )

    config = models.JSONField(
        default=dict,
        help_text="Channel-specific settings. Sensitive fields (passwords, API keys) are AES-encrypted before storage."
    )

    class Meta:
        db_table = 'notification_channel_settings'
        verbose_name = 'Notification Channel Setting'
        verbose_name_plural = 'Notification Channel Settings'

    def __str__(self):
        status = 'active' if self.is_active else 'inactive'
        return f"{self.get_channel_display()} ({status})"

    def get_config_value(self, key, default=None):
        """Safe getter for config values."""
        return self.config.get(key, default)


class NotificationLog(TimeStampedModel):
    """
    Audit trail for every notification dispatched by the system.

    Every send attempt (success or failure) is recorded here.
    Failed notifications can be retried via Celery.

    This table is the single source of truth for:
    - What was sent to whom
    - When it was sent
    - Whether it succeeded
    - What the rendered content looked like
    """

    class Status(models.TextChoices):
        PENDING  = 'pending',  'Pending'
        SENT     = 'sent',     'Sent'
        FAILED   = 'failed',   'Failed'
        RETRYING = 'retrying', 'Retrying'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='notification_logs',
        help_text="Recipient user"
    )

    channel = models.CharField(
        max_length=20,
        choices=NotificationChannelSettings.Channel.choices,
        db_index=True,
        help_text="Channel used to deliver this notification"
    )

    template_code = models.ForeignKey(
        NotificationTemplateCode,
        on_delete=models.SET_NULL,
        null=True,
        related_name='logs',
        help_text="Template definition used"
    )

    language = models.ForeignKey(
        Language,
        on_delete=models.SET_NULL,
        null=True,
        related_name='notification_logs',
        help_text="Language the notification was rendered in"
    )

    # Rendered content — stored so we have a record of exactly what was sent
    rendered_subject = models.CharField(
        max_length=500,
        blank=True,
        help_text="Final rendered subject line (email only)"
    )

    rendered_body = models.TextField(
        help_text="Final rendered body after variable substitution"
    )

    # Recipient address (email address, phone number etc.)
    recipient = models.CharField(
        max_length=255,
        blank=True,
        help_text="Email address, phone number, or device token used for delivery"
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
        help_text="Delivery status"
    )

    failure_reason = models.TextField(
        blank=True,
        help_text="Error message if delivery failed"
    )

    retry_count = models.PositiveSmallIntegerField(
        default=0,
        help_text="Number of retry attempts made"
    )

    sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the notification was successfully delivered"
    )

    # Context used for rendering — stored for debugging and retry
    context = models.JSONField(
        default=dict,
        blank=True,
        help_text="Variable context used to render the template"
    )

    class Meta:
        db_table = 'notification_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'channel', 'status']),
            models.Index(fields=['status', 'retry_count']),
            models.Index(fields=['created_at']),
        ]
        verbose_name = 'Notification Log'
        verbose_name_plural = 'Notification Logs'

    def __str__(self):
        return f"{self.channel} → {self.recipient} [{self.status}] at {self.created_at:%Y-%m-%d %H:%M}"

    @property
    def can_retry(self):
        """Only failed notifications with < 3 attempts can be retried."""
        return self.status == self.Status.FAILED and self.retry_count < 3


class InAppNotification(TimeStampedModel):
    """
    User inbox for in-app notifications.

    Created by the in-app channel backend when a notification is dispatched.
    Frontend polls GET /api/notifications/inbox/ to display the bell icon count
    and notification list.

    Linked to NotificationLog for full audit trail.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='in_app_notifications',
        help_text="User who receives this notification"
    )

    log = models.OneToOneField(
        NotificationLog,
        on_delete=models.CASCADE,
        related_name='in_app_notification',
        help_text="Source notification log entry"
    )

    title = models.CharField(
        max_length=500,
        help_text="Notification title (rendered subject)"
    )

    body = models.TextField(
        help_text="Notification body (rendered content)"
    )

    is_read = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether the user has read this notification"
    )

    read_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the user read this notification"
    )

    class Meta:
        db_table = 'in_app_notifications'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read']),
            models.Index(fields=['user', 'created_at']),
        ]
        verbose_name = 'In-App Notification'
        verbose_name_plural = 'In-App Notifications'

    def __str__(self):
        status = 'read' if self.is_read else 'unread'
        return f"{self.user.username} — {self.title[:50]} [{status}]"

    def mark_as_read(self):
        """Mark notification as read."""
        if not self.is_read:
            from django.utils import timezone
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])
