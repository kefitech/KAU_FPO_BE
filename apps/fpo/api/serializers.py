"""
FPO API Serializers
===================
Input validation and output shapes for all FPO-facing endpoints.
"""

import re

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.core.services.translation import t
from apps.core.utils.constants import UserRole

from apps.database.models.fpo import (
    FPO, ApplicationStatusHistory, RegisteredUnder,
)
from apps.core.utils.constants import District, FPOStatus

User = get_user_model()


# =============================================================================
# FPO USER REGISTRATION
# =============================================================================

class RegisterFPOUserSerializer(serializers.Serializer):
    """
    FPO user self-registration.

    Creates an fpo_manager account. Username is set to email automatically
    so users log in with their email address.
    Phone is required — used for SMS OTP in forgot-password flow.
    """

    first_name = serializers.CharField(
        max_length=150, required=True,
        help_text="First name of the FPO representative"
    )
    last_name = serializers.CharField(
        max_length=150, required=True,
        help_text="Last name of the FPO representative"
    )
    email = serializers.EmailField(
        required=True,
        help_text="Email address — used for login and notifications"
    )
    phone = serializers.CharField(
        max_length=10, required=True,
        help_text="10-digit Indian mobile number — used for SMS OTP"
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
    eligibility_token = serializers.CharField(
        write_only=True, required=True,
        help_text="One-time token from POST /api/fpo/eligibility-check/ (valid 30 min)"
    )
    phone_token = serializers.CharField(
        write_only=True, required=True,
        help_text="One-time token from POST /api/fpo/pre-register/verify-otp/ (valid 30 min)"
    )

    def validate_eligibility_token(self, value):
        if not cache.get(f'fpo:eligibility_token:{value}'):
            raise serializers.ValidationError(
                "Invalid or expired eligibility token. Please complete the eligibility check first."
            )
        return value

    def validate_phone_token(self, value):
        if not cache.get(f'fpo:prereg_phone_token:{value}'):
            raise serializers.ValidationError(
                "Invalid or expired phone token. Please verify your phone number first."
            )
        return value

    def validate_email(self, value):
        value = value.lower().strip()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError(t('auth.email_already_exists'))
        return value

    def validate_phone(self, value):
        from apps.core.utils.validators import validate_indian_phone
        from apps.database.models import UserProfile
        try:
            validate_indian_phone(value)
        except DjangoValidationError as e:
            raise serializers.ValidationError(str(e))
        if UserProfile.objects.filter(phone=value).exists():
            raise serializers.ValidationError("An account with this phone number already exists.")
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
        e_token = validated_data.pop('eligibility_token')
        p_token = validated_data.pop('phone_token')
        cache.delete(f'fpo:eligibility_token:{e_token}')
        cache.delete(f'fpo:prereg_phone_token:{p_token}')

        validated_data.pop('confirm_password')
        phone    = validated_data.pop('phone')
        password = validated_data.pop('password')
        email    = validated_data['email']

        user = User.objects.create_user(
            username=email,
            password=password,
            **validated_data,
        )

        fpo_group, _ = Group.objects.get_or_create(name=UserRole.FPO_MANAGER)
        user.groups.add(fpo_group)

        user.profile.phone = phone
        user.profile.save(update_fields=['phone'])

        return user


# =============================================================================
# ELIGIBILITY CHECK
# =============================================================================

class EligibilityCheckSerializer(serializers.Serializer):
    """
    Pre-registration eligibility check (RCD 4.2.1).
    AllowAny — no login required.
    """

    member_count          = serializers.IntegerField(
        required=True, min_value=1,
        help_text='Total number of farmer members'
    )
    district              = serializers.ChoiceField(
        choices=District.choices, required=True,
        help_text='Must be a valid Kerala district'
    )
    registered_under_act  = serializers.BooleanField(
        required=True,
        help_text='Confirm FPO is registered under a relevant Act'
    )
    has_valid_registration = serializers.BooleanField(
        required=True,
        help_text='Confirm FPO has a valid registration number'
    )
    has_bank_account      = serializers.BooleanField(
        required=True,
        help_text='Confirm FPO has an active bank account'
    )


# =============================================================================
# FPO STEP 1 — BASIC INFO (CREATE)
# =============================================================================

class FPOStep1Serializer(serializers.Serializer):
    """
    Step 1 — Basic Info. Creates FPO in DRAFT status.
    Duplicate detection on pan_number, registration_number, cin_number, gst_number.
    """

    name                 = serializers.CharField(max_length=255, help_text='FPO name in English')
    name_ml              = serializers.CharField(max_length=255, required=False, allow_blank=True, help_text='FPO name in Malayalam (optional)')
    registration_number  = serializers.CharField(max_length=100, help_text='Unique FPO registration number (alphanumeric + /)')
    cin_number           = serializers.CharField(max_length=21, required=False, allow_blank=True, help_text='MCA21 CIN number (optional)')
    date_of_registration = serializers.DateField(help_text='Date of FPO registration (not future, not older than 20 years)')
    registered_under     = serializers.ChoiceField(choices=RegisteredUnder.choices, help_text='Act under which FPO is registered')
    pan_number           = serializers.CharField(max_length=10, help_text='PAN number — format: AAAAA9999A')
    gst_number           = serializers.CharField(max_length=15, required=False, allow_blank=True, help_text='GST number (optional) — must start with 32 for Kerala')

    def validate_pan_number(self, value):
        import re
        value = value.upper().strip()
        if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]$', value):
            raise serializers.ValidationError('Invalid PAN format. Expected: AAAAA9999A')
        return value

    def validate_gst_number(self, value):
        import re
        if value:
            value = value.upper().strip()
            if not value.startswith('32'):
                raise serializers.ValidationError('GST number must start with 32 for Kerala.')
            if not re.match(r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$', value):
                raise serializers.ValidationError('Invalid GST number format.')
        return value

    def validate_cin_number(self, value):
        import re
        if value:
            value = value.upper().strip()
            if not re.match(r'^[A-Z]{1}[0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}$', value):
                raise serializers.ValidationError('Invalid CIN format.')
        return value

    def validate_date_of_registration(self, value):
        from datetime import date
        from dateutil.relativedelta import relativedelta
        today = date.today()
        if value > today:
            raise serializers.ValidationError('Date of registration cannot be in the future.')
        if value < today - relativedelta(years=20):
            raise serializers.ValidationError('Date of registration cannot be older than 20 years.')
        return value

    def validate_registration_number(self, value):
        import re
        value = value.strip()
        if not re.match(r'^[A-Za-z0-9/]+$', value):
            raise serializers.ValidationError('Registration number can only contain alphanumeric characters and /.')
        # Duplicate check (exclude current FPO if updating)
        fpo_id = self.context.get('fpo_id')
        qs = FPO.objects.filter(registration_number=value)
        if fpo_id:
            qs = qs.exclude(pk=fpo_id)
        if qs.exists():
            raise serializers.ValidationError('duplicate')
        return value

    def validate(self, attrs):
        # Duplicate checks for pan, gst, cin
        fpo_id = self.context.get('fpo_id')

        pan = attrs.get('pan_number')
        if pan:
            qs = FPO.objects.filter(pan_number=pan)
            if fpo_id:
                qs = qs.exclude(pk=fpo_id)
            if qs.exists():
                raise serializers.ValidationError({'pan_number': 'duplicate'})

        gst = attrs.get('gst_number')
        if gst:
            qs = FPO.objects.filter(gst_number=gst)
            if fpo_id:
                qs = qs.exclude(pk=fpo_id)
            if qs.exists():
                raise serializers.ValidationError({'gst_number': 'duplicate'})

        cin = attrs.get('cin_number')
        if cin:
            qs = FPO.objects.filter(cin_number=cin)
            if fpo_id:
                qs = qs.exclude(pk=fpo_id)
            if qs.exists():
                raise serializers.ValidationError({'cin_number': 'duplicate'})

        return attrs


# =============================================================================
# FPO STEP 2 — CONTACT & LOCATION
# =============================================================================

class FPOStep2Serializer(serializers.Serializer):
    """Step 2 — Contact & Location."""

    district      = serializers.ChoiceField(choices=District.choices)
    block_taluk   = serializers.CharField(max_length=100)
    village_town  = serializers.CharField(max_length=100)
    address_line1 = serializers.CharField(max_length=255)
    address_line2 = serializers.CharField(max_length=255, required=False, allow_blank=True)
    pincode       = serializers.CharField(max_length=6, help_text='6 digits starting with 6')
    office_phone  = serializers.CharField(max_length=10, required=False, allow_blank=True)
    office_email  = serializers.EmailField(help_text='Will require OTP verification before submission')
    website       = serializers.URLField(required=False, allow_blank=True)
    latitude      = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    longitude     = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)

    def validate_pincode(self, value):
        if not value.isdigit() or len(value) != 6 or not value.startswith('6'):
            raise serializers.ValidationError('Pincode must be 6 digits starting with 6.')
        return value

    def validate_office_phone(self, value):
        if value:
            import re
            if not re.match(r'^[6-9]\d{9}$', value):
                raise serializers.ValidationError('Enter a valid 10-digit Indian mobile number.')
            # Duplicate check
            fpo_id = self.context.get('fpo_id')
            qs = FPO.objects.filter(office_phone=value)
            if fpo_id:
                qs = qs.exclude(pk=fpo_id)
            if qs.exists():
                raise serializers.ValidationError('duplicate')
        return value

    def validate_office_email(self, value):
        value = value.lower().strip()
        fpo_id = self.context.get('fpo_id')
        qs = FPO.objects.filter(office_email=value)
        if fpo_id:
            qs = qs.exclude(pk=fpo_id)
        if qs.exists():
            raise serializers.ValidationError('duplicate')
        return value


# =============================================================================
# FPO STEP 3 — SIGNATORY & MEMBERS
# =============================================================================

class FPOStep3Serializer(serializers.Serializer):
    """Step 3 — Signatory & Members."""

    signatory_name          = serializers.CharField(max_length=255)
    signatory_designation   = serializers.CharField(max_length=100)
    signatory_phone         = serializers.CharField(max_length=10)
    signatory_email         = serializers.EmailField()
    signatory_aadhaar_last4 = serializers.CharField(max_length=4, min_length=4, help_text='Last 4 digits of Aadhaar')
    total_members           = serializers.IntegerField(min_value=10, help_text='Minimum 10 members required')
    male_members            = serializers.IntegerField(min_value=0)
    female_members          = serializers.IntegerField(min_value=0)
    sc_st_members           = serializers.IntegerField(min_value=0, required=False, allow_null=True)

    def validate_signatory_aadhaar_last4(self, value):
        if not value.isdigit():
            raise serializers.ValidationError('Must be exactly 4 digits.')
        return value

    def validate_signatory_phone(self, value):
        import re
        if not re.match(r'^[6-9]\d{9}$', value):
            raise serializers.ValidationError('Enter a valid 10-digit Indian mobile number.')
        return value

    def validate(self, attrs):
        total  = attrs.get('total_members', 0)
        male   = attrs.get('male_members', 0)
        female = attrs.get('female_members', 0)
        if male + female > total:
            raise serializers.ValidationError(
                'Sum of male and female members cannot exceed total members.'
            )
        return attrs


# =============================================================================
# FPO STEP 4 — BUSINESS DETAILS
# =============================================================================

class FPOStep4Serializer(serializers.Serializer):
    """Step 4 — Business Details."""

    primary_commodities   = serializers.ListField(
        child=serializers.CharField(), min_length=1,
        help_text='List of primary commodities'
    )
    secondary_commodities = serializers.ListField(
        child=serializers.CharField(), required=False, default=list,
        help_text='List of secondary commodities (optional)'
    )
    annual_turnover = serializers.DecimalField(
        max_digits=15, decimal_places=2,
        required=False, allow_null=True,
        help_text='Annual turnover in INR (optional)'
    )
    bank_name      = serializers.CharField(max_length=100)
    bank_branch    = serializers.CharField(max_length=100)
    account_number = serializers.CharField(max_length=18, help_text='9-18 digit account number')
    ifsc_code      = serializers.CharField(max_length=11, help_text='Format: AAAA0AAAAAA')
    description    = serializers.CharField(required=False, allow_blank=True, help_text='Optional description (bilingual)')

    def validate_account_number(self, value):
        if not value.isdigit() or not (9 <= len(value) <= 18):
            raise serializers.ValidationError('Account number must be 9-18 digits.')
        return value

    def validate_ifsc_code(self, value):
        import re
        value = value.upper().strip()
        if not re.match(r'^[A-Z]{4}0[A-Z0-9]{6}$', value):
            raise serializers.ValidationError('Invalid IFSC code format. Expected: AAAA0AAAAAA')
        return value


# =============================================================================
# FPO READ SERIALIZER — GET /api/fpo/me/
# =============================================================================

class FPODetailSerializer(serializers.ModelSerializer):
    """Full FPO profile — returned on GET /api/fpo/me/"""

    status_display       = serializers.CharField(source='get_status_display', read_only=True)
    district_display     = serializers.CharField(source='get_district_display', read_only=True)
    registered_under_display = serializers.CharField(source='get_registered_under_display', read_only=True)
    current_tier         = serializers.SerializerMethodField()
    required_docs_uploaded  = serializers.SerializerMethodField()
    required_docs_verified  = serializers.SerializerMethodField()
    submission_errors    = serializers.SerializerMethodField()

    class Meta:
        model  = FPO
        fields = [
            'id', 'uuid', 'application_id', 'status', 'status_display',
            'current_step', 'current_tier',
            # Step 1
            'name', 'name_ml', 'registration_number', 'cin_number',
            'date_of_registration', 'registered_under', 'registered_under_display',
            'pan_number', 'gst_number',
            # Step 2
            'district', 'district_display', 'block_taluk', 'village_town',
            'address_line1', 'address_line2', 'pincode',
            'office_phone', 'office_email', 'website', 'email_verified', 'phone_verified',
            'latitude', 'longitude',
            # Step 3
            'signatory_name', 'signatory_designation', 'signatory_phone',
            'signatory_email', 'signatory_aadhaar_last4',
            'total_members', 'male_members', 'female_members', 'sc_st_members',
            # Step 4
            'primary_commodities', 'secondary_commodities', 'annual_turnover',
            'bank_name', 'bank_branch', 'account_number', 'ifsc_code', 'description',
            # Meta
            'max_secondary_users', 'required_docs_uploaded',
            'required_docs_verified', 'submission_errors',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_current_tier(self, obj):
        return obj.current_tier

    @extend_schema_field(serializers.BooleanField())
    def get_required_docs_uploaded(self, obj):
        return obj.required_documents_uploaded

    @extend_schema_field(serializers.BooleanField())
    def get_required_docs_verified(self, obj):
        return obj.required_documents_verified

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_submission_errors(self, obj):
        return obj.get_submission_errors()


# =============================================================================
# STATUS TIMELINE SERIALIZER — GET /api/fpo/me/status/
# =============================================================================

class StatusHistorySerializer(serializers.ModelSerializer):
    """Single status change entry for the timeline."""

    changed_by_name = serializers.SerializerMethodField()

    class Meta:
        model  = ApplicationStatusHistory
        fields = ['id', 'from_status', 'to_status', 'changed_by_name', 'notes', 'created_at']

    @extend_schema_field(serializers.CharField())
    def get_changed_by_name(self, obj):
        if obj.changed_by:
            return obj.changed_by.get_full_name() or obj.changed_by.email
        return None


# =============================================================================
# FIELD VALIDATION SERIALIZER — POST /api/fpo/validate-field/
# =============================================================================

class FieldValidateSerializer(serializers.Serializer):
    """Per-field blur validation — real-time duplicate + format check."""

    SUPPORTED_FIELDS = [
        'pan_number', 'gst_number', 'cin_number', 'registration_number',
        'office_email', 'office_phone', 'ifsc_code', 'account_number', 'pincode',
    ]

    field = serializers.ChoiceField(
        choices=[(f, f) for f in SUPPORTED_FIELDS],
        help_text='Field name to validate'
    )
    value = serializers.CharField(help_text='Current field value')
