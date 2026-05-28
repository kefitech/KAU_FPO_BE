"""
VerificationService — FPO Email + Phone OTP verification.

Handles:
    - office_email OTP (6-digit, 10 min TTL, sent via email)
    - office_phone OTP (6-digit, 10 min TTL, sent via SMS)

Redis keys:
    fpo:email_otp:{fpo_id}       → 6-digit OTP string
    fpo:email_otp_count:{fpo_id} → send count (max 3 per 10 min window)
    fpo:phone_otp:{fpo_id}       → 6-digit OTP string
    fpo:phone_otp_count:{fpo_id} → send count (max 3 per 10 min window)

Both OTPs are one-time use — deleted after successful verification.
Rate limit resets automatically when the 10 min TTL expires.
"""

import random
import string

from django.core.cache import cache

from apps.notifications.services import send_notification

_OTP_TTL   = 600  # 10 minutes
_MAX_SENDS = 3    # max OTP sends per 10 min window


class OTPRateLimitExceeded(Exception):
    pass


def _generate_otp() -> str:
    return ''.join(random.choices(string.digits, k=6))


def _check_and_increment(count_key: str) -> None:
    """
    Increment the send counter. Raise OTPRateLimitExceeded if limit reached.
    Counter TTL is set on first send and not extended on subsequent sends —
    so the window always starts from the first send in that 10-min period.
    """
    count = cache.get(count_key, 0)
    if count >= _MAX_SENDS:
        raise OTPRateLimitExceeded()
    if count == 0:
        cache.set(count_key, 1, _OTP_TTL)
    else:
        cache.incr(count_key)


class VerificationService:

    # ── Email OTP ─────────────────────────────────────────────────────────────

    @staticmethod
    def send_email_otp(fpo, lang: str = 'en') -> None:
        """
        Generate and send OTP to fpo.office_email.
        Raises OTPRateLimitExceeded if called more than 3 times in 10 minutes.
        """
        _check_and_increment(f'fpo:email_otp_count:{fpo.id}')
        otp = _generate_otp()
        cache.set(f'fpo:email_otp:{fpo.id}', otp, _OTP_TTL)
        send_notification(
            user=fpo.primary_user,
            code='fpo_email_otp',
            channel='email',
            context={
                'user_name': fpo.primary_user.get_full_name() or fpo.primary_user.username,
                'otp': otp,
            },
            lang=lang,
            override_recipient=fpo.office_email,
        )

    @staticmethod
    def verify_email_otp(fpo, otp: str) -> bool:
        """Return True and mark email verified if OTP matches. Consumes the OTP."""
        key = f'fpo:email_otp:{fpo.id}'
        stored = cache.get(key)
        if stored and stored == otp:
            cache.delete(key)
            cache.delete(f'fpo:email_otp_count:{fpo.id}')
            fpo.email_verified = True
            fpo.save(update_fields=['email_verified'])
            return True
        return False

    # ── Phone OTP ─────────────────────────────────────────────────────────────

    @staticmethod
    def send_phone_otp(fpo, lang: str = 'en') -> None:
        """
        Generate and send OTP to fpo.office_phone via SMS.
        Raises OTPRateLimitExceeded if called more than 3 times in 10 minutes.
        """
        _check_and_increment(f'fpo:phone_otp_count:{fpo.id}')
        otp = _generate_otp()
        cache.set(f'fpo:phone_otp:{fpo.id}', otp, _OTP_TTL)
        send_notification(
            user=fpo.primary_user,
            code='fpo_phone_otp',
            channel='sms',
            context={'otp': otp},
            lang=lang,
            override_recipient=fpo.office_phone,
        )

    @staticmethod
    def verify_phone_otp(fpo, otp: str) -> bool:
        """Return True and mark phone verified if OTP matches. Consumes the OTP."""
        key = f'fpo:phone_otp:{fpo.id}'
        stored = cache.get(key)
        if stored and stored == otp:
            cache.delete(key)
            cache.delete(f'fpo:phone_otp_count:{fpo.id}')
            fpo.phone_verified = True
            fpo.save(update_fields=['phone_verified'])
            return True
        return False
