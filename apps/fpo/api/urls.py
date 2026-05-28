"""
FPO API URL Configuration
==========================
All FPO-facing API endpoints.
Base: /api/fpo/
"""

from django.urls import path

# Auth (registration) — included in /api/auth/ via accounts/urls.py
from .auth import RegisterFPOUserView
from .registration import (
    EligibilityCheckView,
    PreRegisterSendOTPView,
    PreRegisterVerifyOTPView,
    FPORegisterView,
    FPOMeView,
    FPOStatusView,
    FieldValidateView,
)
from .email_verify import EmailOTPSendView, EmailOTPConfirmView
from .phone_verify import PhoneOTPSendView, PhoneOTPConfirmView
from .documents import DocumentUploadView, DocumentDeleteView
from .submit import FPOSubmitView

# FPO-facing auth urls exposed to accounts/urls.py
fpo_auth_urls = [
    path('register/', RegisterFPOUserView.as_view(), name='fpo-register'),
]

# FPO module urls (included at /api/fpo/)
urlpatterns = [
    path('eligibility-check/',            EligibilityCheckView.as_view(),      name='fpo-eligibility-check'),
    path('pre-register/send-otp/',        PreRegisterSendOTPView.as_view(),     name='fpo-prereg-send-otp'),
    path('pre-register/verify-otp/',      PreRegisterVerifyOTPView.as_view(),   name='fpo-prereg-verify-otp'),
    path('register/',                FPORegisterView.as_view(),        name='fpo-register-step1'),
    path('me/',                      FPOMeView.as_view(),              name='fpo-me'),
    path('me/status/',               FPOStatusView.as_view(),          name='fpo-me-status'),
    path('validate-field/',          FieldValidateView.as_view(),      name='fpo-validate-field'),
    # Email OTP verification
    path('email-verify/send/',       EmailOTPSendView.as_view(),       name='fpo-email-otp-send'),
    path('email-verify/confirm/',    EmailOTPConfirmView.as_view(),    name='fpo-email-otp-confirm'),
    # Phone OTP verification
    path('phone-verify/send/',       PhoneOTPSendView.as_view(),       name='fpo-phone-otp-send'),
    path('phone-verify/confirm/',    PhoneOTPConfirmView.as_view(),    name='fpo-phone-otp-confirm'),
    # Documents
    path('me/documents/',               DocumentUploadView.as_view(),     name='fpo-documents'),
    path('me/documents/<uuid:doc_id>/', DocumentDeleteView.as_view(),     name='fpo-document-delete'),
    # Submit
    path('me/submit/',                  FPOSubmitView.as_view(),           name='fpo-submit'),
]
