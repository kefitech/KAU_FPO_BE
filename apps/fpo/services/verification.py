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

_OTP_TTL      = 600  # 10 minutes
_MAX_SENDS    = 3    # max OTP sends per 10 min window
_MAX_ATTEMPTS = 3    # max wrong guesses before OTP is invalidated


class OTPRateLimitExceeded(Exception):
    pass


class OTPAttemptsExhausted(Exception):
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


def _check_attempts(attempts_key: str, otp_key: str, otp_ttl: int) -> int:
    """
    Increment the failed-attempt counter.
    Returns remaining attempts. Raises OTPAttemptsExhausted (and deletes OTP) when 0 remain.
    """
    attempts = cache.get(attempts_key, 0) + 1
    remaining = max(0, _MAX_ATTEMPTS - attempts)
    if remaining == 0:
        cache.delete(otp_key)
        cache.delete(attempts_key)
        raise OTPAttemptsExhausted()
    cache.set(attempts_key, attempts, otp_ttl)
    return remaining


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
    def verify_email_otp(fpo, otp: str) -> int:
        """
        Verify email OTP. Returns 0 on success.
        Returns remaining attempts (1 or 2) on wrong OTP.
        Raises OTPAttemptsExhausted when all attempts used (OTP deleted).
        """
        otp_key      = f'fpo:email_otp:{fpo.id}'
        attempts_key = f'fpo:email_otp_attempts:{fpo.id}'
        stored = cache.get(otp_key)
        if stored and stored == otp:
            cache.delete(otp_key)
            cache.delete(f'fpo:email_otp_count:{fpo.id}')
            cache.delete(attempts_key)
            fpo.email_verified = True
            fpo.save(update_fields=['email_verified'])
            return 0
        # Wrong OTP — track attempts (raises OTPAttemptsExhausted when exhausted)
        return _check_attempts(attempts_key, otp_key, _OTP_TTL)

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
    def verify_phone_otp(fpo, otp: str) -> int:
        """
        Verify phone OTP. Returns 0 on success.
        Returns remaining attempts (1 or 2) on wrong OTP.
        Raises OTPAttemptsExhausted when all attempts used (OTP deleted).
        """
        otp_key      = f'fpo:phone_otp:{fpo.id}'
        attempts_key = f'fpo:phone_otp_attempts:{fpo.id}'
        stored = cache.get(otp_key)
        if stored and stored == otp:
            cache.delete(otp_key)
            cache.delete(f'fpo:phone_otp_count:{fpo.id}')
            cache.delete(attempts_key)
            fpo.phone_verified = True
            fpo.save(update_fields=['phone_verified'])
            return 0
        return _check_attempts(attempts_key, otp_key, _OTP_TTL)
