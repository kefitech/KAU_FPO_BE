"""
SMS Notification Backend
========================

Sends SMS via MSG91 API.
Credentials are read from NotificationChannelSettings (decrypted config).

Config shape expected:
    {
        "api_key": "<auth_key>",
        "sender_id": "KAUINF",
        "base_url": "https://api.msg91.com/api/v5/"
    }

DLT template IDs are stored per NotificationTemplate row (sms_dlt_template_id field).
Every SMS template must have a TRAI-approved DLT template ID for delivery in India.
"""

import re
import logging
import requests
from django.utils import timezone

from .base import BaseNotificationBackend

logger = logging.getLogger(__name__)

_OTP_RE = re.compile(r'\b(\d{4,8})\b')


class SMSBackend(BaseNotificationBackend):

    def send(self, recipient: str, subject: str, body: str, log) -> bool:
        api_key   = self.settings.get('api_key', '')
        sender_id = self.settings.get('sender_id', 'KAUINF')
        base_url  = self.settings.get('base_url', 'https://api.msg91.com/api/v5/')

        # Resolve DLT template ID from the per-template field
        dlt_template_id = self._get_dlt_template_id(log)

        # Normalize phone — ensure 91 prefix (no + for MSG91 API)
        phone = recipient.strip().lstrip('+').lstrip('0')
        if not phone.startswith('91'):
            phone = f"91{phone}"

        headers = {'authkey': api_key, 'content-type': 'application/json'}

        try:
            otp_match = _OTP_RE.search(body)
            if otp_match:
                logger.warning(f"\n{'='*50}\n[DEV] SMS OTP → {phone}\n[DEV] OTP CODE: {otp_match.group(1)}\n{'='*50}")
                params = {'mobile': phone, 'otp': otp_match.group(1)}
                if dlt_template_id:
                    params['template_id'] = dlt_template_id
                response = requests.post(
                    f"{base_url}otp",
                    params=params,
                    headers=headers,
                    timeout=10,
                )
            else:
                # MSG91 flow API — DLT template ID passed in sms body object
                sms_payload = {'message': body, 'to': [phone]}
                if dlt_template_id:
                    sms_payload['dlt_te_id'] = dlt_template_id
                response = requests.post(
                    f"{base_url}flow/",
                    json={
                        'sender':  sender_id,
                        'route':   '4',
                        'country': '91',
                        'sms':     [sms_payload],
                    },
                    headers=headers,
                    timeout=10,
                )

            response.raise_for_status()
            data = response.json()

            if data.get('type') == 'success':
                log.status  = log.__class__.Status.SENT
                log.sent_at = timezone.now()
                log.save(update_fields=['status', 'sent_at'])
                logger.info(f"SMS sent to {phone}")
                return True
            else:
                raise ValueError(data.get('message', 'Unknown SMS error'))

        except Exception as exc:
            log.status         = log.__class__.Status.FAILED
            log.failure_reason = str(exc)
            log.retry_count   += 1
            log.save(update_fields=['status', 'failure_reason', 'retry_count'])
            logger.error(f"SMS failed to {phone}: {exc}")
            return False

    def _get_dlt_template_id(self, log) -> str:
        """Look up DLT template ID from the NotificationTemplate row for this log."""
        try:
            if log.template_code and log.language:
                tmpl = log.template_code.templates.filter(
                    language=log.language, is_active=True
                ).first()
                if tmpl and tmpl.sms_dlt_template_id:
                    return tmpl.sms_dlt_template_id
        except Exception:
            pass
        return ''
