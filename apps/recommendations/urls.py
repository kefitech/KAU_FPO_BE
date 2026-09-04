"""
URL configuration for recommendations app.
Actual route definitions live in apps/recommendations/api/urls.py.
"""
from django.urls import path, include

app_name = 'recommendations'

urlpatterns = [
    path('', include('apps.recommendations.api.urls')),
]
