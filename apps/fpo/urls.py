"""
URL configuration for FPO app.
Base: /api/fpo/
"""

from django.urls import include, path

from apps.fpo.api.urls import urlpatterns as api_urls

app_name = 'fpo'

urlpatterns = [
    path('', include(api_urls)),
]
