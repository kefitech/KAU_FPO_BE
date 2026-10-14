"""
Webmail links
=============
A notification can open the recipient's email inbox in a new tab instead of an
in-app page — e.g. an expert's enquiry notice, whose full message (and the FPO's
reply-to address) is in their email. webmail_url() builds that link; the inbox
API passes through only https links to WEBMAIL_HOSTS (see notification_link).
"""

from urllib.parse import urlencode

GMAIL   = 'https://mail.google.com/mail/'
OUTLOOK = 'https://outlook.live.com/mail/'
YAHOO   = 'https://mail.yahoo.com/'

_WEBMAIL_BY_DOMAIN = {
    'gmail.com':      GMAIL,
    'googlemail.com': GMAIL,
    'outlook.com':    OUTLOOK,
    'hotmail.com':    OUTLOOK,
    'live.com':       OUTLOOK,
    'msn.com':        OUTLOOK,
    'yahoo.com':      YAHOO,
    'yahoo.co.in':    YAHOO,
    'ymail.com':      YAHOO,
}

WEBMAIL_HOSTS = {'mail.google.com', 'outlook.live.com', 'mail.yahoo.com'}


def webmail_url(email: str) -> str:
    """
    Home page of the webmail for `email`. Other domains (e.g. an organisation's
    own) fall back to Gmail; `authuser` picks that account when the browser is
    signed in to several Google accounts.
    """
    domain = email.rsplit('@', 1)[-1].lower() if email else ''
    base = _WEBMAIL_BY_DOMAIN.get(domain, GMAIL)
    if base == GMAIL and email:
        return f'{GMAIL}?{urlencode({"authuser": email})}'
    return base
