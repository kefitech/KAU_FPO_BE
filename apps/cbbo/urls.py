"""
apps/cbbo/urls.py
"""
from django.urls import path
app_name = 'cbbo'

from apps.cbbo.api.assignments import AssignedFPOListView, AssignedFPODetailView, AssignedFPOVerifyDocumentView
from apps.cbbo.api.dashboard import CBBODashboardStatsView
from apps.cbbo.api.reports import ReportListCreateView, ReportDetailView, ReportSubmitView
from apps.cbbo.api.training import (
    TrainingSessionListCreateView, TrainingSessionDetailView, TrainingAttendanceSetView,
    TrainingCommentsReadView,
)
from apps.cbbo.api.market_linkage import CBBOMarketLinkageFPOListView, CBBOMarketLinkageFPOProductsView
from apps.cbbo.api.registration import CBBORegistrationView, PublicOrganisationListView, CBBORegistrationOTPSendView, CBBORegistrationOTPConfirmView, CBBORegistrationEmailOTPSendView, CBBORegistrationEmailOTPConfirmView

urlpatterns = [
    # assignments.py
    path('fpos/', AssignedFPOListView.as_view(), name='cbbo-fpo-list'),
    path('fpos/<int:fpo_id>/', AssignedFPODetailView.as_view(), name='cbbo-fpo-detail'),
    path('fpos/<int:fpo_id>/verify-document/<int:doc_id>/', AssignedFPOVerifyDocumentView.as_view(), name='cbbo-fpo-verify-document'),
    # dashboard.py
    path('dashboard/stats/', CBBODashboardStatsView.as_view(), name='cbbo-dashboard-stats'),
    # reports.py
    path('reports/', ReportListCreateView.as_view(), name='cbbo-report-list-create'),
    path('reports/<int:report_id>/', ReportDetailView.as_view(), name='cbbo-report-detail'),
    path('reports/<int:report_id>/submit/', ReportSubmitView.as_view(), name='cbbo-report-submit'),
    # training.py
    path('training/', TrainingSessionListCreateView.as_view(), name='cbbo-training-list-create'),
    path('training/<int:session_id>/', TrainingSessionDetailView.as_view(), name='cbbo-training-detail'),
    path('training/<int:session_id>/attendance/', TrainingAttendanceSetView.as_view(), name='cbbo-training-attendance-set'),
    path('training/<int:session_id>/comments/read/', TrainingCommentsReadView.as_view(), name='cbbo-training-comments-read'),
    # market_linkage.py
    path('market-linkage/fpos/', CBBOMarketLinkageFPOListView.as_view(), name='cbbo-market-linkage-fpos'),
    path('market-linkage/fpos/<int:fpo_id>/products/', CBBOMarketLinkageFPOProductsView.as_view(), name='cbbo-market-linkage-fpo-products'),
    # registration.py
    path('register/', CBBORegistrationView.as_view(), name='cbbo-register'),
    path('register/otp/send/', CBBORegistrationOTPSendView.as_view(), name='cbbo-register-otp-send'),
     path('register/otp/confirm/', CBBORegistrationOTPConfirmView.as_view(), name='cbbo-register-otp-confirm'),
    path('register/otp/email/send/', CBBORegistrationEmailOTPSendView.as_view(), name='cbbo-register-otp-email-send'),
    path('register/otp/email/confirm/', CBBORegistrationEmailOTPConfirmView.as_view(), name='cbbo-register-otp-email-confirm'),
    path('organisations/', PublicOrganisationListView.as_view(), name='cbbo-organisations-public'),
]
