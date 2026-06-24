"""
Two-Factor Authentication API
==============================
Base Path: /api/auth/2fa/

TOTP-based 2FA for super_admin and sub_admin accounts.
Compatible with Google Authenticator and any TOTP app.

Flow:
  Setup   : POST /setup/         → get secret + QR code
            POST /verify-setup/  → confirm with first code → 2FA active + backup codes returned
  Login   : POST /login/verify/  → submit code + partial_token → full JWT issued
  Recovery: POST /login/backup/  → use backup code instead of TOTP
  Manage  : POST /disable/<id>/  → super admin disables 2FA for a user
            POST /regenerate-backup-codes/ → generate fresh backup codes
"""

import io
import base64
import secrets
import pyotp
import qrcode

from django.contrib.auth.models import User
from django.conf import settings as django_settings

from rest_framework import serializers
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken
from rest_framework_simplejwt.exceptions import TokenError
from drf_spectacular.utils import extend_schema, inline_serializer, OpenApiResponse

from apps.core.permissions.rbac import IsSuperAdmin, IsSubAdminOrSuperAdmin
from apps.core.utils.throttles import TwoFactorLoginThrottle, TwoFactorSetupThrottle, Disable2FAOTPThrottle
from apps.core.utils.constants import UserRole
from apps.core.utils.responses import StandardResponse
from apps.core.utils.cookies import set_jwt_cookies
from apps.core.utils.cache import set_cache, get_cache, delete_cache
from apps.core.services.translation import t
from apps.database.models import AdminTwoFactor

TWO_FACTOR_DISABLE_OTP_TTL = 10 * 60  # 10 minutes

ISSUER_NAME = "KAU-FPO"
PARTIAL_TOKEN_CLAIM = 'two_factor_pending'


def _mask_email(email: str) -> str:
    """at******@kefitech.com — show first 2 chars, mask middle, keep domain."""
    local, _, domain = email.partition('@')
    masked_local = local[:2] + '*' * max(len(local) - 2, 4)
    return f"{masked_local}@{domain}"


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _is_admin_user(user):
    return user.groups.filter(name__in=[UserRole.SUPER_ADMIN, UserRole.SUB_ADMIN]).exists()


def _generate_qr_base64(secret, email):
    uri = pyotp.totp.TOTP(secret).provisioning_uri(name=email, issuer_name=ISSUER_NAME)
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode()


def _issue_partial_token(user):
    """Issue a short-lived access token that only allows hitting /2fa/login/verify/ or /password/change/."""
    token = RefreshToken.for_user(user)
    token[PARTIAL_TOKEN_CLAIM] = True
    return str(token.access_token)


def _verify_partial_token(partial_token):
    """Validate a partial token and return the User, or None if invalid."""
    from django.contrib.auth.models import User as DjangoUser
    from rest_framework_simplejwt.exceptions import TokenError
    try:
        token = AccessToken(partial_token)
        if not token.get(PARTIAL_TOKEN_CLAIM):
            return None
        return DjangoUser.objects.get(pk=token['user_id'], is_active=True)
    except Exception:
        return None


def _verify_totp(two_factor, code):
    totp = pyotp.TOTP(two_factor.secret)
    # valid_window=0 → only the current 30s window accepted (strict).
    # pyotp handles minor clock drift internally.
    return totp.verify(code, valid_window=0)


# ─── Request Serializers ──────────────────────────────────────────────────────

class TwoFactorCodeSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=6, min_length=6, help_text="6-digit TOTP code from Google Authenticator")


class TwoFactorLoginVerifySerializer(serializers.Serializer):
    partial_token = serializers.CharField(help_text="partial_token received from login response")
    code          = serializers.CharField(max_length=6, min_length=6, help_text="6-digit TOTP code from Google Authenticator")


class TwoFactorLoginBackupSerializer(serializers.Serializer):
    partial_token = serializers.CharField(help_text="partial_token received from login response")
    backup_code   = serializers.CharField(help_text="One-time backup code (format: XXXXXXXXXX)")


# ─── Response Serializers ─────────────────────────────────────────────────────

class TwoFactorSetupResponseSerializer(serializers.Serializer):
    secret       = serializers.CharField()
    qr_code      = serializers.CharField(help_text="Base64-encoded PNG QR code — display as <img src='data:image/png;base64,...'>")
    instructions = serializers.CharField()


class TwoFactorVerifySetupResponseSerializer(serializers.Serializer):
    backup_codes = serializers.ListField(child=serializers.CharField())
    warning      = serializers.CharField()


class TwoFactorStatusResponseSerializer(serializers.Serializer):
    is_enabled             = serializers.BooleanField()
    backup_codes_remaining = serializers.IntegerField()


class TwoFactorBackupCodesResponseSerializer(serializers.Serializer):
    backup_codes = serializers.ListField(child=serializers.CharField())
    warning      = serializers.CharField()


# ─── Setup ───────────────────────────────────────────────────────────────────

class TwoFactorSetupView(APIView):
    """
    Generate a TOTP secret and QR code for the authenticated admin.
    Does NOT enable 2FA yet — admin must verify with first code via /verify-setup/.
    """
    throttle_classes = [TwoFactorSetupThrottle]
    permission_classes = [IsSubAdminOrSuperAdmin]

    @extend_schema(
        tags=['Authentication - 2FA'],
        request=None,
        responses={200: TwoFactorSetupResponseSerializer},
        summary="Initiate 2FA setup — get secret and QR code",
    )
    def post(self, request):
        lang = getattr(request, 'language', 'en')
        user = request.user

        two_factor, _ = AdminTwoFactor.objects.get_or_create(
            user=user,
            defaults={'secret': pyotp.random_base32(), 'is_enabled': False}
        )

        if two_factor.is_enabled:
            return StandardResponse.error(
                message=t('auth.two_factor_already_enabled', lang), status_code=400
            )

        two_factor.secret = pyotp.random_base32()
        two_factor.save(update_fields=['secret'])

        return StandardResponse.success(
            data={
                'secret': two_factor.secret,
                'qr_code': _generate_qr_base64(two_factor.secret, user.email),
                'instructions': 'Scan the QR code with Google Authenticator, then call /verify-setup/ with the first code.',
            },
            message=t('auth.two_factor_setup_initiated', lang),
        )


class TwoFactorVerifySetupView(APIView):
    """
    Confirm 2FA setup by submitting the first TOTP code.
    On success: 2FA is enabled and backup codes are returned — shown once only.
    """
    permission_classes = [IsSubAdminOrSuperAdmin]

    @extend_schema(
        tags=['Authentication - 2FA'],
        request=TwoFactorCodeSerializer,
        responses={200: TwoFactorVerifySetupResponseSerializer},
        summary="Confirm 2FA setup with first TOTP code — activates 2FA and returns backup codes",
    )
    def post(self, request):
        lang = getattr(request, 'language', 'en')
        serializer = TwoFactorCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        code = serializer.validated_data['code']

        try:
            two_factor = AdminTwoFactor.objects.get(user=request.user)
        except AdminTwoFactor.DoesNotExist:
            return StandardResponse.error(
                message=t('auth.two_factor_not_initiated', lang), status_code=400
            )

        if two_factor.is_enabled:
            return StandardResponse.error(
                message=t('auth.two_factor_already_enabled', lang), status_code=400
            )

        if not _verify_totp(two_factor, code):
            return StandardResponse.error(
                message=t('auth.two_factor_invalid_code', lang), status_code=400
            )

        backup_codes = two_factor.generate_backup_codes()
        two_factor.is_enabled = True
        two_factor.save(update_fields=['is_enabled', 'backup_codes'])

        return StandardResponse.success(
            data={
                'backup_codes': backup_codes,
                'warning': 'Save these backup codes now. They will not be shown again.',
            },
            message=t('auth.two_factor_enabled', lang),
        )


# ─── Login verification ───────────────────────────────────────────────────────

class TwoFactorLoginVerifyView(APIView):
    """
    Verify TOTP code during login.
    Send the partial_token from the login response + 6-digit code → full JWT issued.
    """
    permission_classes = []
    throttle_classes   = [TwoFactorLoginThrottle]

    @extend_schema(
        tags=['Authentication - 2FA'],
        request=TwoFactorLoginVerifySerializer,
        responses={200: inline_serializer('TwoFactorLoginResponse', fields={'access': serializers.CharField(required=False)})},
        summary="Complete login with TOTP code — returns full JWT",
    )
    def post(self, request):
        lang = getattr(request, 'language', 'en')
        serializer = TwoFactorLoginVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        partial_token = serializer.validated_data['partial_token']
        code          = serializer.validated_data['code']

        try:
            token = AccessToken(partial_token)
            if not token.get(PARTIAL_TOKEN_CLAIM):
                raise TokenError('Not a partial token')
            user = User.objects.get(id=token['user_id'])
        except (TokenError, User.DoesNotExist):
            return StandardResponse.error(
                message=t('auth.token_invalid', lang), status_code=401
            )

        try:
            two_factor = AdminTwoFactor.objects.get(user=user, is_enabled=True)
        except AdminTwoFactor.DoesNotExist:
            return StandardResponse.error(
                message=t('auth.two_factor_not_enabled', lang), status_code=400
            )

        if not _verify_totp(two_factor, code):
            return StandardResponse.error(
                message=t('auth.two_factor_invalid_code', lang), status_code=400
            )

        refresh = RefreshToken.for_user(user)
        response = StandardResponse.success(
            data={'access': str(refresh.access_token)} if django_settings.DEBUG else {},
            message=t('auth.login_success', lang),
        )
        set_jwt_cookies(response, refresh)
        return response


class TwoFactorLoginBackupView(APIView):
    """
    Use a one-time backup code during login instead of TOTP.
    Send the partial_token from the login response + backup_code → full JWT issued.
    """
    permission_classes = []
    throttle_classes   = [TwoFactorLoginThrottle]

    @extend_schema(
        tags=['Authentication - 2FA'],
        request=TwoFactorLoginBackupSerializer,
        responses={200: inline_serializer('TwoFactorBackupLoginResponse', fields={'access': serializers.CharField(required=False)})},
        summary="Complete login with backup code — returns full JWT",
    )
    def post(self, request):
        lang = getattr(request, 'language', 'en')
        serializer = TwoFactorLoginBackupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        partial_token = serializer.validated_data['partial_token']
        backup_code   = serializer.validated_data['backup_code']

        try:
            token = AccessToken(partial_token)
            if not token.get(PARTIAL_TOKEN_CLAIM):
                raise TokenError('Not a partial token')
            user = User.objects.get(id=token['user_id'])
        except (TokenError, User.DoesNotExist):
            return StandardResponse.error(
                message=t('auth.token_invalid', lang), status_code=401
            )

        try:
            two_factor = AdminTwoFactor.objects.get(user=user, is_enabled=True)
        except AdminTwoFactor.DoesNotExist:
            return StandardResponse.error(
                message=t('auth.two_factor_not_enabled', lang), status_code=400
            )

        if not two_factor.use_backup_code(backup_code):
            return StandardResponse.error(
                message=t('auth.two_factor_invalid_backup_code', lang), status_code=400
            )

        refresh = RefreshToken.for_user(user)
        response = StandardResponse.success(
            data={'access': str(refresh.access_token)} if django_settings.DEBUG else {},
            message=t('auth.login_success', lang),
        )
        set_jwt_cookies(response, refresh)
        return response


# ─── Management ──────────────────────────────────────────────────────────────

class TwoFactorStatusView(APIView):
    """Get current 2FA status for the authenticated admin."""
    permission_classes = [IsSubAdminOrSuperAdmin]

    @extend_schema(
        tags=['Authentication - 2FA'],
        responses={200: TwoFactorStatusResponseSerializer},
        summary="Get 2FA status for current user",
    )
    def get(self, request):
        lang = getattr(request, 'language', 'en')
        try:
            two_factor = AdminTwoFactor.objects.get(user=request.user)
            data = {
                'is_enabled': two_factor.is_enabled,
                'backup_codes_remaining': len(two_factor.backup_codes),
            }
        except AdminTwoFactor.DoesNotExist:
            data = {'is_enabled': False, 'backup_codes_remaining': 0}

        return StandardResponse.success(
            data=data,
            message=t('auth.two_factor_status_retrieved', lang),
        )


class TwoFactorRegenerateBackupCodesView(APIView):
    """Regenerate backup codes — invalidates existing ones. Requires current TOTP code."""
    permission_classes = [IsSubAdminOrSuperAdmin]

    @extend_schema(
        tags=['Authentication - 2FA'],
        request=TwoFactorCodeSerializer,
        responses={200: TwoFactorBackupCodesResponseSerializer},
        summary="Regenerate backup codes (requires current TOTP code)",
    )
    def post(self, request):
        lang = getattr(request, 'language', 'en')
        serializer = TwoFactorCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        code = serializer.validated_data['code']

        try:
            two_factor = AdminTwoFactor.objects.get(user=request.user, is_enabled=True)
        except AdminTwoFactor.DoesNotExist:
            return StandardResponse.error(
                message=t('auth.two_factor_not_enabled', lang), status_code=400
            )

        if not _verify_totp(two_factor, code):
            return StandardResponse.error(
                message=t('auth.two_factor_invalid_code', lang), status_code=400
            )

        backup_codes = two_factor.generate_backup_codes()
        two_factor.save(update_fields=['backup_codes'])

        return StandardResponse.success(
            data={
                'backup_codes': backup_codes,
                'warning': 'Old backup codes are now invalid. Save these now.',
            },
            message=t('auth.two_factor_backup_codes_regenerated', lang),
        )


class TwoFactorDisableRequestOTPView(APIView):
    """
    POST /api/auth/2fa/disable/request-otp/

    Recovery step — sends a 6-digit OTP to the user's registered email.
    Works both pre-login (partial_token) and post-login (authenticated session).
    OTP is valid for 10 minutes.
    """
    permission_classes = [AllowAny]
    throttle_classes   = [Disable2FAOTPThrottle]

    @extend_schema(
        tags=['Authentication - 2FA'],
        request=inline_serializer('TwoFactorDisableOTPRequest', fields={
            'partial_token': serializers.CharField(
                required=False,
                help_text='Partial token from login response (pre-login flow). Omit if already logged in.'
            ),
        }),
        responses={200: inline_serializer('TwoFactorDisableOTPResponse', fields={})},
        summary="Request email OTP to disable 2FA (recovery)",
        description=(
            "Sends a 6-digit OTP to the user's registered email address.\n\n"
            "**Pre-login:** pass `partial_token` from the login response.\n\n"
            "**Already logged in:** no body needed — uses the authenticated session.\n\n"
            "OTP is valid for 10 minutes. "
            "Then call POST /api/auth/2fa/disable/ with `email_otp`."
        ),
    )
    def post(self, request):
        from apps.notifications.services import send_notification

        lang          = getattr(request, 'language', 'en')
        partial_token = request.data.get('partial_token', '').strip()

        # Resolve user — from partial_token (pre-login) or authenticated session
        if partial_token:
            user = _verify_partial_token(partial_token)
            if not user:
                return StandardResponse.error(
                    message=t('auth.invalid_or_expired_token', lang), status_code=400
                )
        elif request.user and request.user.is_authenticated:
            user = request.user
        else:
            return StandardResponse.error(
                message="Provide a partial_token or log in first.", status_code=400
            )

        try:
            AdminTwoFactor.objects.get(user=user, is_enabled=True)
        except AdminTwoFactor.DoesNotExist:
            return StandardResponse.error(
                message=t('auth.two_factor_not_enabled', lang), status_code=400
            )

        otp       = str(secrets.randbelow(900000) + 100000)
        cache_key = f"2fa_disable_otp:{user.id}"
        set_cache(cache_key, otp, TWO_FACTOR_DISABLE_OTP_TTL)

        try:
            send_notification(
                user=user,
                code='two_factor_otp',
                channel='email',
                context={'user_name': user.first_name or user.username, 'otp': otp},
                lang=lang,
            )
        except Exception:
            pass

        return StandardResponse.success(
            message=f'A 6-digit OTP has been sent to {_mask_email(user.email)}. Valid for 10 minutes.',
        )


class TwoFactorSelfDisableView(APIView):
    """
    POST /api/auth/2fa/disable/

    Disables 2FA. Works both pre-login (partial_token) and post-login.

    - Logged in + has authenticator : { "code": "123456" }
    - Logged in + lost phone        : { "email_otp": "123456" }
    - Pre-login recovery            : { "partial_token": "...", "email_otp": "123456" }
      → On success, frontend redirects to login (user logs in normally, no 2FA prompt)
    """
    permission_classes = [AllowAny]
    throttle_classes   = [Disable2FAOTPThrottle]

    @extend_schema(
        tags=['Authentication - 2FA'],
        request=inline_serializer('TwoFactorSelfDisableRequest', fields={
            'code':          serializers.CharField(required=False, help_text='TOTP from authenticator app (logged-in only)'),
            'email_otp':     serializers.CharField(required=False, help_text='OTP received via email after calling /disable/request-otp/'),
            'partial_token': serializers.CharField(required=False, help_text='Partial token from login response (pre-login recovery)'),
        }),
        responses={200: inline_serializer('TwoFactorSelfDisableResponse', fields={})},
        summary="Disable your own 2FA",
        description=(
            "Disables 2FA for the user. Three supported flows:\n\n"
            "**1. Normal (logged in)** — `{ \"code\": \"123456\" }` TOTP from authenticator.\n\n"
            "**2. Recovery (logged in)** — `{ \"email_otp\": \"123456\" }` after calling `/disable/request-otp/`.\n\n"
            "**3. Recovery (pre-login)** — `{ \"partial_token\": \"...\", \"email_otp\": \"123456\" }` "
            "when locked out at the 2FA screen. On success, frontend redirects to login — user logs in normally (no 2FA prompt this time)."
        ),
    )
    def post(self, request):
        lang          = getattr(request, 'language', 'en')
        totp_code     = request.data.get('code', '').strip()
        email_otp     = request.data.get('email_otp', '').strip()
        partial_token = request.data.get('partial_token', '').strip()

        # Resolve user
        if partial_token:
            user = _verify_partial_token(partial_token)
            if not user:
                return StandardResponse.error(
                    message=t('auth.invalid_or_expired_token', lang), status_code=400
                )
        elif request.user and request.user.is_authenticated:
            user = request.user
        else:
            return StandardResponse.error(
                message="Provide a partial_token or log in first.", status_code=400
            )

        if not totp_code and not email_otp:
            return StandardResponse.error(
                message="Provide either 'code' (TOTP) or 'email_otp' (recovery OTP).",
                status_code=400,
            )

        try:
            two_factor = AdminTwoFactor.objects.get(user=user, is_enabled=True)
        except AdminTwoFactor.DoesNotExist:
            return StandardResponse.error(
                message=t('auth.two_factor_not_enabled', lang), status_code=400
            )

        if totp_code:
            if not _verify_totp(two_factor, totp_code):
                return StandardResponse.error(
                    message=t('auth.two_factor_invalid_code', lang), status_code=400
                )
        else:
            cache_key  = f"2fa_disable_otp:{user.id}"
            cached_otp = get_cache(cache_key)
            if not cached_otp or cached_otp != email_otp:
                return StandardResponse.error(
                    message='Invalid or expired OTP. Request a new one via /disable/request-otp/.',
                    status_code=400,
                )
            delete_cache(cache_key)

        two_factor.is_enabled   = False
        two_factor.secret       = ''
        two_factor.backup_codes = []
        two_factor.save(update_fields=['is_enabled', 'secret', 'backup_codes'])

        return StandardResponse.success(
            message=t('auth.two_factor_disabled', lang),
        )


class TwoFactorDisableView(APIView):
    """
    Super admin disables 2FA for any admin user.
    Used when a sub-admin loses their phone and is locked out.
    """
    permission_classes = [IsSuperAdmin]

    @extend_schema(
        tags=['Authentication - 2FA'],
        request=None,
        responses={200: inline_serializer('TwoFactorDisableResponse', fields={})},
        summary="Disable 2FA for a user (super_admin only — for account recovery)",
    )
    def post(self, request, user_id):
        lang = getattr(request, 'language', 'en')

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return StandardResponse.error(
                message=t('common.not_found', lang), status_code=404
            )

        try:
            two_factor = AdminTwoFactor.objects.get(user=user)
            two_factor.is_enabled = False
            two_factor.secret = ''
            two_factor.backup_codes = []
            two_factor.save()
        except AdminTwoFactor.DoesNotExist:
            pass

        return StandardResponse.success(
            message=t('auth.two_factor_disabled', lang),
        )
