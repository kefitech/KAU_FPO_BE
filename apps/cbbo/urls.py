"""
apps/cbbo/urls.py
"""
from django.urls import path


app_name = 'cbbo'  

from apps.cbbo.api.assignments import AssignedFPOListView, AssignedFPODetailView
from apps.cbbo.api.reports import ReportListCreateView, ReportDetailView, ReportSubmitView
from apps.cbbo.api.training import (
    TrainingSessionListCreateView, TrainingSessionDetailView, TrainingAttendanceSetView,
)

urlpatterns = [
    # assignments.py
    path('fpos/', AssignedFPOListView.as_view(), name='cbbo-fpo-list'),
    path('fpos/<int:fpo_id>/', AssignedFPODetailView.as_view(), name='cbbo-fpo-detail'),

    # reports.py
    path('reports/', ReportListCreateView.as_view(), name='cbbo-report-list-create'),
    path('reports/<int:report_id>/', ReportDetailView.as_view(), name='cbbo-report-detail'),
    path('reports/<int:report_id>/submit/', ReportSubmitView.as_view(), name='cbbo-report-submit'),

    # training.py
    path('training/', TrainingSessionListCreateView.as_view(), name='cbbo-training-list-create'),
    path('training/<int:session_id>/', TrainingSessionDetailView.as_view(), name='cbbo-training-detail'),
    path('training/<int:session_id>/attendance/', TrainingAttendanceSetView.as_view(), name='cbbo-training-attendance-set'),
]