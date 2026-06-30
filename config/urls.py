"""
██╗  ██╗███████╗███████╗██╗    ████████╗███████╗ ██████╗██╗  ██╗
██║ ██╔╝██╔════╝██╔════╝██║    ╚══██╔══╝██╔════╝██╔════╝██║  ██║
█████╔╝ █████╗  █████╗  ██║       ██║   █████╗  ██║     ███████║
██╔═██╗ ██╔══╝  ██╔══╝  ██║       ██║   ██╔══╝  ██║     ██╔══██║
██║  ██╗███████╗██║     ██║       ██║   ███████╗╚██████╗██║  ██║
╚═╝  ╚═╝╚══════╝╚═╝     ╚═╝       ╚═╝   ╚══════╝ ╚═════╝╚═╝  ╚═╝

                KEFI TECH

 █████╗ ████████╗██╗  ██╗██╗   ██╗██╗
██╔══██╗╚══██╔══╝██║  ██║██║   ██║██║
███████║   ██║   ███████║██║   ██║██║
██╔══██║   ██║   ██╔══██║██║   ██║██║
██║  ██║   ██║   ██║  ██║╚██████╔╝███████╗
╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝ ╚═════╝ ╚══════╝

        ATHUL GOPAN

-----------------------------------------------------
KAU-FPO Backend - Root URL Configuration
========================================

API URL Structure:
    /api/v1/auth/       - Authentication (login, register, password reset)
    /api/v1/fpo/        - FPO management
    /api/v1/experts/    - Expert directory
    /api/v1/marketplace/- Marketplace APIs
    /api/v1/recommendations/ - AI recommendations
    /api/v1/analytics/  - Analytics & reports
    /api/v1/gis/        - GIS/mapping
    /api/v1/government/ - Government portal
    /api/v1/cbbo/       - CBBO portal
    /api/v1/notifications/ - Notifications

    /admin/             - Django admin
    /api/schema/        - OpenAPI schema
    /api/docs/          - Swagger UI

Author:
    Athul Gopan
Created On:
    21-04-2026
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from django.shortcuts import redirect

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)


# =============================================================================
# HEALTH CHECK VIEW
# =============================================================================

def health_check(request):
    """Simple health check endpoint."""
    return JsonResponse({
        'status': 'healthy',
        'message': 'KAU-FPO API is running'
    })


def api_root(request):
    """API root with version info."""
    return JsonResponse({
        'name': 'KAU-FPO Platform API',
        'version': '1.0.0',
        'description': 'AI-Based Digital Platform for KAU-FPO Linkage Programme',
        'documentation': '/api/docs/',
        'health': '/api/health/',
    })


# =============================================================================
# URL PATTERNS
# =============================================================================

urlpatterns = [
    # Root — Swagger in dev, API info in production
    path('', lambda request: redirect('/api/docs/') if settings.DEBUG else JsonResponse({
        'name': 'KAU-FPO Platform API',
        'version': '1.1.1',
        'status': 'running',
    })),

    # Admin
    path('admin/', admin.site.urls),

    # API Root & Health
    path('api/', api_root, name='api-root'),
    path('api/health/', health_check, name='health-check'),

    # API Documentation (drf-spectacular)
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # Public endpoints (no auth required)
    path('api/translations/', include('apps.core.urls', namespace='core')),
    path('api/public/',       include('apps.core.public_urls')),

    # API v1 endpoints
    path('api/auth/', include('apps.accounts.urls', namespace='accounts')),
    path('api/admin/', include('apps.accounts.api.admin.urls')),  # Admin management APIs
    path('api/fpo/', include('apps.fpo.urls', namespace='fpo')),
    path('api/experts/', include('apps.experts.urls', namespace='experts')),
    path('api/marketplace/', include('apps.marketplace.urls', namespace='marketplace')),
    path('api/recommendations/', include('apps.recommendations.urls', namespace='recommendations')),
    path('api/analytics/', include('apps.analytics.urls', namespace='analytics')),
    path('api/gis/', include('apps.gis_module.urls', namespace='gis')),
    path('api/government/', include('apps.government.urls', namespace='government')),
    path('api/cbbo/', include('apps.cbbo.urls', namespace='cbbo')),
    path('api/notifications/', include('apps.notifications.urls', namespace='notifications')),
]

# =============================================================================
# STATIC & MEDIA FILES (Development only)
# =============================================================================

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

    # Debug toolbar (if installed)
    try:
        import debug_toolbar
        urlpatterns += [
            path('__debug__/', include(debug_toolbar.urls)),
        ]
    except ImportError:
        pass

# =============================================================================
# CUSTOM ADMIN SITE CONFIGURATION
# =============================================================================

admin.site.site_header = 'KAU-FPO Administration'
admin.site.site_title = 'KAU-FPO Admin'
admin.site.index_title = 'Welcome to KAU-FPO Admin Portal'
