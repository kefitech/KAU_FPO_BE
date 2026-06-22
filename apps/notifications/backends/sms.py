"""
SMS Notification Backend
========================

Sends SMS via MSG91 API.
Credentials are read from NotificationChannelSettings (decrypted config).

Config shape expected:
    {
        "api_key": "<auth_key>",
        "sender_id": "KAUFPO",
        "otp_template_id": "<template_id>",   # required for OTP messages
        "base_url": "https://api.msg91.com/api/v5/"
    }

# DEV NOTE (2026-05-11):
# Currently using MSG91 OTP API for development/testing purposes.
# Before going live:
#   1. Complete DLT registration (TRAI requirement for Indian SMS)
#   2. Get approved transactional template from MSG91
#   3. Switch OTP delivery to use the approved DLT template_id
#   4. Update otp_template_id in NotificationChannelSettings via API
"""

import re
import logging
import requests
from django.utils import timezone

from .base import BaseNotificationBackend

logger = logging.getLogger(__name__)

_OTP_RE = re.compile(r'\b(\d{6})\b')


class SMSBackend(BaseNotificationBackend):

    def send(self, recipient: str, subject: str, body: str, log) -> bool:
        api_key     = self.settings.get('api_key', '')
        sender_id   = self.settings.get('sender_id', 'KAUFPO')
        template_id = self.settings.get('otp_template_id', '')
        base_url    = self.settings.get('base_url', 'https://api.msg91.com/api/v5/')

        # Normalize phone — ensure 91 prefix (no + for MSG91 OTP API)
        phone = recipient.strip().lstrip('+').lstrip('0')
        if not phone.startswith('91'):
            phone = f"91{phone}"

        headers = {'authkey': api_key, 'content-type': 'application/json'}

        try:
            otp_match = _OTP_RE.search(body)
            if otp_match:
                print(f"\n{'='*50}")
                print(f"[DEV] SMS OTP → {phone}")
                print(f"[DEV] OTP: {otp_match.group(1)}")
                print(f"{'='*50}\n")
                # MSG91 OTP API — params sent as query string (MSG91 requirement)
                params = {'mobile': phone, 'otp': otp_match.group(1)}
                if template_id:
                    params['template_id'] = template_id
                response = requests.post(
                    f"{base_url}otp",
                    params=params,
                    headers=headers,
                    timeout=10,
                )
            else:
                # MSG91 flow/transactional API — for non-OTP messages
                response = requests.post(
                    f"{base_url}flow/",
                    json={
                        'sender':  sender_id,
                        'route':   '4',
                        'country': '91',
                        'sms': [{'message': body, 'to': [phone]}],
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
