"""
KAU-FPO Platform - Accounts API Serializers
============================================

Serializers for authentication and role management.

Author: Athul Gopan
Created: 22-04-2026
"""

import re
from typing import List
from rest_framework import serializers
from django.contrib.auth.models import Group
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import extend_schema_field

from apps.core.services.translation import t
from apps.core.utils.constants import UserRole
from apps.core.models.generic import AuditLog
from django.contrib.auth import authenticate

User = get_user_model()


class RoleSerializer(serializers.ModelSerializer):
    """
    Serializer for Role (Django Group) management.

    Wraps Django's built-in Group model to manage roles.
    """

    # Read-only fields
    id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Group
        fields = ['id', 'name']

    def validate_name(self, value):
        """
        Validate role name.
        - Must be unique
        - Must be lowercase with underscores
        - Cannot be empty
        """
        if not value or not value.strip():
            raise serializers.ValidationError("Role name cannot be empty.")

        # Convert to lowercase with underscores
        value = value.lower().strip().replace(' ', '_')

        # Check uniqueness (excluding current instance in update)
        instance_id = self.instance.id if self.instance else None
        if Group.objects.filter(name=value).exclude(id=instance_id).exists():
            raise serializers.ValidationError(
                f"Role with name '{value}' already exists."
            )

        return value

    def to_representation(self, instance):
        """
        Customize output representation.
        """
        representation = super().to_representation(instance)

        # Add user count (how many users have this role)
        representation['user_count'] = instance.user_set.count()

        return representation


class UserSerializer(serializers.ModelSerializer):
    """
    Serializer for User model (read-only representation).

    Used for returning user data in responses.
    Does not include password field.
    """

    roles = serializers.SerializerMethodField()
    phone = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'phone',
            'roles',
            'is_active',
            'date_joined',
            'last_login',
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.CharField())
    def get_phone(self, obj):
        return getattr(getattr(obj, 'profile', None), 'phone', '')

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_roles(self, obj) -> List[str]:
        return list(obj.groups.values_list('name', flat=True))


class RegisterSuperAdminSerializer(serializers.Serializer):
    """
    Serializer for Super Admin registration.

    Validates input and creates new super_admin user.
    """

    # Required fields
    username = serializers.CharField(
        max_length=150,
        required=True,
        help_text="Username for login (alphanumeric and @/./+/-/_ only)"
    )
    email = serializers.EmailField(
        required=True,
        help_text="Valid email address"
    )
    password = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'},
        help_text="Minimum 8 characters, 1 uppercase, 1 lowercase, 1 number"
    )
    password_confirm = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'},
        help_text="Must match password"
    )
    first_name = serializers.CharField(
        max_length=150,
        required=True,
        help_text="User's first name"
    )
    last_name = serializers.CharField(
        max_length=150,
        required=True,
        help_text="User's last name"
    )
    phone = serializers.CharField(
        max_length=15,
        required=False,
        allow_blank=True,
        default='',
        help_text="Indian phone number (10 digits, optional +91 prefix)"
    )

    def validate_username(self, value):
        """
        Validate username uniqueness.
        """
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError(
                t('auth.username_already_exists')
            )
        return value

    def validate_email(self, value):
        """
        Validate email uniqueness.
        """
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError(
                t('auth.email_already_exists')
            )
        return value.lower()

    def validate_password(self, value):
        """
        Validate password strength.

        Requirements:
        - Minimum 8 characters
        - At least 1 uppercase letter
        - At least 1 lowercase letter
        - At least 1 number
        """
        # Check minimum length
        if len(value) < 8:
            raise serializers.ValidationError(
                t('auth.password_too_short')
            )

        # Check complexity
        has_upper = re.search(r'[A-Z]', value)
        has_lower = re.search(r'[a-z]', value)
        has_digit = re.search(r'\d', value)

        if not (has_upper and has_lower and has_digit):
            raise serializers.ValidationError(
                t('auth.password_too_weak')
            )

        # Use Django's password validators (common passwords, etc.)
        try:
            validate_password(value)
        except DjangoValidationError as e:
            raise serializers.ValidationError(str(e))

        return value

    def validate_phone(self, value):
        if value:
            try:
                from apps.core.utils.validators import validate_indian_phone
                validate_indian_phone(value)
            except DjangoValidationError as e:
                raise serializers.ValidationError(str(e))
        return value

    def validate(self, attrs):
        """
        Validate password confirmation match.
        """
        password = attrs.get('password')
        password_confirm = attrs.get('password_confirm')

        if password != password_confirm:
            raise serializers.ValidationError({
                'password_confirm': t('auth.password_mismatch')
            })

        return attrs

    def create(self, validated_data):
        """
        Create super_admin user and assign to super_admin group.
        """
        validated_data.pop('password_confirm', None)
        phone    = validated_data.pop('phone', '')
        password = validated_data.pop('password')

        user = User.objects.create_user(password=password, **validated_data)

        super_admin_group, _ = Group.objects.get_or_create(name=UserRole.SUPER_ADMIN)
        user.groups.add(super_admin_group)

        if phone:
            user.profile.phone = phone
            user.profile.save(update_fields=['phone'])

        return user


class LoginSerializer(serializers.Serializer):
    """
    Serializer for user login.

    Accepts username or email along with password.
    Returns JWT tokens (access + refresh) on successful authentication.
    """

    # Accept either username or email
    username = serializers.CharField(
        required=True,
        help_text="Username or email address"
    )
    password = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'},
        help_text="User password"
    )

    def validate(self, attrs):
        """
        Validate credentials and authenticate user.
        """
        username = attrs.get('username')
        password = attrs.get('password')

        # Try to find user by username or email
        user = None

        # Check if input is email format
        if '@' in username:
            # Try to find by email
            try:
                user_obj = User.objects.get(email=username)
                username = user_obj.username
            except User.DoesNotExist:
                pass

        # Authenticate user
        user = authenticate(username=username, password=password)

        if user is None:
            raise serializers.ValidationError({
                'non_field_errors': [t('auth.invalid_credentials')]
            })

        # Check if account is active
        if not user.is_active:
            raise serializers.ValidationError({
                'non_field_errors': [t('auth.account_disabled')]
            })

        # Store user in validated data
        attrs['user'] = user
        return attrs


class LoginHistorySerializer(serializers.ModelSerializer):
    """
    Serializer for login history from AuditLog.

    Shows login attempts (successful and failed) with IP address,
    location, user agent, and timestamp.
    """

    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.CharField(source='user.email', read_only=True)
    action_display = serializers.CharField(source='get_action_display', read_only=True)
    location_string = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            'id',
            'username',
            'email',
            'action',
            'action_display',
            'ip_address',
            'location',
            'location_string',
            'user_agent',
            'request_path',
            'request_method',
            'changes',
            'created_at',
        ]
        read_only_fields = fields

    def get_location_string(self, obj) -> str:
        """
        Get formatted location string from location JSON field.

        Returns:
            Formatted string like "Thrissur, Kerala, India" or "Unknown"
        """
        if not obj.location:
            return "Unknown"

        parts = []

        if obj.location.get('city') and obj.location['city'] != 'Unknown':
            parts.append(obj.location['city'])

        if obj.location.get('region') and obj.location['region'] != 'Unknown':
            parts.append(obj.location['region'])

        if obj.location.get('country') and obj.location['country'] != 'Unknown':
            parts.append(obj.location['country'])

        return ', '.join(parts) if parts else 'Unknown'


class ForgotPasswordSerializer(serializers.Serializer):
    """
    Request body for forgot password.

    Pass `email` for admin accounts (super_admin, sub_admin) — sends a reset link.
    Pass `phone` for FPO users (fpo_manager) — sends a 6-digit OTP via SMS.
    Exactly one of the two fields is required.
    """

    email = serializers.EmailField(
        required=False,
        allow_blank=True,
        help_text="Registered email address (admins only)"
    )
    phone = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=15,
        help_text="Registered phone number (FPO users only)"
    )

    def validate(self, attrs):
        email = attrs.get('email', '').strip()
        phone = attrs.get('phone', '').strip()
        if not email and not phone:
            raise serializers.ValidationError("Provide either email or phone.")
        return attrs


class VerifyOTPSerializer(serializers.Serializer):
    """
    Request body for OTP verification (SMS password reset flow).

    After a successful verify, the response contains a `reset_token`
    to be passed to the reset endpoint.
    """

    phone = serializers.CharField(
        required=True,
        max_length=15,
        help_text="Phone number used in the forgot-password request"
    )
    otp = serializers.CharField(
        required=True,
        min_length=6,
        max_length=6,
        help_text="6-digit OTP received via SMS"
    )


class ResetPasswordSerializer(serializers.Serializer):
    """
    Request body for setting a new password.

    Used by both flows:
    - Email flow: token comes from the link in the reset email
    - SMS flow: token comes from the verify-otp response
    """

    token = serializers.CharField(
        required=True,
        help_text="Reset token from email link or verify-otp response"
    )
    new_password = serializers.CharField(
        required=True,
        write_only=True,
        style={'input_type': 'password'},
        help_text="New password (min 8 chars, 1 uppercase, 1 lowercase, 1 digit)"
    )
    confirm_password = serializers.CharField(
        required=True,
        write_only=True,
        style={'input_type': 'password'},
        help_text="Must match new_password"
    )

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({'confirm_password': t('auth.password_mismatch')})
        return attrs


class ChangePasswordSerializer(serializers.Serializer):
    partial_token    = serializers.CharField(required=True, help_text="Partial token from login response")
    new_password     = serializers.CharField(required=True, write_only=True, style={'input_type': 'password'})
    confirm_password = serializers.CharField(required=True, write_only=True, style={'input_type': 'password'})

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({'confirm_password': t('auth.password_mismatch')})
        return attrs


class ProfileUpdateSerializer(serializers.Serializer):
    first_name         = serializers.CharField(max_length=150, required=False, allow_blank=True, help_text="User's first name")
    last_name          = serializers.CharField(max_length=150, required=False, allow_blank=True, help_text="User's last name")
    phone              = serializers.CharField(max_length=15, required=False, allow_blank=True, help_text="Indian phone number (10 digits)")
    preferred_language = serializers.CharField(max_length=10, required=False, help_text="Language code e.g. en, ml")

    def validate_phone(self, value):
        if value:
            from apps.core.utils.validators import validate_indian_phone
            try:
                validate_indian_phone(value)
            except DjangoValidationError as e:
                raise serializers.ValidationError(str(e))
        return value

    def validate_preferred_language(self, value):
        from apps.database.models import Language
        valid = [lang['code'] for lang in Language.get_active_languages()]
        if value not in valid:
            raise serializers.ValidationError(f"'{value}' is not an active language.")
        return value


class ChangeCurrentPasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(
        required=True, write_only=True, style={'input_type': 'password'},
        help_text="The user's current password"
    )
    new_password     = serializers.CharField(
        required=True, write_only=True, style={'input_type': 'password'},
        help_text="New password (min 8 chars, 1 uppercase, 1 lowercase, 1 digit)"
    )
    confirm_password = serializers.CharField(
        required=True, write_only=True, style={'input_type': 'password'},
        help_text="Must match new_password"
    )

    def validate_new_password(self, value):
        import re
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
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({'confirm_password': t('auth.password_mismatch')})
        return attrs
