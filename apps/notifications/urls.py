"""
URL configuration for notifications app.

Endpoints:
    /api/notifications/template-codes/      — manage template definitions (dropdown source)
    /api/notifications/templates/           — manage language-specific template content
    /api/notifications/channel-settings/    — manage channel credentials (super_admin only)
    /api/notifications/inbox/               — user in-app notification inbox
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .api.templates import NotificationTemplateCodeViewSet, NotificationTemplateViewSet
from .api.settings import NotificationChannelSettingsViewSet
from .api.inbox import InboxViewSet

app_name = 'notifications'

router = DefaultRouter()
router.register(r'template-codes',    NotificationTemplateCodeViewSet,    basename='template-code')
router.register(r'templates',         NotificationTemplateViewSet,         basename='template')
router.register(r'channel-settings',  NotificationChannelSettingsViewSet,  basename='channel-settings')
router.register(r'inbox',             InboxViewSet,                        basename='inbox')

urlpatterns = [
    path('', include(router.urls)),
]
