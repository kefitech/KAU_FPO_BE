"""
Email Notification Backend
==========================

Sends emails via Gmail OAuth 2.0 (preferred) or SMTP (fallback).
Credentials are read from NotificationChannelSettings (decrypted config).

Gmail OAuth config shape:
    {
        "client_id": "...",
        "client_secret": "<encrypted>",
        "refresh_token": "<encrypted>",
        "from_email": "noreply.kfl@kau.in",
        "from_name": "KAU-FPO Platform"
    }

SMTP config shape (fallback):
    {
        "host": "smtp.gmail.com",
        "port": 587,
        "username": "noreply@kau.in",
        "password": "<encrypted>",
        "from_email": "noreply@kau.in",
        "from_name": "KAU-FPO Platform",
        "use_tls": true
    }
"""

import base64
import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone

from .base import BaseNotificationBackend

logger = logging.getLogger(__name__)


class EmailBackend(BaseNotificationBackend):

    def send(self, recipient: str, subject: str, body: str, log) -> bool:
        try:
            ctx         = log.context or {}
            button_link = ctx.get('button_link', '')
            button_text = ctx.get('button_text', 'Open')

            html_body = render_to_string('email/base.html', {
                'subject':         subject,
                'content':         body,
                'button_link':     button_link,
                'button_text':     button_text,
                'company_name':    getattr(settings, 'EMAIL_COMPANY_NAME',    'KAU-FPO Platform'),
                'company_address': getattr(settings, 'EMAIL_COMPANY_ADDRESS', 'Kerala Agricultural University, Thrissur'),
                'primary_color':   getattr(settings, 'EMAIL_PRIMARY_COLOR',   '#2e7d32'),
                'year':            datetime.now().year,
            })

            if self.settings.get('refresh_token'):
                success = self._send_via_gmail_oauth(recipient, subject, body, html_body)
            else:
                success = self._send_via_smtp(recipient, subject, body, html_body)

            if success:
                log.status  = log.__class__.Status.SENT
                log.sent_at = timezone.now()
                log.save(update_fields=['status', 'sent_at'])
                logger.info(f"Email sent to {recipient} | subject: {subject[:60]}")
            else:
                raise Exception("Send returned False")

            return True

        except Exception as exc:
            log.status         = log.__class__.Status.FAILED
            log.failure_reason = str(exc)
            log.retry_count   += 1
            log.save(update_fields=['status', 'failure_reason', 'retry_count'])
            logger.error(f"Email failed to {recipient}: {exc}")
            return False

    def _send_via_gmail_oauth(self, recipient, subject, plain_body, html_body) -> bool:
        import requests as http
        from googleapiclient.discovery import build
        from google.oauth2.credentials import Credentials

        client_id     = self.settings.get('client_id', '')
        client_secret = self.settings.get('client_secret', '')
        refresh_token = self.settings.get('refresh_token', '')
        from_name     = self.settings.get('from_name', 'KAU-FPO Platform')
        from_email    = self.settings.get('from_email', '')

        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=client_id,
            client_secret=client_secret,
        )

        # Refresh to get a valid access token
        import google.auth.transport.requests
        creds.refresh(google.auth.transport.requests.Request())

        service = build('gmail', 'v1', credentials=creds, cache_discovery=False)

        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From']    = f"{from_name} <{from_email}>"
        msg['To']      = recipient
        msg.attach(MIMEText(plain_body, 'plain', 'utf-8'))
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(userId='me', body={'raw': raw}).execute()
        return True

    def _send_via_smtp(self, recipient, subject, plain_body, html_body) -> bool:
        host       = self.settings.get('host', '')
        port       = int(self.settings.get('port', 587))
        username   = self.settings.get('username', '')
        password   = self.settings.get('password', '')
        from_name  = self.settings.get('from_name', 'KAU-FPO Platform')
        from_email = self.settings.get('from_email', username)
        use_tls    = self.settings.get('use_tls', True)

        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From']    = f"{from_name} <{from_email}>"
        msg['To']      = recipient
        msg.attach(MIMEText(plain_body, 'plain', 'utf-8'))
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))

        if use_tls:
            server = smtplib.SMTP(host, port)
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(host, port)

        server.login(username, password)
        server.sendmail(from_email, [recipient], msg.as_string())
        server.quit()
        return True
