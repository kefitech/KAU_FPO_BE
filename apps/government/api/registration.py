"""
Public self-registration for government officials and facilitators.
POST /api/government/register/ - AllowAny, creates a pending account.
Requires Super Admin or Sub Admin approval before the account can log in.

Phone number is verified via SMS OTP before registration, instead of the
user setting their own password. A random password is generated server-side;
the official sets their real password later via the normal reset-password
flow once their account is approved.
"""
import logging
import random
import string

from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework import serializers, status
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny

from apps.core.utils.constants import UserRole, District
from apps.core.utils.responses import StandardResponse
from apps.database.models.government import GovernmentOfficialProfile, USER_CATEGORY_CHOICES
from apps.notifications.services import send_notification

from apps.government.api.validators import validate_id_number

logger = logging.getLogger(__name__)

_OTP_TTL      = 600  # 10 minutes
_VERIFIED_TTL = 900  # 15 minutes — enough time to finish filling the form
_MAX_SENDS    = 3
_MAX_ATTEMPTS = 3


class OTPRateLimitExceeded(Exception):
    pass


class OTPAttemptsExhausted(Exception):
    pass


def _generate_otp() -> str:
    return ''.join(random.choices(string.digits, k=6))


def _generate_password() -> str:
    alphabet = string.ascii_letters + string.digits
    return ''.join(random.choices(alphabet, k=16))

def _send_registration_otp(contact: str, channel: str, lang: str = 'en') -> None:
    count_key = f'gov_reg_otp_count:{channel}:{contact}'
    count = cache.get(count_key, 0)
    if count >= _MAX_SENDS:
        raise OTPRateLimitExceeded()
    if count == 0:
        cache.set(count_key, 1, _OTP_TTL)
    else:
        cache.incr(count_key)

    otp = _generate_otp()
    logger.warning(f"[DEV] Government registration {channel} OTP for {contact}: {otp}")
    cache.set(f'gov_reg_otp:{channel}:{contact}', otp, _OTP_TTL)
    notif_channel = 'sms' if channel == 'phone' else 'email'
    notif_code = 'government_registration_otp' if channel == 'phone' else 'government_registration_email_otp'
    send_notification(
        user=None,
        code=notif_code,
        channel=notif_channel,
        context={'otp': otp},
        lang=lang,
        override_recipient=contact,
    )

def _verify_registration_otp(contact: str, channel: str, otp: str) -> int:
    otp_key = f'gov_reg_otp:{channel}:{contact}'
    attempts_key = f'gov_reg_otp_attempts:{channel}:{contact}'
    stored = cache.get(otp_key)
    if stored and stored == otp:
        cache.delete(otp_key)
        cache.delete(f'gov_reg_otp_count:{channel}:{contact}')
        cache.delete(attempts_key)
        cache.set(f'gov_reg_otp_verified:{channel}:{contact}', '1', _VERIFIED_TTL)
        return 0
    attempts = cache.get(attempts_key, 0) + 1
    remaining = max(0, _MAX_ATTEMPTS - attempts)
    if remaining == 0:
        cache.delete(otp_key)
        cache.delete(attempts_key)
        raise OTPAttemptsExhausted()
    cache.set(attempts_key, attempts, _OTP_TTL)
    return remaining


class _GovtOTPSendSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=15)


class GovernmentRegistrationOTPSendView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        lang = getattr(request, 'language', 'en')
        serializer = _GovtOTPSendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data['phone']

        try:
            _send_registration_otp(phone, 'phone', lang=lang)
        except OTPRateLimitExceeded:
            return StandardResponse.error(
                'Too many OTP requests. Please try again later.',
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        return StandardResponse.success(message='OTP sent.')


class _GovtOTPConfirmSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=15)
    otp = serializers.CharField(min_length=6, max_length=6)


class GovernmentRegistrationOTPConfirmView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = _GovtOTPConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data['phone']
        otp = serializer.validated_data['otp']

        try:
            remaining = _verify_registration_otp(phone, 'phone', otp)
        except OTPAttemptsExhausted:
            return StandardResponse.error(
                'Too many incorrect attempts. Please request a new OTP.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if remaining > 0:
            return StandardResponse.error(
                f'Incorrect OTP. {remaining} attempt(s) remaining.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        return StandardResponse.success(message='Phone verified.')


class _GovtEmailOTPSendSerializer(serializers.Serializer):
    email = serializers.EmailField()


class GovernmentRegistrationEmailOTPSendView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        lang = getattr(request, 'language', 'en')
        serializer = _GovtEmailOTPSendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email'].lower()

        try:
            _send_registration_otp(email, 'email', lang=lang)
        except OTPRateLimitExceeded:
            return StandardResponse.error(
                'Too many OTP requests. Please try again later.',
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        return StandardResponse.success(message='OTP sent.')


class _GovtEmailOTPConfirmSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(min_length=6, max_length=6)


class GovernmentRegistrationEmailOTPConfirmView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = _GovtEmailOTPConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email'].lower()
        otp = serializer.validated_data['otp']

        try:
            remaining = _verify_registration_otp(email, 'email', otp)
        except OTPAttemptsExhausted:
            return StandardResponse.error(
                'Too many incorrect attempts. Please request a new OTP.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if remaining > 0:
            return StandardResponse.error(
                f'Incorrect OTP. {remaining} attempt(s) remaining.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        return StandardResponse.success(message='Email verified.')


class GovernmentRegistrationSerializer(serializers.Serializer):
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150, required=False, default='')
    phone = serializers.CharField(max_length=15)
    designation = serializers.CharField(max_length=200)
    department = serializers.CharField(max_length=200)
    user_category = serializers.ChoiceField(choices=USER_CATEGORY_CHOICES)
    id_number = serializers.CharField(max_length=30)
    jurisdiction_type = serializers.ChoiceField(choices=[('district', 'District'), ('state', 'State')])
    assigned_district = serializers.ChoiceField(choices=District.choices, required=False, allow_null=True)

    def validate_email(self, value):
        value = value.lower()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError('A user with this email already exists.')
        if not cache.get(f'gov_reg_otp_verified:email:{value}'):
            raise serializers.ValidationError('Email has not been verified. Please verify it first.')
        return value

    def validate_phone(self, value):
        if not cache.get(f'gov_reg_otp_verified:phone:{value}'):
            raise serializers.ValidationError('Phone number has not been verified. Please verify it first.')
        return value

    def validate(self, attrs):
        if attrs['jurisdiction_type'] == 'district' and not attrs.get('assigned_district'):
            raise serializers.ValidationError({
                'assigned_district': 'Required when jurisdiction_type=district.'
            })

        is_valid, error = validate_id_number(attrs['user_category'], attrs['id_number'])
        if not is_valid:
            raise serializers.ValidationError({'id_number': error})

        return attrs


class GovernmentRegistrationView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = GovernmentRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = User.objects.create_user(
            username=data['email'],
            email=data['email'],
            password=_generate_password(),
            first_name=data['first_name'],
            last_name=data.get('last_name', ''),
            is_active=False,
        )

        from django.contrib.auth.models import Group
        govt_group, _ = Group.objects.get_or_create(name=UserRole.GOVERNMENT)
        user.groups.add(govt_group)

        GovernmentOfficialProfile.objects.create(
            user=user,
            designation=data['designation'],
            department=data['department'],
            jurisdiction_type=data['jurisdiction_type'],
            assigned_district=data.get('assigned_district') if data['jurisdiction_type'] == 'district' else None,
            user_category=data['user_category'],
            id_number=data['id_number'],
            registration_status='pending',
        )

        profile = user.profile
        if data.get('phone'):
            profile.phone = data['phone']
            profile.save(update_fields=['phone'])

        # OTP verification is single-use — clear it now that registration is complete
        cache.delete(f'gov_reg_otp_verified:phone:{data["phone"]}')
        cache.delete(f'gov_reg_otp_verified:email:{data["email"]}')

        return StandardResponse.success(
            data={'id': user.id, 'status': 'pending'},
            message='Registration submitted. Your account will be reviewed by an administrator before you can log in.',
            status_code=201,
        )
