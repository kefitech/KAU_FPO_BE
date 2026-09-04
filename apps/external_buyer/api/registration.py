"""
External Buyer Registration APIs
==================================
Endpoints:
    POST   /api/external-buyer/pre-register/send-email-otp/
    POST   /api/external-buyer/pre-register/verify-email-otp/
"""

import logging
import secrets

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email as django_validate_email

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.core.utils.responses import StandardResponse
from apps.notifications.services import send_notification


def _mask_email(email: str) -> str:
    local, _, domain = email.partition('@')
    if len(local) <= 2:
        return f'{local[0]}***@{domain}'
    return f'{local[:2]}{"*" * (len(local) - 2)}@{domain}'


class BuyerSendEmailOTPView(APIView):
    """
    POST /api/external-buyer/pre-register/send-email-otp/

    Sends a 6-digit OTP to the given email before buyer account creation.
    Rate limited: 3 sends per 10 minutes per email.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['External Buyer - Registration'],
        summary='Send email OTP for buyer pre-registration verification',
        description='Send a 6-digit OTP to an email before buyer account creation. Rate limited to 3 sends per 10 minutes.',
        request=None,
        responses={200: None, 400: None, 429: None},
    )
    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        if not email:
            return StandardResponse.error('Email is required.', status_code=status.HTTP_400_BAD_REQUEST)
        try:
            django_validate_email(email)
        except DjangoValidationError:
            return StandardResponse.error('Enter a valid email address.', status_code=status.HTTP_400_BAD_REQUEST)
        if User.objects.filter(email=email).exists():
            return StandardResponse.error('An account with this email already exists.', status_code=status.HTTP_400_BAD_REQUEST)

        count_key = f'buyer:prereg_email_otp_count:{email}'
        otp_key   = f'buyer:prereg_email_otp:{email}'
        _OTP_TTL  = 600
        _MAX_SENDS = 3

        count = cache.get(count_key, 0)
        if count >= _MAX_SENDS:
            return StandardResponse.error('Too many OTP requests. Please wait 10 minutes before trying again.', status_code=status.HTTP_429_TOO_MANY_REQUESTS)

        otp = str(secrets.randbelow(900000) + 100000)
        cache.set(otp_key, otp, _OTP_TTL)
        if count == 0:
            cache.set(count_key, 1, _OTP_TTL)
        else:
            cache.incr(count_key)

        logging.getLogger(__name__).warning(f"[DEV] Buyer email OTP for {email}: {otp}")

        try:
            send_notification(user=None, code='email_verification', channel='email', context={'otp': otp}, override_recipient=email)
        except Exception:
            pass

        return StandardResponse.success(data={'email': _mask_email(email)}, message='OTP sent to your email address.')


class BuyerVerifyEmailOTPView(APIView):
    """
    POST /api/external-buyer/pre-register/verify-email-otp/

    Verifies the OTP sent to the email. On success returns a one-time
    email_token (30 min TTL) required at buyer registration.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['External Buyer - Registration'],
        summary='Verify email OTP for buyer pre-registration',
        description='Submit the 6-digit email OTP. On success returns an email_token required at buyer registration.',
        request=None,
        responses={200: None, 400: None},
    )
    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        otp   = request.data.get('otp', '').strip()
        if not email or not otp:
            return StandardResponse.error('email and otp are required.', status_code=status.HTTP_400_BAD_REQUEST)

        _MAX_ATTEMPTS = 3
        _OTP_TTL      = 600
        otp_key      = f'buyer:prereg_email_otp:{email}'
        attempts_key = f'buyer:prereg_email_otp_attempts:{email}'
        stored       = cache.get(otp_key)

        if not stored:
            return StandardResponse.error('OTP has expired. Please request a new one.', status_code=status.HTTP_400_BAD_REQUEST)

        if stored != otp:
            attempts = cache.get(attempts_key, 0) + 1
            remaining = max(0, _MAX_ATTEMPTS - attempts)
            if remaining == 0:
                cache.delete(otp_key)
                cache.delete(attempts_key)
                return StandardResponse.error('Maximum attempts reached. Please request a new OTP.', status_code=status.HTTP_400_BAD_REQUEST)
            cache.set(attempts_key, attempts, _OTP_TTL)
            return StandardResponse.error(f'Incorrect OTP. {remaining} attempt(s) remaining. OTP is valid for 10 minutes.', status_code=status.HTTP_400_BAD_REQUEST)

        cache.delete(otp_key)
        cache.delete(attempts_key)
        cache.delete(f'buyer:prereg_email_otp_count:{email}')

        email_token = secrets.token_urlsafe(32)
        cache.set(f'buyer:prereg_email_token:{email_token}', email, 1800)

        return StandardResponse.success(data={'email_token': email_token}, message='Email address verified successfully.')