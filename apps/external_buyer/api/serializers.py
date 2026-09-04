"""
External Buyer Registration Serializers
=========================================
"""

import re

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.core.services.translation import t

User = get_user_model()


class RegisterBuyerUserSerializer(serializers.Serializer):
    """
    External buyer self-registration.

    Requires a verified phone_token (from POST /api/fpo/pre-register/verify-otp/)
    and a verified email_token (from POST /api/external-buyer/pre-register/verify-email-otp/).
    Email/phone are derived from these tokens, not re-submitted, so the login
    credentials always match what was actually verified via OTP.

    Creates a User, assigns the external_buyer group, and creates a pending
    BuyerDirectory row linked to the new user.
    """

    first_name = serializers.CharField(
        max_length=150, required=True,
        help_text="First name of the buyer contact"
    )
    last_name = serializers.CharField(
        max_length=150, required=True,
        help_text="Last name of the buyer contact"
    )
    organisation = serializers.CharField(
        max_length=300, required=False, allow_blank=True,
        help_text="Company / organisation name (optional)"
    )
    password = serializers.CharField(
        write_only=True, required=True,
        style={'input_type': 'password'},
        help_text="Min 8 chars, 1 uppercase, 1 lowercase, 1 digit"
    )
    confirm_password = serializers.CharField(
        write_only=True, required=True,
        style={'input_type': 'password'},
        help_text="Must match password"
    )
    phone_token = serializers.CharField(
        write_only=True, required=True,
        help_text="One-time token from POST /api/fpo/pre-register/verify-otp/ (valid 30 min)"
    )
    email_token = serializers.CharField(
        write_only=True, required=True,
        help_text="One-time token from POST /api/external-buyer/pre-register/verify-email-otp/ (valid 30 min)"
    )

    def validate_phone_token(self, value):
        if not cache.get(f'fpo:prereg_phone_token:{value}'):
            raise serializers.ValidationError(
                "Invalid or expired phone token. Please verify your phone number first."
            )
        return value

    def validate_email_token(self, value):
        if not cache.get(f'buyer:prereg_email_token:{value}'):
            raise serializers.ValidationError(
                "Invalid or expired email token. Please verify your email address first."
            )
        return value

    def validate_password(self, value):
        if len(value) < 8:
            raise serializers.ValidationError(t('auth.password_too_short'))
        if not (re.search(r'[A-Z]', value) and re.search(r'[a-z]', value) and re.search(r'\d', value)):
            raise serializers.ValidationError(t('auth.password_too_weak'))
        try:
            validate_password(value)
        except DjangoValidationError as e:
            raise serializers.ValidationError(str(e))
        return value

    def validate(self, attrs):
        if attrs['password'] != attrs['confirm_password']:
            raise serializers.ValidationError({'confirm_password': t('auth.password_mismatch')})
        return attrs

    def create(self, validated_data):
        phone_token = validated_data.pop('phone_token')
        email_token = validated_data.pop('email_token')

        phone = cache.get(f'fpo:prereg_phone_token:{phone_token}')
        email = cache.get(f'buyer:prereg_email_token:{email_token}')

        if not phone or not email:
            raise serializers.ValidationError('Verification tokens expired. Please verify phone and email again.')

        cache.delete(f'fpo:prereg_phone_token:{phone_token}')
        cache.delete(f'buyer:prereg_email_token:{email_token}')

        validated_data.pop('confirm_password')
        password     = validated_data.pop('password')
        organisation = validated_data.pop('organisation', '')
        first_name   = validated_data['first_name']
        last_name    = validated_data['last_name']

        user = User.objects.create_user(
            username=email,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
        )

        buyer_group, _ = Group.objects.get_or_create(name='external_buyer')
        user.groups.add(buyer_group)

        user.profile.phone = phone
        user.profile.save(update_fields=['phone'])

        from apps.database.models.marketplace import BuyerDirectory
        BuyerDirectory.objects.create(
            user=user,
            name=f"{first_name} {last_name}".strip(),
            organisation=organisation,
            contact_email=email,
            contact_phone=phone,
            fpo=None,
            status=BuyerDirectory.Status.PENDING,
        )

        return user