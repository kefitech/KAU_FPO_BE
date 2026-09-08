"""
URL configuration for government portal app.
"""
from django.urls import path

from apps.government.api.fpos import GovernmentFPOListView, GovernmentFPODetailView
from apps.government.api.dashboard import GovernmentDashboardStatsView
from apps.government.api.schemes import GovernmentSchemeListView, GovernmentSchemeDetailView
from apps.government.api.training import (
    GovernmentTrainingSessionListView,
    GovernmentTrainingSessionDetailView,
    GovernmentTrainingAttendanceSetView,
)
from apps.government.api.registration import GovernmentRegistrationView
from apps.government.api.reports import GovernmentFPOReportView

app_name = 'government'

urlpatterns = [
    path('fpos/', GovernmentFPOListView.as_view(), name='fpo-list'),
    path('fpos/<int:fpo_id>/', GovernmentFPODetailView.as_view(), name='fpo-detail'),
    path('dashboard/stats/', GovernmentDashboardStatsView.as_view(), name='dashboard-stats'),
    path('schemes/', GovernmentSchemeListView.as_view(), name='scheme-list'),
    path('schemes/<int:pk>/', GovernmentSchemeDetailView.as_view(), name='scheme-detail'),
    path('training-sessions/', GovernmentTrainingSessionListView.as_view(), name='training-list'),
    path('training-sessions/<int:session_id>/', GovernmentTrainingSessionDetailView.as_view(), name='training-detail'),
    path('training-sessions/<int:session_id>/attendance/', GovernmentTrainingAttendanceSetView.as_view(), name='training-attendance'),
    path('register/', GovernmentRegistrationView.as_view(), name='register'),
    path('reports/fpo-summary/', GovernmentFPOReportView.as_view(), name='fpo-report'),
]
