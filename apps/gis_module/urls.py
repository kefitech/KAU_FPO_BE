"""
URL configuration for GIS module app.
Actual route definitions live in apps/gis_module/api/urls.py, per the
module's file layout (API logic in api/, models in apps/database/models/).
"""
from django.urls import path, include

app_name = 'gis'

urlpatterns = [
    path('', include('apps.gis_module.api.urls')),
]
