"""
WhatsApp Business API Backend
=============================

Sends WhatsApp messages via Meta Graph API using pre-approved message templates.

Config shape (stored encrypted in NotificationChannelSettings):
    {
        "phone_number_id": "...",
        "access_token":    "...",   # AES-encrypted (token is in sensitive fields list)
        "api_version":     "v19.0"
    }

Recipient is the user's phone number from user.profile.phone (same as SMS channel).

WhatsApp Business API only supports pre-approved Meta templates — free-form text
is not allowed for business-initiated conversations. Each NotificationTemplate for
the whatsapp channel must have whatsapp_template_name and whatsapp_template_language
set (visible and required in Swagger / POST /api/notifications/templates/).

Variable mapping: context dict values (excluding internal _wa_ keys) are sent as
indexed body parameters in insertion order. Admin must ensure this matches the
parameter order in the Meta-approved template.

NOTE: Meta verification, business account setup, and template approval are handled
by KAU — not a dev task. Activate the channel via:
    POST /api/notifications/channel-settings/
    { "channel": "whatsapp", "is_active": true, "config": { ... } }
"""

import logging
import requests
from django.utils import timezone

from .base import BaseNotificationBackend

logger = logging.getLogger(__name__)

_META_API_URL = "https://graph.facebook.com/{api_version}/{phone_number_id}/messages"


class WhatsAppBackend(BaseNotificationBackend):

    def send(self, recipient: str, subject: str, body: str, log) -> bool:
        phone_number_id = self.settings.get('phone_number_id', '')
        access_token    = self.settings.get('access_token', '')
        api_version     = self.settings.get('api_version', 'v19.0')

        if not phone_number_id or not access_token:
            return self._fail(log, "WhatsApp config missing phone_number_id or access_token")

        # Normalize phone to E.164 without + (Meta requires digits only)
        phone = recipient.strip().lstrip('+').lstrip('0')
        if not phone.startswith('91'):
            phone = f"91{phone}"

        # Template name + language stored in log.context (injected by dispatcher)
        template_name     = log.context.get('_wa_template_name', '')
        template_language = log.context.get('_wa_template_language', 'en')

        if not template_name:
            return self._fail(log, "whatsapp_template_name not set on NotificationTemplate — cannot send")

        # Body parameters: all context values except internal _wa_ keys, in insertion order
        parameters = [
            {'type': 'text', 'text': str(v)}
            for k, v in log.context.items()
            if not k.startswith('_wa_')
        ]

        payload = {
            'messaging_product': 'whatsapp',
            'to':   phone,
            'type': 'template',
            'template': {
                'name':     template_name,
                'language': {'code': template_language},
                'components': [
                    {'type': 'body', 'parameters': parameters}
                ] if parameters else [],
            },
        }

        url = _META_API_URL.format(
            api_version=api_version,
            phone_number_id=phone_number_id,
        )

        try:
            response = requests.post(
                url,
                json=payload,
                headers={
                    'Authorization': f"Bearer {access_token}",
                    'Content-Type':  'application/json',
                },
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()

            if data.get('messages'):
                log.status  = log.__class__.Status.SENT
                log.sent_at = timezone.now()
                log.save(update_fields=['status', 'sent_at'])
                logger.info(f"WhatsApp sent to {phone} (id={data['messages'][0].get('id')})")
                return True
            else:
                raise ValueError(f"Unexpected Meta response: {data}")

        except Exception as exc:
            self._fail(log, str(exc))
            logger.error(f"WhatsApp failed to {phone}: {exc}")
            return False

    def _fail(self, log, reason: str) -> bool:
        log.status         = log.__class__.Status.FAILED
        log.failure_reason = reason
        log.retry_count   += 1
        log.save(update_fields=['status', 'failure_reason', 'retry_count'])
        logger.error(f"WhatsApp: {reason}")
        return False
