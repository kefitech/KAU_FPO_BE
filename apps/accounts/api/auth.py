"""
KAU-FPO Platform - Authentication API
======================================

API endpoints for user authentication and registration.

Endpoints:
- POST /api/auth/register/super-admin/ - Register super admin account

Author: Athul Gopan
Created: 22-04-2026
"""

import secrets
import logging

from django.db import models

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import serializers as drf_serializers
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password

from apps.core.permissions.rbac import IsSuperAdminOrFirstUser, IsSuperAdmin, get_user_permissions
from apps.core.utils.throttles import (
    LoginThrottle, ForgotPasswordThrottle, OTPVerifyThrottle, RegisterThrottle,
)
from apps.core.utils.responses import StandardResponse
from apps.core.services.translation import t
from apps.core.utils.cookies import set_jwt_cookies, clear_jwt_cookies, get_refresh_token_from_cookie
from apps.core.models.generic import AuditLog
from apps.core.utils.pagination import StandardPagination
from apps.core.utils.cache import cache_key, set_cache, get_cache, delete_cache
from apps.core.utils.constants import (
    PASSWORD_RESET_EMAIL_TOKEN_TTL,
    PASSWORD_RESET_OTP_TTL,
    PASSWORD_RESET_TOKEN_TTL,
)
from apps.database.models import MenuItem, AdminTwoFactor, UserProfile
from apps.accounts.api.two_factor import _issue_partial_token, _is_admin_user
from .serializers import (
    RegisterSuperAdminSerializer, UserSerializer, LoginSerializer,
    LoginHistorySerializer, ForgotPasswordSerializer, VerifyOTPSerializer,
    ResetPasswordSerializer, ProfileUpdateSerializer, ChangePasswordSerializer,
    ChangeCurrentPasswordSerializer,
)

logger = logging.getLogger(__name__)
User = get_user_model()


# =============================================================================
# LOGIN LOCKOUT HELPERS (KAU RCD Reply, June 2026)
# =============================================================================
# 5 consecutive failures → account locked for 30 minutes
# Implemented via Redis keys — no migration needed.

_LOGIN_FAIL_TTL  = 30 * 60   # 30-minute window
_LOGIN_LOCK_TTL  = 30 * 60   # lock duration
_MAX_FAIL_COUNT  = 5


def _fail_key(identifier: str) -> str:
    return f'auth:failed_logins:{identifier.lower()}'


def _lock_key(user_id: int) -> str:
    return f'auth:account_locked:{user_id}'


def _increment_failed_login(identifier: str) -> None:
    from django.core.cache import cache
    from django.contrib.auth import get_user_model
    User = get_user_model()
    key   = _fail_key(identifier)
    count = cache.get(key, 0) + 1
    cache.set(key, count, timeout=_LOGIN_FAIL_TTL)
    # Lock the account if threshold reached
    user = User.objects.filter(
        models.Q(username=identifier) | models.Q(email=identifier)
    ).first()
    if user and count >= _MAX_FAIL_COUNT:
        cache.set(_lock_key(user.pk), True, timeout=_LOGIN_LOCK_TTL)


def _is_account_locked(user) -> bool:
    from django.core.cache import cache
    return bool(cache.get(_lock_key(user.pk)))


def _lock_remaining_minutes(user) -> int:
    """Return whole minutes remaining on the account lock (minimum 1)."""
    from django.core.cache import cache
    try:
        client = cache.client.get_client()
        versioned_key = cache.client.make_key(_lock_key(user.pk))
        ttl_seconds = client.ttl(versioned_key)
        if ttl_seconds and ttl_seconds > 0:
            return max(1, -(-ttl_seconds // 60))  # ceiling division
    except Exception:
        pass
    return _LOGIN_LOCK_TTL // 60  # fallback to full duration


def _clear_failed_login(user) -> None:
    from django.core.cache import cache
    cache.delete(_fail_key(user.username))
    cache.delete(_fail_key(user.email))
    cache.delete(_lock_key(user.pk))


def _get_user_role(user):
    """Return the highest-priority role name for a user."""
    priority = ['super_admin', 'sub_admin', 'fpo_manager', 'government', 'cbbo', 'expert', 'viewer']
    user_groups = set(user.groups.values_list('name', flat=True))
    for role in priority:
        if role in user_groups:
            return role
    return None


def _get_redirect(user, role):
    from apps.fpo.services.redirect import get_fpo_redirect
    return get_fpo_redirect(user)


def _build_menu(user, lang):
    """Return translated menu items the user is allowed to see."""
    user_groups = user.groups.all()

    top_level = MenuItem.objects.filter(
        parent=None,
        is_active=True,
        roles__in=user_groups,
    ).prefetch_related('children__roles', 'roles').order_by('order').distinct()

    def serialize_item(item):
        entry = {
            'label': t(item.label_key, language=lang),
            'path':  item.path,
            'icon':  item.icon,
        }
        active_children = [
            c for c in item.children.filter(is_active=True).order_by('order')
            if c.roles.filter(pk__in=user_groups).exists()
        ]
        if active_children:
            entry['children'] = [serialize_item(c) for c in active_children]
        return entry

    return [serialize_item(item) for item in top_level]


class RegisterSuperAdminView(APIView):
    """
    Register a new Super Admin account.

    Permissions:
    - First super_admin: No authentication required (bootstrap mode)
    - Subsequent super_admins: Only authenticated super_admin can create
    """

    permission_classes  = [IsSuperAdminOrFirstUser]
    throttle_classes    = [RegisterThrottle]
    serializer_class    = RegisterSuperAdminSerializer  # For drf-spectacular

    @extend_schema(
        request=RegisterSuperAdminSerializer,
        responses={
            201: OpenApiResponse(
                response=UserSerializer,
                description="Super admin account created successfully"
            ),
            400: OpenApiResponse(description="Validation error"),
        },
        summary="Register Super Admin",
        description="Create a new super admin account. First registration requires no auth (bootstrap mode).",
        tags=["Authentication"]
    )
    def post(self, request, *args, **kwargs):
        """
        Create a new super admin user.
        """
        language = getattr(request, 'language', 'en')

        # Validate input
        serializer = RegisterSuperAdminSerializer(data=request.data)

        if not serializer.is_valid():
            return StandardResponse.validation_error(
                errors=serializer.errors,
                message=t("auth.validation_failed", language)
            )

        user = serializer.save()

        return StandardResponse.created(
            data=UserSerializer(user).data,
            message=t("auth.super_admin_created", language)
        )


class LoginView(APIView):
    """
    User login endpoint.

    Accepts username/email and password.
    Returns JWT access and refresh tokens on successful authentication.
    """
    authentication_classes = []  # skip auth check — stale cookies must not block login

    permission_classes = [AllowAny]
    throttle_classes   = [LoginThrottle]
    serializer_class   = LoginSerializer  # For drf-spectacular

    @extend_schema(
        request=LoginSerializer,
        responses={
            200: OpenApiResponse(
                description="Login successful - JWT tokens set as HTTP-only cookies and user info returned"
            ),
            400: OpenApiResponse(description="Invalid credentials or validation error"),
        },
        summary="User Login (Cookie-based)",
        description="Authenticate user with username/email and password. Sets JWT tokens as HTTP-only cookies for enhanced security.",
        tags=["Authentication"]
    )
    def post(self, request, *args, **kwargs):
        """
        Authenticate user and set JWT tokens as HTTP-only cookies.
        """
        language = getattr(request, 'language', 'en')

        # Validate input
        serializer = LoginSerializer(data=request.data)

        if not serializer.is_valid():
            username_or_email = request.data.get('username', '') or request.data.get('email', '')
            # Increment failed login counter if we can identify the user
            if username_or_email:
                _increment_failed_login(username_or_email)
            AuditLog.log(
                user=None,
                action=AuditLog.Action.FAILED_LOGIN,
                changes={'username': username_or_email, 'reason': 'Invalid credentials'},
                request=request
            )
            return StandardResponse.validation_error(
                errors=serializer.errors,
                message=t("auth.invalid_credentials", language)
            )

        # Get authenticated user
        user = serializer.validated_data['user']

        # Check if account is locked
        if _is_account_locked(user):
            return StandardResponse.error(
                t('auth.account_locked', language, minutes=_lock_remaining_minutes(user)),
                status_code=status.HTTP_403_FORBIDDEN,
            )

        # Clear failed login counter on success
        _clear_failed_login(user)

        # Log successful login with IP address and location metadata
        AuditLog.log(
            user=user,
            action=AuditLog.Action.LOGIN,
            request=request
        )

        # If admin has 2FA enabled → return partial token, block full JWT
        if _is_admin_user(user):
            try:
                two_factor = AdminTwoFactor.objects.get(user=user, is_enabled=True)
                if two_factor.is_enabled:
                    return StandardResponse.success(
                        data={
                            'two_factor_required': True,
                            'partial_token': _issue_partial_token(user),
                        },
                        message=t('auth.two_factor_required', language),
                    )
            except AdminTwoFactor.DoesNotExist:
                pass

        # If user must change password → return partial token, block full JWT
        if getattr(getattr(user, 'profile', None), 'must_change_password', False):
            return StandardResponse.success(
                data={
                    'must_change_password': True,
                    'partial_token': _issue_partial_token(user),
                },
                message=t('auth.must_change_password', language),
            )

        # Serialize user data
        user_serializer = UserSerializer(user)

        # Generate token pair once — reused for both cookie and response body
        from django.conf import settings as django_settings
        refresh = RefreshToken.for_user(user)

        # In production: browser uses HttpOnly cookie automatically — no token in body needed.
        # In development: include access token in body for Swagger/Postman testing.
        response_data = {'user': user_serializer.data}
        if django_settings.DEBUG:
            response_data['access'] = str(refresh.access_token)

        response = StandardResponse.success(
            data=response_data,
            message=t("auth.login_success", language)
        )

        # Set HttpOnly cookies (used by browser/Next.js automatically)
        response = set_jwt_cookies(response, refresh)

        return response


class LogoutView(APIView):
    """
    User logout endpoint (Cookie-based).

    Blacklists the refresh token from cookie and clears all JWT cookies.
    Requires authenticated user.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None,  # No request body needed
        responses={
            200: OpenApiResponse(description="Logout successful - cookies cleared and token blacklisted"),
            400: OpenApiResponse(description="Invalid or missing token"),
        },
        summary="User Logout (Cookie-based)",
        description="Logout user by blacklisting the refresh token from cookie and clearing all JWT cookies.",
        tags=["Authentication"]
    )
    def post(self, request, *args, **kwargs):
        """
        Blacklist refresh token from cookie and clear JWT cookies.
        """
        language = getattr(request, 'language', 'en')

        # Get refresh token from cookie
        refresh_token = get_refresh_token_from_cookie(request)

        if not refresh_token:
            return StandardResponse.error(
                message="Refresh token not found in cookies",
                status_code=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Blacklist the refresh token
            token = RefreshToken(refresh_token)
            token.blacklist()

            # Log successful logout
            AuditLog.log(
                user=request.user,
                action=AuditLog.Action.LOGOUT,
                request=request
            )

            # Create success response
            response = StandardResponse.success(
                data='',
                message=t("auth.logout_success", language)
            )

            # Clear JWT cookies
            response = clear_jwt_cookies(response)

            return response

        except TokenError:
            return StandardResponse.error(
                message=t("auth.token_invalid", language),
                status_code=status.HTTP_400_BAD_REQUEST
            )


class RefreshTokenView(APIView):
    """
    Token refresh endpoint (Cookie-based).

    Reads refresh token from cookie and issues new access + refresh tokens.
    Implements token rotation for enhanced security.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        request=None,  # No request body needed
        responses={
            200: OpenApiResponse(
                description="Token refresh successful - new tokens set as cookies"
            ),
            400: OpenApiResponse(description="Invalid or expired refresh token"),
        },
        summary="Refresh JWT Tokens (Cookie-based)",
        description="Generate new access and refresh tokens using the refresh token from cookie. Old refresh token is blacklisted.",
        tags=["Authentication"]
    )
    def post(self, request, *args, **kwargs):
        """
        Refresh JWT tokens using cookie-based refresh token.
        """
        language = getattr(request, 'language', 'en')

        # Get refresh token from cookie
        refresh_token = get_refresh_token_from_cookie(request)

        if not refresh_token:
            return StandardResponse.error(
                message="Refresh token not found in cookies",
                status_code=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Validate and rotate the refresh token
            old_token = RefreshToken(refresh_token)

            # Get user from token
            user_id = old_token.get('user_id')
            from django.contrib.auth import get_user_model
            User = get_user_model()
            user = User.objects.get(id=user_id)

            # Generate new token pair
            from rest_framework_simplejwt.tokens import RefreshToken as JWTRefreshToken
            new_refresh = JWTRefreshToken.for_user(user)

            # Create success response with new access token in body
            response = StandardResponse.success(
                data={'access': str(new_refresh.access_token)},
                message=t("auth.token_refreshed", language)
            )

            # Set new tokens as HttpOnly cookies
            response = set_jwt_cookies(response, new_refresh)

            return response

        except TokenError:
            return StandardResponse.error(
                message=t("auth.token_invalid", language),
                status_code=status.HTTP_400_BAD_REQUEST
            )
        except User.DoesNotExist:
            return StandardResponse.error(
                message="User not found",
                status_code=status.HTTP_404_NOT_FOUND
            )


class LoginHistoryView(APIView):
    """
    View login history (successful and failed login attempts).

    Permissions:
    - Super Admin: Can view all login history
    - Authenticated users: Can view their own login history
    """

    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination

    @extend_schema(
        responses={
            200: OpenApiResponse(
                response=LoginHistorySerializer(many=True),
                description="Login history retrieved successfully"
            ),
        },
        summary="Get Login History",
        description="View login history with IP address, user agent, and timestamps. Super admins can view all history, others see only their own.",
        tags=["Authentication"]
    )
    def get(self, request, *args, **kwargs):
        """
        Get login history (successful and failed attempts).
        """
        language = getattr(request, 'language', 'en')

        # Base queryset for login/logout/failed_login actions
        queryset = AuditLog.objects.filter(
            action__in=[
                AuditLog.Action.LOGIN,
                AuditLog.Action.LOGOUT,
                AuditLog.Action.FAILED_LOGIN
            ]
        ).select_related('user').order_by('-created_at')

        # Filter by user if not super admin
        if not request.user.groups.filter(name='super_admin').exists():
            queryset = queryset.filter(user=request.user)

        # Optional filters
        user_id    = request.query_params.get('user_id')
        action = request.query_params.get('action')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        if user_id:
            queryset = queryset.filter(user_id=user_id)
        if action:
            queryset = queryset.filter(action=action)
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)

        # Paginate
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)

        # Serialize
        serializer = LoginHistorySerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)


class MeView(APIView):
    """
    GET /api/auth/me/

    Returns the logged-in user's profile, role, permissions,
    and a translated role-filtered sidebar menu.

    Frontend calls this on every page load to build the sidebar
    and check what the user is allowed to do.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: OpenApiResponse(description="User profile + translated menu")},
        summary="Get current user profile + menu",
        description="Returns user info, role, permissions, and a translated sidebar menu filtered by the user's role.",
        tags=["Authentication"]
    )
    def get(self, request, *args, **kwargs):
        lang = getattr(request, 'language', 'en')
        user = request.user

        role        = _get_user_role(user)
        permissions = get_user_permissions(user)
        redirect    = _get_redirect(user, role)
        profile     = getattr(user, 'profile', None)

        data = {
            'user': {
                'id':                 user.id,
                'email':              user.email,
                'first_name':         user.first_name,
                'last_name':          user.last_name,
                'phone':              profile.phone if profile else '',
                'preferred_language': profile.preferred_language if profile else 'en',
                'role':               role,
                'permissions':        sorted(permissions) if '*' not in permissions else ['*'],
            },
            'menu':     None if redirect else _build_menu(user, lang),
            'redirect': redirect,
        }

        return StandardResponse.success(
            data=data,
            message=t('auth.profile_retrieved', lang)
        )


class ProfileUpdateView(APIView):
    """
    PATCH /api/auth/me/profile/

    Update the current user's phone number and/or preferred language.
    Any authenticated user can update their own profile.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=ProfileUpdateSerializer,
        responses={200: OpenApiResponse(description="Profile updated")},
        summary="Update user profile",
        description="Update first name, last name, phone, and/or preferred language for the current user. Send only the fields you want to change.",
        tags=["Authentication"]
    )
    def patch(self, request, *args, **kwargs):
        lang = getattr(request, 'language', 'en')
        serializer = ProfileUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user    = request.user
        profile, _ = UserProfile.objects.get_or_create(user=user)
        changes = {}

        # User model fields
        user_fields_changed = []
        if 'first_name' in data and data['first_name'] != user.first_name:
            changes['first_name'] = {'old': user.first_name, 'new': data['first_name']}
            user.first_name = data['first_name']
            user_fields_changed.append('first_name')

        if 'last_name' in data and data['last_name'] != user.last_name:
            changes['last_name'] = {'old': user.last_name, 'new': data['last_name']}
            user.last_name = data['last_name']
            user_fields_changed.append('last_name')

        if user_fields_changed:
            user.save(update_fields=user_fields_changed)

        # Profile model fields
        profile_fields_changed = []
        if 'phone' in data and data['phone'] != profile.phone:
            changes['phone'] = {'old': profile.phone, 'new': data['phone']}
            profile.phone = data['phone']
            profile_fields_changed.append('phone')

        if 'preferred_language' in data and data['preferred_language'] != profile.preferred_language:
            changes['preferred_language'] = {'old': profile.preferred_language, 'new': data['preferred_language']}
            profile.preferred_language = data['preferred_language']
            profile_fields_changed.append('preferred_language')

        if profile_fields_changed:
            profile.save(update_fields=profile_fields_changed)

        if changes:
            from apps.core.services.audit import AuditService
            AuditService.log_update(user=user, instance=profile, changes=changes, request=request)

        return StandardResponse.success(
            data={
                'first_name':         user.first_name,
                'last_name':          user.last_name,
                'phone':              profile.phone,
                'preferred_language': profile.preferred_language,
            },
            message=t('auth.profile_updated', lang)
        )


class ForgotPasswordView(APIView):
    """
    POST /api/auth/password/forgot/

    Admins (super_admin, sub_admin) → sends reset link to email (15 min expiry).
    FPO users (fpo_manager)        → sends 6-digit OTP to phone (10 min expiry).
    Always returns 200 — never reveals whether the email/phone exists.
    """

    permission_classes = [AllowAny]
    throttle_classes   = [ForgotPasswordThrottle]

    @extend_schema(
        request=ForgotPasswordSerializer,
        responses={200: OpenApiResponse(description="Reset link or OTP sent")},
        summary="Forgot Password",
        description=(
            "Pass `email` for admin accounts — receives a password reset link. "
            "Pass `phone` for FPO users — receives a 6-digit OTP via SMS."
        ),
        tags=["Authentication"]
    )
    def post(self, request, *args, **kwargs):
        lang       = getattr(request, 'language', 'en')
        serializer = ForgotPasswordSerializer(data=request.data)

        if not serializer.is_valid():
            return StandardResponse.validation_error(
                errors=serializer.errors,
                message=t('auth.validation_failed', lang)
            )

        email = serializer.validated_data.get('email', '').strip().lower()
        phone = serializer.validated_data.get('phone', '').strip()

        if email:
            self._handle_email_reset(email, lang)
        else:
            self._handle_sms_otp(phone, lang)

        # Always return the same message — never reveal if email/phone exists
        return StandardResponse.success(
            message=t('auth.password_reset_sent', lang)
        )

    def _handle_email_reset(self, email, lang):
        from apps.notifications.services import send_notification
        from django.conf import settings as django_settings

        user = User.objects.filter(email=email, is_active=True).first()
        if not user:
            return

        token      = secrets.token_urlsafe(32)
        reset_link = f"{django_settings.FRONTEND_URL}/reset-password?token={token}"
        set_cache(cache_key('pwd_reset_email', token), user.id, PASSWORD_RESET_EMAIL_TOKEN_TTL)

        try:
            send_notification(
                user=user,
                code='password_reset',
                channel='email',
                context={
                    'user_name':   user.first_name or user.username,
                    'reset_link':  reset_link,
                    'button_link': reset_link,
                    'button_text': 'Reset Password',
                },
                lang=lang,
            )
        except Exception:
            logger.exception(f"Failed to queue password reset email for user {user.id}")

    def _handle_sms_otp(self, phone, lang):
        from apps.notifications.services import send_notification

        user = User.objects.filter(profile__phone=phone, is_active=True).first()
        if not user:
            return

        otp = str(secrets.randbelow(900000) + 100000)  # 100000–999999
        set_cache(cache_key('pwd_reset_otp', phone), {'otp': otp, 'user_id': user.id}, PASSWORD_RESET_OTP_TTL)

        try:
            send_notification(
                user=user,
                code='mobile_verification',
                channel='sms',
                context={'otp': otp},
                lang=lang,
            )
        except Exception:
            logger.exception(f"Failed to queue OTP SMS for phone {phone}")


class VerifyOTPView(APIView):
    """
    POST /api/auth/password/verify-otp/

    SMS flow only. Validates the 6-digit OTP.
    On success returns a short-lived `reset_token` to pass to /reset/.
    OTP is consumed on use — cannot be reused.
    """

    permission_classes = [AllowAny]
    throttle_classes   = [OTPVerifyThrottle]

    @extend_schema(
        request=VerifyOTPSerializer,
        responses={200: OpenApiResponse(description="OTP verified — reset_token returned")},
        summary="Verify OTP (SMS Reset Flow)",
        description="Validate the 6-digit OTP received via SMS. Returns a reset_token to use at /api/auth/password/reset/.",
        tags=["Authentication"]
    )
    def post(self, request, *args, **kwargs):
        lang       = getattr(request, 'language', 'en')
        serializer = VerifyOTPSerializer(data=request.data)

        if not serializer.is_valid():
            return StandardResponse.validation_error(
                errors=serializer.errors,
                message=t('auth.validation_failed', lang)
            )

        phone  = serializer.validated_data['phone']
        otp    = serializer.validated_data['otp']
        cached = get_cache(cache_key('pwd_reset_otp', phone))

        if not cached or cached.get('otp') != otp:
            return StandardResponse.error(
                message=t('auth.otp_invalid_or_expired', lang),
                status_code=status.HTTP_400_BAD_REQUEST
            )

        delete_cache(cache_key('pwd_reset_otp', phone))

        reset_token = secrets.token_urlsafe(32)
        set_cache(cache_key('pwd_reset_token', reset_token), cached['user_id'], PASSWORD_RESET_TOKEN_TTL)

        return StandardResponse.success(
            data={'reset_token': reset_token},
            message=t('auth.otp_verified', lang)
        )


class ResetPasswordView(APIView):
    """
    POST /api/auth/password/reset/

    Final step — both flows (email link + SMS OTP) converge here.
    Token is deleted on use — strictly one-time.
    Sends a confirmation email after successful reset.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        request=ResetPasswordSerializer,
        responses={
            200: OpenApiResponse(description="Password reset successfully"),
            400: OpenApiResponse(description="Invalid/expired token or weak password"),
        },
        summary="Reset Password",
        description=(
            "Set a new password using the reset token. "
            "Token is from the email reset link or from verify-otp response. "
            "Token is one-time use — deleted immediately after successful reset."
        ),
        tags=["Authentication"]
    )
    def post(self, request, *args, **kwargs):
        lang       = getattr(request, 'language', 'en')
        serializer = ResetPasswordSerializer(data=request.data)

        if not serializer.is_valid():
            return StandardResponse.validation_error(
                errors=serializer.errors,
                message=t('auth.validation_failed', lang)
            )

        token        = serializer.validated_data['token']
        new_password = serializer.validated_data['new_password']

        # Check email-flow token first, then OTP-flow token
        user_id   = get_cache(cache_key('pwd_reset_email', token))
        token_key = cache_key('pwd_reset_email', token)

        if not user_id:
            user_id   = get_cache(cache_key('pwd_reset_token', token))
            token_key = cache_key('pwd_reset_token', token)

        if not user_id:
            return StandardResponse.error(
                message=t('auth.reset_token_invalid_or_expired', lang),
                status_code=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = User.objects.get(pk=user_id, is_active=True)
        except User.DoesNotExist:
            return StandardResponse.error(
                message=t('auth.user_not_found', lang),
                status_code=status.HTTP_404_NOT_FOUND
            )

        try:
            validate_password(new_password, user)
        except ValidationError as e:
            return StandardResponse.error(
                message=' '.join(e.messages),
                status_code=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(new_password)
        user.save(update_fields=['password'])
        delete_cache(token_key)

        AuditLog.log(user=user, action=AuditLog.Action.PASSWORD_CHANGE, request=request)

        from apps.notifications.services import send_notification
        try:
            send_notification(
                user=user,
                code='password_changed',
                channel='email',
                context={'user_name': user.first_name or user.username},
                lang=lang,
            )
        except Exception:
            logger.exception(f"Failed to queue password-changed email for user {user.id}")

        return StandardResponse.success(
            message=t('auth.password_reset_success', lang)
        )


class ChangePasswordView(APIView):
    """
    POST /api/auth/password/change/

    Forced password change for users who logged in with a temporary password.
    Requires the partial_token from the login response (must_change_password=True).
    Clears must_change_password flag and issues full JWT cookies on success.
    """

    permission_classes = [AllowAny]
    throttle_classes   = [OTPVerifyThrottle]

    @extend_schema(
        request=ChangePasswordSerializer,
        responses={
            200: OpenApiResponse(description="Password changed — full JWT issued"),
            400: OpenApiResponse(description="Invalid token or weak password"),
        },
        summary="Change temporary password",
        description="Used when must_change_password=True after login. Validates partial_token, sets new password, issues full JWT.",
        tags=["Authentication"]
    )
    def post(self, request, *args, **kwargs):
        from apps.accounts.api.two_factor import _verify_partial_token
        from apps.notifications.services import send_notification

        lang       = getattr(request, 'language', 'en')
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = _verify_partial_token(data['partial_token'])
        if not user:
            return StandardResponse.error(
                message=t('auth.invalid_or_expired_token', lang),
                status_code=status.HTTP_400_BAD_REQUEST
            )

        try:
            validate_password(data['new_password'], user)
        except ValidationError as e:
            return StandardResponse.error(
                message=' '.join(e.messages),
                status_code=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(data['new_password'])
        user.save(update_fields=['password'])

        profile = user.profile
        profile.must_change_password = False
        profile.save(update_fields=['must_change_password'])

        AuditLog.log(user=user, action=AuditLog.Action.PASSWORD_CHANGE, request=request)

        try:
            send_notification(
                user=user,
                code='password_changed',
                channel='email',
                context={'user_name': user.first_name or user.username},
                lang=lang,
            )
        except Exception:
            logger.exception(f"Failed to queue password-changed email for user {user.id}")

        refresh  = RefreshToken.for_user(user)
        response = StandardResponse.success(
            data={'user': UserSerializer(user).data},
            message=t('auth.password_changed_login', lang)
        )
        response = set_jwt_cookies(response, refresh)
        return response


class ChangeCurrentPasswordView(APIView):
    """
    POST /api/auth/password/change-current/

    Voluntary password change for any logged-in user.
    Verifies current password first, then sets the new one.
    Does NOT require a partial_token — the user must already be fully authenticated.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=ChangeCurrentPasswordSerializer,
        responses={
            200: OpenApiResponse(description="Password changed successfully"),
            400: OpenApiResponse(description="Wrong current password or weak new password"),
        },
        summary="Change current password",
        description=(
            "Allows a logged-in user to voluntarily change their own password. "
            "Requires the current password for verification. "
            "On success, existing JWT cookies remain valid — no re-login required."
        ),
        tags=["Authentication"]
    )
    def post(self, request, *args, **kwargs):
        from apps.notifications.services import send_notification

        lang       = getattr(request, 'language', 'en')
        serializer = ChangeCurrentPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = request.user

        if not user.check_password(data['current_password']):
            return StandardResponse.error(
                message=t('auth.invalid_credentials', lang),
                status_code=status.HTTP_400_BAD_REQUEST
            )

        if data['current_password'] == data['new_password']:
            return StandardResponse.error(
                message='New password must be different from the current password.',
                status_code=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(data['new_password'])
        user.save(update_fields=['password'])

        AuditLog.log(user=user, action=AuditLog.Action.PASSWORD_CHANGE, request=request)

        try:
            send_notification(
                user=user,
                code='password_changed',
                channel='email',
                context={'user_name': user.first_name or user.username},
                lang=lang,
            )
        except Exception:
            logger.exception(f"Failed to queue password-changed email for user {user.id}")

        return StandardResponse.success(
            message=t('auth.password_changed', lang)
        )
