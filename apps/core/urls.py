"""
Core App URLs
=============
Public endpoints that require no authentication.
"""

from django.urls import path
from .api.translations import PublicTranslationsView

app_name = 'core'

urlpatterns = [
    path('public/', PublicTranslationsView.as_view(), name='public-translations'),
]
