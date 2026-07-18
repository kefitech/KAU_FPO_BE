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
from .info_response import FPOInfoResponseView
from .dashboard import FPODashboardView
from .profile import FPOProfileView
from .claim import FPOClaimView, FPOClaimRespondView, FPOClaimDocumentUploadView, FPOClaimDocumentDeleteView
from .schemes import SchemeListPublicView, SchemeDetailPublicView
from .team import (
    TeamListView, TeamInviteView, TeamDeactivateView,
    TeamBulkInviteView, TeamBulkInviteFileView,
    TeamBulkActivateView, TeamBulkDeactivateView,
    TeamResetPasswordView,
)
from .tier_assessment import (
    TierAssessmentView,
    TierAssessmentDetailView,
    TierAssessmentSubmitView,
    TierAssessmentHistoryView,
    TierAssessmentReopenView,
    TierAssessmentUploadView,
    TierAssessmentUploadDeleteView,
)

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
    path('me/info-response/',           FPOInfoResponseView.as_view(),     name='fpo-info-response'),
    # Dashboard
    path('dashboard/',                  FPODashboardView.as_view(),        name='fpo-dashboard'),
    # Personal profile
    path('me/profile/',                 FPOProfileView.as_view(),          name='fpo-profile'),
    # Ownership claim
    path('claim/',                      FPOClaimView.as_view(),            name='fpo-claim'),
    path('claim/<int:claim_id>/respond/',   FPOClaimRespondView.as_view(),        name='fpo-claim-respond'),
    path('claim/<int:claim_id>/documents/',            FPOClaimDocumentUploadView.as_view(),  name='fpo-claim-documents'),
    path('claim/<int:claim_id>/documents/<int:doc_id>/', FPOClaimDocumentDeleteView.as_view(), name='fpo-claim-document-delete'),
    # Schemes & Subsidies (public browse)
    path('schemes/',                    SchemeListPublicView.as_view(),    name='fpo-schemes-list'),
    path('schemes/<int:pk>/',           SchemeDetailPublicView.as_view(),  name='fpo-schemes-detail'),
    # Team management
    path('me/team/',                            TeamListView.as_view(),           name='fpo-team-list'),
    path('me/team/invite/',                     TeamInviteView.as_view(),         name='fpo-team-invite'),
    path('me/team/bulk-invite/',                TeamBulkInviteView.as_view(),     name='fpo-team-bulk-invite'),
    path('me/team/bulk-invite-file/',           TeamBulkInviteFileView.as_view(), name='fpo-team-bulk-invite-file'),
    path('me/team/bulk-activate/',              TeamBulkActivateView.as_view(),   name='fpo-team-bulk-activate'),
    path('me/team/bulk-deactivate/',            TeamBulkDeactivateView.as_view(), name='fpo-team-bulk-deactivate'),
    path('me/team/<int:user_id>/deactivate/',     TeamDeactivateView.as_view(),     name='fpo-team-deactivate'),
    path('me/team/<int:user_id>/reset-password/', TeamResetPasswordView.as_view(),  name='fpo-team-reset-password'),
    # Tier Assessment
    path('me/tier-assessment/',                         TierAssessmentView.as_view(),        name='fpo-tier-assessment'),
    path('me/tier-assessment/history/',                 TierAssessmentHistoryView.as_view(), name='fpo-tier-assessment-history'),
    path('me/tier-assessment/<int:assessment_id>/',     TierAssessmentDetailView.as_view(),  name='fpo-tier-assessment-detail'),
    path('me/tier-assessment/<int:assessment_id>/submit/', TierAssessmentSubmitView.as_view(), name='fpo-tier-assessment-submit'),
    path('me/tier-assessment/<int:assessment_id>/reopen/', TierAssessmentReopenView.as_view(), name='fpo-tier-assessment-reopen'),
    path('me/tier-assessment/<int:assessment_id>/upload/', TierAssessmentUploadView.as_view(), name='fpo-tier-assessment-upload'),
    path('me/tier-assessment/<int:assessment_id>/upload/<int:upload_id>/', TierAssessmentUploadDeleteView.as_view(), name='fpo-tier-assessment-upload-delete'),
]
