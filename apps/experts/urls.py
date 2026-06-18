"""
Expert Directory URL Configuration
=====================================
Base: /api/experts/
"""

from django.urls import path

from .api.views import ExpertListView, ExpertDetailView, ExpertEnquiryView

app_name = 'experts'

urlpatterns = [
    path('',                  ExpertListView.as_view(),    name='expert-list'),
    path('<int:pk>/',         ExpertDetailView.as_view(),  name='expert-detail'),
    path('<int:pk>/enquiry/', ExpertEnquiryView.as_view(), name='expert-enquiry'),
]
