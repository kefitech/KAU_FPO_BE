"""
Admin API URLs for Multilingual System
======================================

RESTful endpoints for managing languages, translation categories, and translations.

Only accessible to super_admin and admin roles.

Base Path: /api/admin/

Endpoints:
- /api/admin/languages/
- /api/admin/translation-categories/
- /api/admin/translations/

Author: Athul Gopan (Kefi Tech Solutions)
Created: 28-04-2026
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .languages import LanguageViewSet
from .categories import TranslationCategoryViewSet
from .translations import TranslationViewSet
from .fpo_roles import FPOMemberRoleViewSet
from .fpo_actions import FPOActionViewSet
from .fpo_permissions import FPOPermissionMatrixView, FPORolePermissionsView
from .applications import (
    ApplicationListView,
    ApplicationDetailView,
    ApplicationMarkUnderReviewView,
    ApplicationApproveView,
    ApplicationRejectView,
    ApplicationRequestInfoView,
    ApplicationVerifyDocumentView,
    ApplicationSetUserLimitView,
)
from apps.accounts.api.menu import MenuItemViewSet
from apps.accounts.api.sub_admins import SubAdminViewSet

# Create DRF router
router = DefaultRouter()

# Register ViewSets
router.register(r'languages', LanguageViewSet, basename='language')
router.register(r'translation-categories', TranslationCategoryViewSet, basename='translation-category')
router.register(r'translations', TranslationViewSet, basename='translation')
router.register(r'menu', MenuItemViewSet, basename='menu')
router.register(r'sub-admins', SubAdminViewSet, basename='sub-admin')
router.register(r'fpo-member-roles', FPOMemberRoleViewSet, basename='fpo-member-role')
router.register(r'fpo-actions', FPOActionViewSet, basename='fpo-action')

# URL patterns
urlpatterns = [
    path('', include(router.urls)),
    path('fpo-permissions/',          FPOPermissionMatrixView.as_view(),      name='fpo-permission-matrix'),
    path('fpo-permissions/<int:role_id>/', FPORolePermissionsView.as_view(), name='fpo-role-permissions'),
    # FPO Applications workflow
    path('applications/',                                                    ApplicationListView.as_view(),             name='admin-applications-list'),
    path('applications/<int:fpo_id>/',                                       ApplicationDetailView.as_view(),           name='admin-applications-detail'),
    path('applications/<int:fpo_id>/mark-under-review/',                     ApplicationMarkUnderReviewView.as_view(),  name='admin-applications-under-review'),
    path('applications/<int:fpo_id>/approve/',                               ApplicationApproveView.as_view(),          name='admin-applications-approve'),
    path('applications/<int:fpo_id>/reject/',                                ApplicationRejectView.as_view(),           name='admin-applications-reject'),
    path('applications/<int:fpo_id>/request-info/',                          ApplicationRequestInfoView.as_view(),      name='admin-applications-request-info'),
    path('applications/<int:fpo_id>/verify-document/<int:doc_id>/',          ApplicationVerifyDocumentView.as_view(),   name='admin-applications-verify-doc'),
    path('applications/<int:fpo_id>/set-user-limit/',                        ApplicationSetUserLimitView.as_view(),     name='admin-applications-set-limit'),
]
