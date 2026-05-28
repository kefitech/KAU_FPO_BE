"""
Email Notification Backend
==========================

Sends emails via SMTP or AWS SES.
Credentials are read from NotificationChannelSettings (decrypted config).

Config shape expected:
    {
        "host": "smtp.gmail.com",
        "port": 587,
        "username": "noreply@kau.in",
        "password": "<decrypted>",
        "from_email": "noreply@kau.in",
        "from_name": "KAU-FPO Platform",
        "use_tls": true
    }
"""

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
        host       = self.settings.get('host', '')
        port       = int(self.settings.get('port', 587))
        username   = self.settings.get('username', '')
        password   = self.settings.get('password', '')
        from_name  = self.settings.get('from_name', 'KAU-FPO Platform')
        from_email = self.settings.get('from_email', username)
        use_tls    = self.settings.get('use_tls', True)

        try:
            # Extract optional button context stored at dispatch time
            ctx          = log.context or {}
            button_link  = ctx.get('button_link', '')
            button_text  = ctx.get('button_text', 'Open')

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

            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From']    = f"{from_name} <{from_email}>"
            msg['To']      = recipient

            # Plain text fallback (strips HTML tags crudely — good enough for clients that need it)
            msg.attach(MIMEText(body, 'plain', 'utf-8'))
            msg.attach(MIMEText(html_body, 'html', 'utf-8'))

            if use_tls:
                server = smtplib.SMTP(host, port)
                server.starttls()
            else:
                server = smtplib.SMTP_SSL(host, port)

            server.login(username, password)
            server.sendmail(from_email, [recipient], msg.as_string())
            server.quit()

            log.status  = log.__class__.Status.SENT
            log.sent_at = timezone.now()
            log.save(update_fields=['status', 'sent_at'])

            logger.info(f"Email sent to {recipient} | subject: {subject[:60]}")
            return True

        except Exception as exc:
            log.status         = log.__class__.Status.FAILED
            log.failure_reason = str(exc)
            log.retry_count   += 1
            log.save(update_fields=['status', 'failure_reason', 'retry_count'])

            logger.error(f"Email failed to {recipient}: {exc}")
            return False
