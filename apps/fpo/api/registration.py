"""
FPO Registration APIs
=====================
Eligibility check, 4-step wizard, status timeline, field validation.

Endpoints:
    POST   /api/fpo/eligibility-check/
    POST   /api/fpo/pre-register/send-otp/
    POST   /api/fpo/pre-register/verify-otp/
    POST   /api/fpo/register/
    GET    /api/fpo/me/
    PATCH  /api/fpo/me/
    GET    /api/fpo/me/status/
    POST   /api/fpo/validate-field/
"""

import re
import secrets

from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView

from apps.core.permissions.rbac import IsFPOManager
from apps.core.utils.constants import FPOStatus, can_transition_fpo_status
from apps.core.utils.validators import validate_indian_phone
from apps.core.utils.responses import StandardResponse
from apps.core.services.audit import AuditService
from apps.core.models.generic import AuditLog
from apps.database.models.fpo import FPO, ApplicationStatusHistory
from apps.database.models import UserProfile
from apps.notifications.services import send_notification

from rest_framework import serializers as drf_serializers

from .serializers import (
    EligibilityCheckSerializer,
    FieldValidateSerializer,
    FPODetailSerializer,
    FPOStep1Serializer,
    FPOStep2Serializer,
    FPOStep3Serializer,
    FPOStep4Serializer,
    StatusHistorySerializer,
)

STEP_SERIALIZER_MAP = {
    1: FPOStep1Serializer,
    2: FPOStep2Serializer,
    3: FPOStep3Serializer,
    4: FPOStep4Serializer,
}

STEP_FIELDS_MAP = {
    1: [
        'name', 'name_ml', 'legal_structure', 'legal_structure_detail',
        'registration_number', 'cin_number',
        'date_of_registration', 'pan_number', 'gst_number',
    ],
    2: [
        'district', 'block_taluk', 'village_town', 'address_line1',
        'address_line2', 'pincode', 'office_phone', 'office_email',
        'website', 'latitude', 'longitude',
    ],
    3: [
        'signatory_name', 'signatory_designation', 'signatory_phone',
        'signatory_email', 'signatory_aadhaar_last4', 'total_members',
        'male_members', 'female_members', 'sc_st_members',
        'promoting_agency', 'facilitating_agency_name',
        'ceo_available', 'accountant_available',
        'total_directors', 'women_directors', 'directors_under_35',
    ],
    4: [
        'primary_commodities', 'secondary_commodities', 'annual_turnover',
        'bank_name', 'bank_branch', 'account_number', 'ifsc_code', 'description',
    ],
}


class _FPOWizardPatchSerializer(drf_serializers.Serializer):
    """Swagger-only: shows all possible fields for PATCH /api/fpo/me/ steps 1-4."""
    step = drf_serializers.IntegerField(help_text='Which step to save: 1, 2, 3, or 4')
    # Step 1
    name                   = drf_serializers.CharField(required=False)
    name_ml                = drf_serializers.CharField(required=False)
    legal_structure        = drf_serializers.CharField(required=False, help_text="From /api/public/master-data/?category=legal_structure")
    legal_structure_detail = drf_serializers.CharField(required=False, help_text="State CSA act name when legal_structure='state_specific_csa'")
    registration_number    = drf_serializers.CharField(required=False)
    cin_number             = drf_serializers.CharField(required=False)
    date_of_registration   = drf_serializers.DateField(required=False)
    pan_number             = drf_serializers.CharField(required=False)
    gst_number             = drf_serializers.CharField(required=False)
    # Step 2
    district       = drf_serializers.CharField(required=False, help_text='3-letter district code e.g. TRS')
    block_taluk    = drf_serializers.CharField(required=False, help_text='Block name from /api/public/master-data/?category=block&district=<code>')
    village_town   = drf_serializers.CharField(required=False)
    address_line1  = drf_serializers.CharField(required=False)
    address_line2  = drf_serializers.CharField(required=False)
    pincode        = drf_serializers.CharField(required=False)
    office_phone   = drf_serializers.CharField(required=False)
    office_email   = drf_serializers.EmailField(required=False)
    website        = drf_serializers.URLField(required=False)
    latitude       = drf_serializers.DecimalField(max_digits=9, decimal_places=6, required=False)
    longitude      = drf_serializers.DecimalField(max_digits=9, decimal_places=6, required=False)
    # Step 3
    signatory_name           = drf_serializers.CharField(required=False)
    signatory_designation    = drf_serializers.CharField(required=False, help_text="From /api/public/master-data/?category=signatory_designation")
    signatory_phone          = drf_serializers.CharField(required=False)
    signatory_email          = drf_serializers.EmailField(required=False)
    signatory_aadhaar_last4  = drf_serializers.CharField(required=False)
    total_members            = drf_serializers.IntegerField(required=False)
    male_members             = drf_serializers.IntegerField(required=False)
    female_members           = drf_serializers.IntegerField(required=False)
    sc_st_members            = drf_serializers.IntegerField(required=False)
    promoting_agency         = drf_serializers.CharField(required=False, help_text="From /api/public/master-data/?category=promoting_agency")
    facilitating_agency_name = drf_serializers.CharField(required=False)
    ceo_available            = drf_serializers.BooleanField(required=False)
    accountant_available     = drf_serializers.BooleanField(required=False)
    total_directors          = drf_serializers.IntegerField(required=False)
    women_directors          = drf_serializers.IntegerField(required=False)
    directors_under_35       = drf_serializers.IntegerField(required=False)
    # Step 4
    primary_commodities   = drf_serializers.ListField(child=drf_serializers.CharField(), required=False)
    secondary_commodities = drf_serializers.ListField(child=drf_serializers.CharField(), required=False)
    annual_turnover       = drf_serializers.DecimalField(max_digits=15, decimal_places=2, required=False, help_text='Annual turnover in Lakhs (INR)')
    bank_name             = drf_serializers.CharField(required=False, help_text='From /api/public/master-data/?category=bank_name')
    bank_branch           = drf_serializers.CharField(required=False)
    account_number        = drf_serializers.CharField(required=False)
    ifsc_code             = drf_serializers.CharField(required=False)
    description           = drf_serializers.CharField(required=False)


# =============================================================================
# ELIGIBILITY CHECK
# =============================================================================

class EligibilityCheckView(APIView):
    """
    POST /api/fpo/eligibility-check/

    Pre-registration eligibility check (RCD 4.2.1).
    No login required. Must pass before registration form is shown.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["FPO - Registration"],
        summary="Eligibility Check",
        description=(
            "Pre-registration eligibility check. "
            "All criteria must pass before the registration form is shown. "
            "No authentication required."
        ),
        request=EligibilityCheckSerializer,
        responses={
            200: OpenApiResponse(description="Eligibility result"),
        },
    )
    def post(self, request):
        serializer = EligibilityCheckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        errors = []

        if data['member_count'] < 10:
            errors.append('FPO must have a minimum of 10 farmer members.')

        if not data['registered_under_act']:
            errors.append('FPO must be registered under a relevant Act.')

        if not data['has_valid_registration']:
            errors.append('FPO must have a valid registration number.')

        if not data['has_bank_account']:
            errors.append('FPO must have an active bank account.')

        eligible = len(errors) == 0

        response_data = {
            'eligible': eligible,
            'errors':   errors,
            'district': data['district'],
        }

        if eligible:
            token = secrets.token_urlsafe(32)
            cache.set(f'fpo:eligibility_token:{token}', data['district'], 1800)  # 30 min
            response_data['eligibility_token'] = token

        return StandardResponse.success(
            data=response_data,
            message='Eligibility check passed.' if eligible else 'Eligibility check failed.',
        )


# =============================================================================
# PRE-REGISTRATION PHONE OTP
# =============================================================================

class PreRegisterSendOTPView(APIView):
    """
    POST /api/fpo/pre-register/send-otp/

    Sends a 6-digit OTP to the given phone number before account creation.
    Proves the user has a real Indian mobile number.
    No authentication required.
    Rate limited: 3 sends per 10 minutes per phone number.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        tags=['FPO - Registration'],
        summary='Send phone OTP for pre-registration verification',
        description=(
            'Send a 6-digit OTP to a phone number before account creation. '
            'Rate limited to 3 sends per 10 minutes. '
            'No authentication required.'
        ),
        request=None,
        responses={200: None, 400: None, 429: None},
    )
    def post(self, request):
        phone = request.data.get('phone', '').strip()
        if not phone:
            return StandardResponse.error(
                'Phone number is required.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            validate_indian_phone(phone)
        except DjangoValidationError as e:
            return StandardResponse.error(str(e), status_code=status.HTTP_400_BAD_REQUEST)

        if UserProfile.objects.filter(phone=phone).exists():
            return StandardResponse.error(
                'An account with this phone number already exists.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        count_key = f'fpo:prereg_otp_count:{phone}'
        otp_key   = f'fpo:prereg_otp:{phone}'
        _OTP_TTL  = 600  # 10 min
        _MAX_SENDS = 3

        count = cache.get(count_key, 0)
        if count >= _MAX_SENDS:
            return StandardResponse.error(
                'Too many OTP requests. Please wait 10 minutes before trying again.',
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        otp = str(secrets.randbelow(900000) + 100000)
        cache.set(otp_key, otp, _OTP_TTL)
        if count == 0:
            cache.set(count_key, 1, _OTP_TTL)
        else:
            cache.incr(count_key)

        try:
            send_notification(
                user=None,
                code='mobile_verification',
                channel='sms',
                context={'otp': otp},
                override_recipient=phone,
            )
        except Exception:
            pass

        return StandardResponse.success(
            data={'phone': _mask_phone(phone)},
            message='OTP sent to your mobile number.',
        )


class PreRegisterVerifyOTPView(APIView):
    """
    POST /api/fpo/pre-register/verify-otp/

    Verifies the OTP sent to the phone number.
    On success returns a one-time phone_token (30 min TTL) required at registration.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        tags=['FPO - Registration'],
        summary='Verify phone OTP for pre-registration',
        description='Submit the 6-digit OTP. On success returns a phone_token required at POST /api/auth/register/.',
        request=None,
        responses={200: None, 400: None},
    )
    def post(self, request):
        phone = request.data.get('phone', '').strip()
        otp   = request.data.get('otp', '').strip()

        if not phone or not otp:
            return StandardResponse.error(
                'phone and otp are required.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        _MAX_ATTEMPTS = 3
        _OTP_TTL      = 600  # 10 min

        otp_key      = f'fpo:prereg_otp:{phone}'
        attempts_key = f'fpo:prereg_otp_attempts:{phone}'
        stored       = cache.get(otp_key)

        if not stored:
            return StandardResponse.error(
                'OTP has expired. Please request a new one.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if stored != otp:
            attempts = cache.get(attempts_key, 0) + 1
            remaining = max(0, _MAX_ATTEMPTS - attempts)
            if remaining == 0:
                cache.delete(otp_key)
                cache.delete(attempts_key)
                return StandardResponse.error(
                    'Maximum attempts reached. Please request a new OTP.',
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            cache.set(attempts_key, attempts, _OTP_TTL)
            return StandardResponse.error(
                f'Incorrect OTP. {remaining} attempt(s) remaining. OTP is valid for 10 minutes.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        cache.delete(otp_key)
        cache.delete(attempts_key)
        cache.delete(f'fpo:prereg_otp_count:{phone}')

        phone_token = secrets.token_urlsafe(32)
        cache.set(f'fpo:prereg_phone_token:{phone_token}', phone, 1800)  # 30 min

        return StandardResponse.success(
            data={'phone_token': phone_token},
            message='Phone number verified successfully.',
        )


def _mask_phone(phone: str) -> str:
    if len(phone) <= 4:
        return phone
    return '•' * (len(phone) - 4) + phone[-4:]


# =============================================================================
# FPO REGISTER — STEP 1
# =============================================================================

class FPORegisterView(APIView):
    """
    POST /api/fpo/register/

    Creates FPO in DRAFT status with Step 1 (Basic Info) data.
    One FPO per user (BR-002). Duplicate detection on pan, gst, cin, reg number.
    If duplicate found → response includes duplicate_detected: true so frontend
    can show the "Claim Your Business" option.
    """

    permission_classes = [IsAuthenticated, IsFPOManager]

    @extend_schema(
        tags=["FPO - Registration"],
        summary="Start FPO Registration (Step 1)",
        description=(
            "Creates FPO in DRAFT status with Step 1 basic info. "
            "One FPO per user account (BR-002). "
            "If a duplicate PAN/GST/CIN/registration number is found, "
            "response includes duplicate_detected: true — frontend shows 'Claim Your Business'."
        ),
        request=FPOStep1Serializer,
        responses={
            201: OpenApiResponse(description="FPO draft created"),
            400: OpenApiResponse(description="Validation error or duplicate detected"),
            409: OpenApiResponse(description="User already has an FPO"),
        },
    )
    def post(self, request):
        # BR-002: one FPO per user
        if FPO.objects.filter(primary_user=request.user).exists():
            return StandardResponse.error(
                'You already have an FPO registered. Use PATCH /api/fpo/me/ to update it.',
                status_code=status.HTTP_409_CONFLICT,
            )

        serializer = FPOStep1Serializer(data=request.data, context={'request': request})

        # Check for duplicates before full validation
        duplicate_field = self._check_duplicates(request.data)
        if duplicate_field:
            return StandardResponse.error(
                f'An FPO with this {duplicate_field} already exists. '
                'If this is your FPO, use the "Claim Your Business" option.',
                status_code=status.HTTP_400_BAD_REQUEST,
                data={
                    'duplicate_detected': True,
                    'duplicate_field':    duplicate_field,
                },
            )

        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        fpo = FPO.objects.create(
            primary_user           = request.user,
            created_by             = request.user,
            name                   = data['name'],
            name_ml                = data.get('name_ml', ''),
            legal_structure        = data['legal_structure'],
            legal_structure_detail = data.get('legal_structure_detail', ''),
            registration_number    = data.get('registration_number', ''),
            cin_number             = data.get('cin_number', ''),
            date_of_registration   = data['date_of_registration'],
            pan_number             = data['pan_number'],
            gst_number             = data.get('gst_number', ''),
            current_step           = 1,
            status                 = FPOStatus.DRAFT,
        )

        ApplicationStatusHistory.objects.create(
            fpo        = fpo,
            from_status = '',
            to_status   = FPOStatus.DRAFT,
            changed_by  = request.user,
            notes       = 'FPO registration started.',
        )

        AuditService.log(
            user=request.user,
            action=AuditLog.Action.CREATE,
            instance=fpo,
            request=request,
            changes={'name': fpo.name, 'legal_structure': fpo.legal_structure},
        )

        return StandardResponse.created(
            data=FPODetailSerializer(fpo).data,
            message='FPO registration started. Continue to Step 2.',
        )

    def _check_duplicates(self, data):
        fields = {
            'pan_number':          data.get('pan_number'),
            'gst_number':          data.get('gst_number'),
            'cin_number':          data.get('cin_number'),
            'registration_number': data.get('registration_number'),
        }
        for field, value in fields.items():
            if value and FPO.objects.filter(**{field: value}).exclude(
                status__in=[FPOStatus.CLAIMED, FPOStatus.DRAFT, FPOStatus.REJECTED]
            ).exists():
                return field
        return None


# =============================================================================
# FPO ME — GET + PATCH
# =============================================================================

class FPOMeView(APIView):
    """
    GET  /api/fpo/me/  — get current FPO profile
    PATCH /api/fpo/me/ — update wizard steps 2, 3, or 4
    """

    permission_classes = [IsAuthenticated, IsFPOManager]

    @extend_schema(
        tags=["FPO - Registration"],
        summary="Get FPO Profile",
        description="Returns the current user's FPO profile and wizard progress.",
        responses={
            200: OpenApiResponse(description="FPO profile"),
            404: OpenApiResponse(description="No FPO found for this user"),
        },
    )
    def get(self, request):
        fpo = self._get_fpo(request)
        if not fpo:
            return StandardResponse.error(
                'No FPO found. Start registration at POST /api/fpo/register/',
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return StandardResponse.success(
            data=FPODetailSerializer(fpo).data,
            message='FPO profile retrieved.',
        )

    @extend_schema(
        tags=["FPO - Registration"],
        summary="Update FPO Wizard (Steps 2-4)",
        description=(
            "Update FPO draft with step data. Send `step` field to indicate which step "
            "(2, 3, or 4). FPO must be in DRAFT or INFO_REQUIRED status (BR-007). "
            "Auto-saves — safe to call multiple times."
        ),
        request=_FPOWizardPatchSerializer,
        responses={
            200: OpenApiResponse(description="FPO updated"),
            400: OpenApiResponse(description="Validation error or invalid step"),
            403: OpenApiResponse(description="FPO not editable in current status"),
            404: OpenApiResponse(description="No FPO found"),
        },
    )
    def patch(self, request):
        fpo = self._get_fpo(request)
        if not fpo:
            return StandardResponse.error(
                'No FPO found. Start registration at POST /api/fpo/register/',
                status_code=status.HTTP_404_NOT_FOUND,
            )

        # BR-007: only editable in DRAFT or INFO_REQUIRED
        if fpo.status not in [FPOStatus.DRAFT, FPOStatus.INFO_REQUIRED]:
            return StandardResponse.error(
                f'FPO cannot be edited in {fpo.get_status_display()} status.',
                status_code=status.HTTP_403_FORBIDDEN,
            )

        step = request.data.get('step')
        if step not in [1, 2, 3, 4]:
            return StandardResponse.error(
                'Invalid step. Must be 1, 2, 3, or 4.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        SerializerClass = STEP_SERIALIZER_MAP[step]
        serializer = SerializerClass(
            data=request.data,
            context={'request': request, 'fpo_id': fpo.pk},
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Capture old values for audit before overwriting
        changes = {}
        for field in STEP_FIELDS_MAP[step]:
            if field in data:
                old_val = getattr(fpo, field, None)
                new_val = data[field]
                if old_val != new_val:
                    changes[field] = {'old': str(old_val) if old_val else '', 'new': str(new_val)}
                setattr(fpo, field, new_val)

        # BR-008: changing office_email/office_phone invalidates prior OTP verification
        if 'office_email' in changes and fpo.email_verified:
            fpo.email_verified = False
            changes['email_verified'] = {'old': 'True', 'new': 'False'}

        if 'office_phone' in changes and fpo.phone_verified:
            fpo.phone_verified = False
            changes['phone_verified'] = {'old': 'True', 'new': 'False'}

        # Advance wizard step if moving forward
        if step > fpo.current_step:
            fpo.current_step = step

        fpo.updated_by = request.user
        fpo.save()

        if changes:
            AuditService.log(
                user=request.user,
                action=AuditLog.Action.FPO_PROFILE_CHANGE,
                instance=fpo,
                request=request,
                changes=changes,
            )

        return StandardResponse.success(
            data=FPODetailSerializer(fpo).data,
            message=f'Step {step} saved successfully.',
        )

    def _get_fpo(self, request):
        return FPO.objects.filter(primary_user=request.user).first()


# =============================================================================
# FPO STATUS TIMELINE
# =============================================================================

class FPOStatusView(APIView):
    """
    GET /api/fpo/me/status/

    Returns current status + full application timeline.
    """

    permission_classes = [IsAuthenticated, IsFPOManager]

    @extend_schema(
        tags=["FPO - Registration"],
        summary="Application Status & Timeline",
        description="Returns current FPO status and full history of status changes.",
        responses={200: OpenApiResponse(description="Status and timeline")},
    )
    def get(self, request):
        fpo = FPO.objects.filter(primary_user=request.user).first()
        if not fpo:
            return StandardResponse.error(
                'No FPO found.',
                status_code=status.HTTP_404_NOT_FOUND,
            )

        history = fpo.status_history.all().order_by('created_at')

        return StandardResponse.success(
            data={
                'application_id': fpo.application_id or None,
                'status':         fpo.status,
                'status_display': fpo.get_status_display(),
                'current_tier':   fpo.current_tier,
                'timeline':       StatusHistorySerializer(history, many=True).data,
            },
            message='Application status retrieved.',
        )


# =============================================================================
# PER-FIELD BLUR VALIDATION
# =============================================================================

class FieldValidateView(APIView):
    """
    POST /api/fpo/validate-field/

    Real-time per-field validation on blur. Checks format + duplicate.
    Returns { valid, error, duplicate } so frontend can show inline errors.
    """

    permission_classes = [IsAuthenticated, IsFPOManager]

    @extend_schema(
        tags=["FPO - Registration"],
        summary="Validate Field",
        description=(
            "Real-time field validation on blur. "
            "Checks format correctness and duplicate detection. "
            "Supported fields: pan_number, gst_number, cin_number, registration_number, "
            "office_email, office_phone, ifsc_code, account_number, pincode."
        ),
        request=FieldValidateSerializer,
        responses={200: OpenApiResponse(description="Validation result")},
    )
    def post(self, request):
        serializer = FieldValidateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        field = serializer.validated_data['field']
        value = serializer.validated_data['value'].strip()

        # Empty value — nothing to validate (required-field check is done at submit time)
        if not value:
            return StandardResponse.success(
                data={'field': field, 'valid': True, 'error': None, 'duplicate': False},
                message='Validation complete.',
            )

        # Get current user's FPO id to exclude from duplicate check
        fpo = FPO.objects.filter(primary_user=request.user).first()
        fpo_id = fpo.pk if fpo else None

        valid, error, duplicate, existing_fpo_id = self._validate(field, value, fpo_id)

        return StandardResponse.success(
            data={
                'field':           field,
                'valid':           valid,
                'error':           error,
                'duplicate':       duplicate,
                'existing_fpo_id': existing_fpo_id,
            },
            message='Validation complete.',
        )

    def _validate(self, field, value, fpo_id):
        """Returns (valid, error_message, is_duplicate, existing_fpo_id)"""

        validators = {
            'pan_number':          self._validate_pan,
            'gst_number':          self._validate_gst,
            'cin_number':          self._validate_cin,
            'registration_number': self._validate_reg_number,
            'office_email':        self._validate_email,
            'office_phone':        self._validate_phone,
            'ifsc_code':           self._validate_ifsc,
            'account_number':      self._validate_account,
            'pincode':             self._validate_pincode,
        }

        fn = validators.get(field)
        if not fn:
            return False, 'Unsupported field.', False

        return fn(value, fpo_id)

    def _check_duplicate(self, field, value, fpo_id):
        qs = FPO.objects.filter(**{field: value}).exclude(status__in=[FPOStatus.CLAIMED, FPOStatus.DRAFT, FPOStatus.REJECTED])
        if fpo_id:
            qs = qs.exclude(pk=fpo_id)
        existing = qs.first()
        return (True, existing.id) if existing else (False, None)

    def _validate_pan(self, value, fpo_id):
        value = value.upper()
        if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]$', value):
            return False, 'Invalid PAN format. Expected: AAAAA9999A', False, None
        dup, dup_fpo_id = self._check_duplicate('pan_number', value, fpo_id)
        if dup:
            return False, 'An FPO with this PAN already exists.', True, dup_fpo_id
        return True, None, False, None

    def _validate_gst(self, value, fpo_id):
        value = value.upper()
        if not value.startswith('32'):
            return False, 'GST number must start with 32 for Kerala.', False, None
        if not re.match(r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$', value):
            return False, 'Invalid GST number format.', False, None
        dup, dup_fpo_id = self._check_duplicate('gst_number', value, fpo_id)
        if dup:
            return False, 'An FPO with this GST number already exists.', True, dup_fpo_id
        return True, None, False, None

    def _validate_cin(self, value, fpo_id):
        value = value.upper()
        if not re.match(r'^[A-Z]{1}[0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}$', value):
            return False, 'Invalid CIN format.', False, None
        dup, dup_fpo_id = self._check_duplicate('cin_number', value, fpo_id)
        if dup:
            return False, 'An FPO with this CIN already exists.', True, dup_fpo_id
        return True, None, False, None

    def _validate_reg_number(self, value, fpo_id):
        if not re.match(r'^[A-Za-z0-9/]+$', value):
            return False, 'Only alphanumeric characters and / are allowed.', False, None
        dup, dup_fpo_id = self._check_duplicate('registration_number', value, fpo_id)
        if dup:
            return False, 'An FPO with this registration number already exists.', True, dup_fpo_id
        return True, None, False, None

    def _validate_email(self, value, fpo_id):
        value = value.lower()
        if not re.match(r'^[^@]+@[^@]+\.[^@]+$', value):
            return False, 'Enter a valid email address.', False, None
        dup, dup_fpo_id = self._check_duplicate('office_email', value, fpo_id)
        if dup:
            return False, 'An FPO with this email already exists.', True, dup_fpo_id
        return True, None, False, None

    def _validate_phone(self, value, fpo_id):
        if not re.match(r'^[6-9]\d{9}$', value):
            return False, 'Enter a valid 10-digit Indian mobile number.', False, None
        dup, dup_fpo_id = self._check_duplicate('office_phone', value, fpo_id)
        if dup:
            return False, 'An FPO with this phone number already exists.', True, dup_fpo_id
        return True, None, False, None

    def _validate_ifsc(self, value, fpo_id):
        value = value.upper()
        if not re.match(r'^[A-Z]{4}0[A-Z0-9]{6}$', value):
            return False, 'Invalid IFSC code. Expected format: AAAA0AAAAAA', False, None
        return True, None, False, None

    def _validate_account(self, value, fpo_id):
        if not value.isdigit() or not (9 <= len(value) <= 18):
            return False, 'Account number must be 9-18 digits.', False, None
        qs = FPO.objects.filter(account_number=value).exclude(
            status__in=[FPOStatus.DRAFT, FPOStatus.REJECTED, FPOStatus.CLAIMED]
        )
        if fpo_id:
            qs = qs.exclude(pk=fpo_id)
        if qs.exists():
            dup = qs.first()
            return False, 'This bank account number is already registered with another FPO.', True, dup.pk
        return True, None, False, None

    def _validate_pincode(self, value, fpo_id):
        if not value.isdigit() or len(value) != 6 or not value.startswith('6'):
            return False, 'Pincode must be 6 digits starting with 6.', False, None
        return True, None, False, None
