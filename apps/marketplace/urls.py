"""
Top-level marketplace URLs.

config/urls.py mounts this app as:
    path('api/marketplace/', include('apps.marketplace.urls', namespace='marketplace')),

This just delegates to api/urls.py, which is where the actual ViewSets
are registered. Kept as a separate file (rather than pointing urls.py
directly to api/urls.py from config/urls.py) so the app has the standard
Django app_name/urls.py entrypoint other apps in this project use.
"""

from django.urls import include, path

app_name = 'marketplace'

urlpatterns = [
    path('', include('apps.marketplace.api.urls')),
]