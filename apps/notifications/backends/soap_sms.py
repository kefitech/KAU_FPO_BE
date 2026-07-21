"""
SMS Notification Backend — KAU Gateway (HTTP GET)
==================================================

Sends SMS via KAU SMS Gateway using HTTP GET.
Credentials are read from NotificationChannelSettings (decrypted config).

Config shape expected:
    {
        "url":         "http://finance.kau.in/services/Utility.asmx",
        "application": "KAUINF",
        "token":       "<encrypted>"
    }

DLT template IDs are stored per NotificationTemplate row (sms_dlt_template_id field).
Every SMS template must have a TRAI-approved DLT template ID for delivery in India.
"""

import logging
import requests
from django.utils import timezone

from .base import BaseNotificationBackend

logger = logging.getLogger(__name__)


class SoapSMSBackend(BaseNotificationBackend):

    def send(self, recipient: str, subject: str, body: str, log) -> bool:
        base_url    = self.settings.get('url', 'http://finance.kau.in/services/Utility.asmx')
        application = self.settings.get('application', 'KAUINF')
        token       = self.settings.get('token', '')

        dlt_template_id = self._get_dlt_template_id(log)

        # Normalize phone — gateway expects 10-digit number (no country code)
        mobile = recipient.strip().lstrip('+').lstrip('0')
        if mobile.startswith('91') and len(mobile) == 12:
            mobile = mobile[2:]

        url = f"{base_url.rstrip('/')}/SendSms"
        params = {
            'Application': application,
            'Token':       token,
            'MobileNo':    mobile,
            'Message':     body,
            'TemplateID':  dlt_template_id,
        }

        logger.debug(f"[SMS] Sending to {mobile} via KAU gateway")

        try:
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()

            resp_text = response.text
            logger.debug(f"[SMS] Gateway response: {resp_text[:200]}")

            # Gateway returns XML like: <string>402,MsgID = ...</string> on success
            # or error text on failure
            if 'error' in resp_text.lower() or 'invalid' in resp_text.lower() or 'fail' in resp_text.lower():
                raise ValueError(f"Gateway returned failure: {resp_text[:200]}")

            log.status  = log.__class__.Status.SENT
            log.sent_at = timezone.now()
            log.save(update_fields=['status', 'sent_at'])
            logger.info(f"SMS sent to {mobile}")
            return True

        except Exception as exc:
            log.status         = log.__class__.Status.FAILED
            log.failure_reason = str(exc)
            log.retry_count   += 1
            log.save(update_fields=['status', 'failure_reason', 'retry_count'])
            logger.error(f"SMS failed to {mobile}: {exc}")
            return False

    def _get_dlt_template_id(self, log) -> str:
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
