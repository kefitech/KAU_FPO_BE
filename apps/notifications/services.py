"""
Notification Dispatcher
=======================

Single entry point for sending all notifications.

Usage anywhere in the codebase:
    from apps.notifications.services import send_notification

    send_notification(
        user    = fpo_manager,
        code    = 'fpo_approved',
        channel = 'email',
        context = {'user_name': 'Rajan', 'fpo_name': 'Kerala FPO'},
        lang    = 'ml',
    )

The dispatcher:
    1. Looks up NotificationChannelSettings (is channel active?)
    2. Looks up NotificationTemplateCode + NotificationTemplate (for lang)
    3. Renders the template with context variables
    4. Creates a NotificationLog entry (status=pending)
    5. Pushes to Celery for async delivery
    6. Celery worker calls the correct backend (email/sms/inapp)

Adding a new channel:
    - Add backend file in apps/notifications/backends/
    - Add one elif block in _get_backend() below
    - Zero other changes needed
"""

import logging
from django.contrib.auth import get_user_model

from apps.database.models import (
    NotificationChannelSettings,
    NotificationTemplateCode,
    NotificationTemplate,
    NotificationLog,
    Language,
)

logger = logging.getLogger(__name__)
User = get_user_model()


def send_notification(
    user,
    code: str,
    channel: str,
    context: dict = None,
    lang: str = 'en',
    override_recipient: str = None,
) -> NotificationLog | None:
    """
    Dispatch a notification asynchronously via Celery.

    Args:
        user               : Django User instance or user ID
        code               : NotificationTemplateCode.code (e.g. 'fpo_approved')
        channel            : Channel string — 'email', 'sms', 'in_app', 'push', 'whatsapp'
        context            : Variable substitution dict — {'user_name': 'Rajan', ...}
        lang               : Language code — 'en', 'ml', 'ta', etc.
        override_recipient : Override the to-address derived from the user profile.
                             Use when sending to fpo.office_email or fpo.office_phone
                             instead of the user's personal contact.

    Returns:
        NotificationLog instance (status=pending) or None if validation fails.
    """
    from .tasks import deliver_notification

    context = context or {}

    # Resolve user ID
    user_id = user.pk if hasattr(user, 'pk') else user

    # Validate channel is active
    try:
        channel_settings = NotificationChannelSettings.objects.get(
            channel=channel, is_active=True
        )
    except NotificationChannelSettings.DoesNotExist:
        logger.warning(f"Channel '{channel}' is not active or not configured. Skipping.")
        return None

    # Validate template code exists
    try:
        template_code = NotificationTemplateCode.objects.get(
            code=code, channel=channel, is_active=True
        )
    except NotificationTemplateCode.DoesNotExist:
        logger.warning(f"No active template code found for code='{code}' channel='{channel}'.")
        return None

    # Get template for requested language, fall back to English
    template = (
        NotificationTemplate.objects.filter(
            template_code=template_code, language__code=lang, is_active=True
        ).select_related('language').first()
        or
        NotificationTemplate.objects.filter(
            template_code=template_code, language__code='en', is_active=True
        ).select_related('language').first()
    )

    if not template:
        logger.warning(f"No template content found for code='{code}' channel='{channel}' lang='{lang}'.")
        return None

    # Render template
    rendered = template.render(context)

    # For WhatsApp: stash template name/language into context so backend can read it
    stored_context = context.copy()
    if channel == 'whatsapp':
        stored_context['_wa_template_name']     = rendered.get('whatsapp_template_name', '')
        stored_context['_wa_template_language'] = rendered.get('whatsapp_template_language', 'en')

    # Get recipient address from user (or use override for e.g. fpo.office_email)
    recipient = override_recipient or _get_recipient(user_id, channel)

    # Create log entry
    log = NotificationLog.objects.create(
        user_id         = user_id,
        channel         = channel,
        template_code   = template_code,
        language        = template.language,
        rendered_subject= rendered.get('subject', ''),
        rendered_body   = rendered['body'],
        recipient       = recipient,
        status          = NotificationLog.Status.PENDING,
        context         = stored_context,
    )

    # Dispatch to Celery
    deliver_notification.delay(log.id, channel_settings.id)

    return log


def _get_recipient(user_id: int, channel: str) -> str:
    """Extract the correct recipient address from the user based on channel."""
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return ''

    if channel == 'email':
        return user.email or ''
    elif channel in ('sms', 'whatsapp'):
        return getattr(getattr(user, 'profile', None), 'phone', '') or ''
    elif channel == 'in_app':
        return str(user_id)
    else:
        return ''


def _get_backend(channel: str, config: dict):
    """Return the correct backend instance for the channel."""
    from .backends import EmailBackend, SMSBackend, InAppBackend, WhatsAppBackend
    from .backends.soap_sms import SoapSMSBackend

    # Use SOAP SMS backend when a SOAP URL is configured, else fall back to MSG91
    if channel == 'sms' and config.get('url'):
        return SoapSMSBackend(config)

    backends = {
        'email':    EmailBackend,
        'sms':      SMSBackend,
        'in_app':   InAppBackend,
        'whatsapp': WhatsAppBackend,
    }

    backend_class = backends.get(channel)
    if not backend_class:
        raise ValueError(f"No backend registered for channel '{channel}'")

    return backend_class(config)
