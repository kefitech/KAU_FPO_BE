"""
FPO Email Verification APIs
============================
Verifies FPO office email via OTP before submission (BR-008).

Endpoints:
    POST  /api/fpo/email-verify/send/     — send 6-digit OTP to office_email
    POST  /api/fpo/email-verify/confirm/  — verify OTP → sets email_verified = True
"""

from drf_spectacular.utils import extend_schema, OpenApiExample
from rest_framework import serializers, status
from rest_framework.views import APIView

from apps.core.permissions.rbac import IsFPOManager
from apps.core.utils.responses import StandardResponse
from apps.core.services.translation import t
from apps.database.models.fpo import FPO
from apps.fpo.services.verification import VerificationService, OTPRateLimitExceeded, OTPAttemptsExhausted


class EmailOTPSendView(APIView):
    permission_classes = [IsFPOManager]

    @extend_schema(
        tags=['FPO - Registration'],
        summary='Send email OTP for office email verification',
        description=(
            'Sends a 6-digit OTP to `office_email` (Step 2 field). '
            'OTP is valid for 10 minutes. Re-calling this endpoint generates a new OTP '
            'and invalidates the previous one. '
            'Requires Step 2 to be completed (office_email must be set).'
        ),
        request=None,
        responses={200: None, 400: None},
    )
    def post(self, request):
        lang = request.language
        try:
            fpo = FPO.objects.get(primary_user=request.user)
        except FPO.DoesNotExist:
            return StandardResponse.error(
                t('fpo.fpo_not_found', lang),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        if not fpo.office_email:
            return StandardResponse.error(
                t('fpo.office_email_required', lang),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if fpo.email_verified:
            return StandardResponse.error(
                t('fpo.email_already_verified', lang),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            VerificationService.send_email_otp(fpo, lang=lang)
        except OTPRateLimitExceeded:
            return StandardResponse.error(
                t('fpo.otp_rate_limit_exceeded', lang),
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        return StandardResponse.success(
            message=t('fpo.email_otp_sent', lang),
            data={'email': _mask_email(fpo.office_email)},
        )


class _EmailOTPConfirmSerializer(serializers.Serializer):
    otp = serializers.CharField(min_length=6, max_length=6)


class EmailOTPConfirmView(APIView):
    permission_classes = [IsFPOManager]

    @extend_schema(
        tags=['FPO - Registration'],
        summary='Confirm email OTP to verify office email',
        description='Submit the 6-digit OTP sent to office_email. Sets `email_verified = true` on success.',
        request=_EmailOTPConfirmSerializer,
        responses={200: None, 400: None},
        examples=[
            OpenApiExample('Confirm OTP', value={'otp': '482910'}, request_only=True),
        ],
    )
    def post(self, request):
        lang = request.language
        serializer = _EmailOTPConfirmSerializer(data=request.data)
        if not serializer.is_valid():
            return StandardResponse.error(
                serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            fpo = FPO.objects.get(primary_user=request.user)
        except FPO.DoesNotExist:
            return StandardResponse.error(
                t('fpo.fpo_not_found', lang),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        if fpo.email_verified:
            return StandardResponse.error(
                t('fpo.email_already_verified', lang),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            remaining = VerificationService.verify_email_otp(fpo, serializer.validated_data['otp'])
        except OTPAttemptsExhausted:
            return StandardResponse.error(
                t('fpo.otp_attempts_exhausted', lang),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if remaining > 0:
            return StandardResponse.error(
                t('fpo.invalid_otp_with_attempts', lang, attempts_remaining=remaining, validity_minutes=10),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        return StandardResponse.success(message=t('fpo.email_verified', lang))


def _mask_email(email: str) -> str:
    """Return at******@domain.com style masked email."""
    if '@' not in email:
        return email
    local, domain = email.split('@', 1)
    visible = local[:2] if len(local) >= 2 else local
    return f"{visible}{'•' * max(4, len(local) - 2)}@{domain}"
