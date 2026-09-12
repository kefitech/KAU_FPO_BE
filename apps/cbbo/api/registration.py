"""
Public self-registration for CBBO/NGO officers.
POST /api/cbbo/register/ - AllowAny, creates a pending account.
Mirrors apps/government/api/registration.py.

Phone number is verified via SMS OTP before registration, instead of the
user setting their own password. A random password is generated server-side;
the officer sets their real password later via the normal reset-password
flow once their account is approved.
"""
import logging
import random
import string

from django.contrib.auth.models import User, Group
from django.core.cache import cache
from rest_framework import serializers, status
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny

from apps.core.utils.constants import UserRole, District
from apps.core.utils.responses import StandardResponse
from apps.database.models.cbbo import CBBOAssignment
from apps.database.models.organisation import Organisation
from apps.database.models.cbbo_profile import CBBOOfficerProfile
from apps.notifications.services import send_notification

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
    count_key = f'cbbo_reg_otp_count:{channel}:{contact}'
    count = cache.get(count_key, 0)
    if count >= _MAX_SENDS:
        raise OTPRateLimitExceeded()
    if count == 0:
        cache.set(count_key, 1, _OTP_TTL)
    else:
        cache.incr(count_key)

    otp = _generate_otp()
    logger.warning(f"[DEV] CBBO registration {channel} OTP for {contact}: {otp}")
    cache.set(f'cbbo_reg_otp:{channel}:{contact}', otp, _OTP_TTL)
    notif_channel = 'sms' if channel == 'phone' else 'email'
    notif_code = 'cbbo_registration_otp' if channel == 'phone' else 'cbbo_registration_email_otp'
    send_notification(
        user=None,
        code=notif_code,
        channel=notif_channel,
        context={'otp': otp},
        lang=lang,
        override_recipient=contact,
    )

def _verify_registration_otp(contact: str, channel: str, otp: str) -> int:
    otp_key = f'cbbo_reg_otp:{channel}:{contact}'
    attempts_key = f'cbbo_reg_otp_attempts:{channel}:{contact}'
    stored = cache.get(otp_key)
    if stored and stored == otp:
        cache.delete(otp_key)
        cache.delete(f'cbbo_reg_otp_count:{channel}:{contact}')
        cache.delete(attempts_key)
        cache.set(f'cbbo_reg_otp_verified:{channel}:{contact}', '1', _VERIFIED_TTL)
        return 0
    attempts = cache.get(attempts_key, 0) + 1
    remaining = max(0, _MAX_ATTEMPTS - attempts)
    if remaining == 0:
        cache.delete(otp_key)
        cache.delete(attempts_key)
        raise OTPAttemptsExhausted()
    cache.set(attempts_key, attempts, _OTP_TTL)
    return remaining


class _CBBOOTPSendSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=15)


class CBBORegistrationOTPSendView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        lang = getattr(request, 'language', 'en')
        serializer = _CBBOOTPSendSerializer(data=request.data)
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


class _CBBOOTPConfirmSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=15)
    otp = serializers.CharField(min_length=6, max_length=6)


class CBBORegistrationOTPConfirmView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = _CBBOOTPConfirmSerializer(data=request.data)
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


class _CBBOEmailOTPSendSerializer(serializers.Serializer):
    email = serializers.EmailField()


class CBBORegistrationEmailOTPSendView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        lang = getattr(request, 'language', 'en')
        serializer = _CBBOEmailOTPSendSerializer(data=request.data)
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


class _CBBOEmailOTPConfirmSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(min_length=6, max_length=6)


class CBBORegistrationEmailOTPConfirmView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = _CBBOEmailOTPConfirmSerializer(data=request.data)
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


class CBBORegistrationSerializer(serializers.Serializer):
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150, required=False, default='')
    phone = serializers.CharField(max_length=15)
    designation = serializers.CharField(max_length=200, required=False, allow_blank=True, default='')
    organisation = serializers.PrimaryKeyRelatedField(queryset=Organisation.objects.filter(is_deleted=False, is_active=True))
    level = serializers.ChoiceField(choices=CBBOAssignment.LEVEL_CHOICES, default=CBBOAssignment.LEVEL_DISTRICT)
    district_codes = serializers.ListField(child=serializers.ChoiceField(choices=District.choices), required=False, default=list)

    def validate_email(self, value):
        value = value.lower()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError('A user with this email already exists.')
        if not cache.get(f'cbbo_reg_otp_verified:email:{value}'):
            raise serializers.ValidationError('Email has not been verified. Please verify it first.')
        return value

    def validate_phone(self, value):
        if not cache.get(f'cbbo_reg_otp_verified:phone:{value}'):
            raise serializers.ValidationError('Phone number has not been verified. Please verify it first.')
        return value

    def validate(self, attrs):
        if attrs['level'] == CBBOAssignment.LEVEL_DISTRICT and not attrs.get('district_codes'):
            raise serializers.ValidationError({'district_codes': 'Required when level=district.'})
        return attrs


class CBBORegistrationView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = CBBORegistrationSerializer(data=request.data)
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

        cbbo_group, _ = Group.objects.get_or_create(name=UserRole.CBBO)
        user.groups.add(cbbo_group)

        CBBOOfficerProfile.objects.create(
            user=user,
            organisation=data['organisation'],
            designation=data.get('designation', ''),
            registration_status='pending',
        )

        if data['level'] == CBBOAssignment.LEVEL_STATE:
            CBBOAssignment.objects.create(cbbo=user, level=CBBOAssignment.LEVEL_STATE, district='', is_active=True)
        else:
            CBBOAssignment.objects.bulk_create([
                CBBOAssignment(cbbo=user, level=CBBOAssignment.LEVEL_DISTRICT, district=code, is_active=True)
                for code in dict.fromkeys(data['district_codes'])
            ])

        profile = user.profile
        if data.get('phone'):
            profile.phone = data['phone']
            profile.save(update_fields=['phone'])

        # OTP verification is single-use — clear it now that registration is complete
        cache.delete(f'cbbo_reg_otp_verified:phone:{data["phone"]}')
        cache.delete(f'cbbo_reg_otp_verified:email:{data["email"]}')

        return StandardResponse.success(
            data={'id': user.id, 'status': 'pending'},
            message='Registration submitted. Your account will be reviewed by an administrator before you can log in.',
            status_code=201,
        )


class PublicOrganisationListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        orgs = Organisation.objects.filter(is_deleted=False, is_active=True).order_by('name')
        data = [
            {'id': o.id, 'name': o.name, 'org_type': o.org_type, 'org_type_display': o.get_org_type_display()}
            for o in orgs
        ]
        return StandardResponse.success(data=data)
