"""
SMS Notification Backend — KAU SOAP Gateway
============================================

Sends SMS via KAU SMS Gateway (SOAP/ASMX service at finance.kau.in).
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

_SOAP_NAMESPACE = 'http://tempuri.org/'

_SOAP_ENVELOPE = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
               xmlns:xsd="http://www.w3.org/2001/XMLSchema"
               xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <SendSms xmlns="http://tempuri.org/">
      <Application>{application}</Application>
      <Token>{token}</Token>
      <Mobile>{mobile}</Mobile>
      <Message>{message}</Message>
      <TemplateID>{template_id}</TemplateID>
    </SendSms>
  </soap:Body>
</soap:Envelope>"""


class SoapSMSBackend(BaseNotificationBackend):

    def send(self, recipient: str, subject: str, body: str, log) -> bool:
        url         = self.settings.get('url', 'http://finance.kau.in/services/Utility.asmx')
        application = self.settings.get('application', 'KAUINF')
        token       = self.settings.get('token', '')

        dlt_template_id = self._get_dlt_template_id(log)

        # Normalize phone — gateway expects 10-digit number (no country code)
        mobile = recipient.strip().lstrip('+').lstrip('0')
        if mobile.startswith('91') and len(mobile) == 12:
            mobile = mobile[2:]

        headers = {
            'Content-Type': 'text/xml; charset=utf-8',
            'SOAPAction':   f'"{_SOAP_NAMESPACE}SendSms"',
        }

        payload = _SOAP_ENVELOPE.format(
            application=application,
            token=token,
            mobile=mobile,
            message=self._xml_escape(body),
            template_id=dlt_template_id,
        )

        logger.warning(
            "\n" + "=" * 50 +
            f"\n[DEV] SMS OTP → {mobile}"
            f"\n[DEV] MESSAGE: {body}"
            "\n" + "=" * 50
        )
        logger.debug(f"[SMS] Sending to {mobile} via KAU SOAP gateway")

        try:
            response = requests.post(url, data=payload.encode('utf-8'), headers=headers, timeout=15)
            response.raise_for_status()

            # ASMX services return XML — check for failure indicators in response
            resp_text = response.text.lower()
            if 'false' in resp_text or 'error' in resp_text or 'invalid' in resp_text:
                raise ValueError(f"Gateway returned failure: {response.text[:200]}")

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

    @staticmethod
    def _xml_escape(text: str) -> str:
        """Escape special XML characters in the SMS message body."""
        return (
            text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&apos;')
        )
