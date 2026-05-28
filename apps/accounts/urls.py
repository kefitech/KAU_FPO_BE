"""
URL configuration for accounts app.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .api.roles import RoleViewSet
from .api.auth import (
    RegisterSuperAdminView, LoginView, LogoutView, RefreshTokenView,
    LoginHistoryView, MeView, ProfileUpdateView, ForgotPasswordView,
    VerifyOTPView, ResetPasswordView, ChangePasswordView, ChangeCurrentPasswordView,
)
from .api.two_factor import (
    TwoFactorSetupView, TwoFactorVerifySetupView,
    TwoFactorLoginVerifyView, TwoFactorLoginBackupView,
    TwoFactorStatusView, TwoFactorRegenerateBackupCodesView,
    TwoFactorDisableView, TwoFactorSelfDisableView, TwoFactorDisableRequestOTPView,
)
from apps.fpo.api.urls import fpo_auth_urls

app_name = 'accounts'

# DRF Router for ViewSets
router = DefaultRouter()
router.register(r'roles', RoleViewSet, basename='role')

urlpatterns = [
    # Authentication API
    path('register/super-admin/', RegisterSuperAdminView.as_view(), name='register-super-admin'),
    *fpo_auth_urls,  # FPO user registration — POST /api/auth/register/
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('token/refresh/', RefreshTokenView.as_view(), name='token-refresh'),
    path('login-history/', LoginHistoryView.as_view(), name='login-history'),
    path('me/', MeView.as_view(), name='me'),
    path('me/profile/', ProfileUpdateView.as_view(), name='me-profile'),

    # Role Management API
    path('', include(router.urls)),

    # Two-Factor Authentication
    path('2fa/status/',                    TwoFactorStatusView.as_view(),                name='2fa-status'),
    path('2fa/setup/',                     TwoFactorSetupView.as_view(),                 name='2fa-setup'),
    path('2fa/verify-setup/',              TwoFactorVerifySetupView.as_view(),           name='2fa-verify-setup'),
    path('2fa/login/verify/',              TwoFactorLoginVerifyView.as_view(),           name='2fa-login-verify'),
    path('2fa/login/backup/',              TwoFactorLoginBackupView.as_view(),           name='2fa-login-backup'),
    path('2fa/regenerate-backup-codes/',   TwoFactorRegenerateBackupCodesView.as_view(), name='2fa-regenerate-backup'),
    path('2fa/disable/request-otp/',       TwoFactorDisableRequestOTPView.as_view(),     name='2fa-disable-request-otp'),
    path('2fa/disable/',                   TwoFactorSelfDisableView.as_view(),           name='2fa-self-disable'),
    path('2fa/disable/<int:user_id>/',     TwoFactorDisableView.as_view(),               name='2fa-disable'),

    # Password Reset
    path('password/forgot/',          ForgotPasswordView.as_view(),         name='password-forgot'),
    path('password/verify-otp/',      VerifyOTPView.as_view(),              name='password-verify-otp'),
    path('password/reset/',           ResetPasswordView.as_view(),          name='password-reset'),
    path('password/change/',          ChangePasswordView.as_view(),         name='password-change'),
    path('password/change-current/',  ChangeCurrentPasswordView.as_view(),  name='password-change-current'),
]
