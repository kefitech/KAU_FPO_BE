"""
FPO Phone Verification APIs
=============================
Verifies FPO office phone via SMS OTP before submission (SRS §3.1.3).

Endpoints:
    POST  /api/fpo/phone-verify/send/     — send 6-digit OTP to office_phone via SMS
    POST  /api/fpo/phone-verify/confirm/  — verify OTP → sets phone_verified = True
"""

from drf_spectacular.utils import extend_schema, OpenApiExample
from rest_framework import serializers, status
from rest_framework.views import APIView

from apps.core.permissions.rbac import IsFPOManager
from apps.core.utils.responses import StandardResponse
from apps.core.services.translation import t
from apps.database.models.fpo import FPO
from apps.fpo.services.verification import VerificationService, OTPRateLimitExceeded, OTPAttemptsExhausted


class PhoneOTPSendView(APIView):
    permission_classes = [IsFPOManager]

    @extend_schema(
        tags=['FPO - Registration'],
        summary='Send SMS OTP for office phone verification',
        description=(
            'Sends a 6-digit OTP to `office_phone` (Step 2 field) via SMS. '
            'OTP is valid for 10 minutes. Re-calling generates a new OTP. '
            'Requires Step 2 to be completed (office_phone must be set).'
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

        if not fpo.office_phone:
            return StandardResponse.error(
                t('fpo.office_phone_required', lang),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if fpo.phone_verified:
            return StandardResponse.error(
                t('fpo.phone_already_verified', lang),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            VerificationService.send_phone_otp(fpo, lang=lang)
        except OTPRateLimitExceeded:
            return StandardResponse.error(
                t('fpo.otp_rate_limit_exceeded', lang),
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        return StandardResponse.success(
            message=t('fpo.phone_otp_sent', lang),
            data={'phone': _mask_phone(fpo.office_phone)},
        )


class _PhoneOTPConfirmSerializer(serializers.Serializer):
    otp = serializers.CharField(min_length=6, max_length=6)


class PhoneOTPConfirmView(APIView):
    permission_classes = [IsFPOManager]

    @extend_schema(
        tags=['FPO - Registration'],
        summary='Confirm SMS OTP to verify office phone',
        description='Submit the 6-digit OTP sent to office_phone. Sets `phone_verified = true` on success.',
        request=_PhoneOTPConfirmSerializer,
        responses={200: None, 400: None},
        examples=[
            OpenApiExample('Confirm OTP', value={'otp': '739201'}, request_only=True),
        ],
    )
    def post(self, request):
        lang = request.language
        serializer = _PhoneOTPConfirmSerializer(data=request.data)
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

        if fpo.phone_verified:
            return StandardResponse.error(
                t('fpo.phone_already_verified', lang),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            remaining = VerificationService.verify_phone_otp(fpo, serializer.validated_data['otp'])
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

        return StandardResponse.success(message=t('fpo.phone_verified', lang))


def _mask_phone(phone: str) -> str:
    """Return ••••••7890 style masked phone — last 4 digits visible."""
    if len(phone) <= 4:
        return phone
    return '•' * (len(phone) - 4) + phone[-4:]
