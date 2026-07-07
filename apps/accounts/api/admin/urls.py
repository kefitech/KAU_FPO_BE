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
    ApplicationRejectView,
    ApplicationRequestInfoView,
    ApplicationVerifyDocumentView,
    ApplicationSetUserLimitView,
    ApplicationAssignTierView,
    ApplicationTierHistoryView,
    ApplicationActivateView,
    ApplicationDeactivateView,
)
from .external_apis import (
    ExternalAPISettingsListView,
    ExternalAPISettingsDetailView,
    ExternalAPISettingsActivateView,
    ExternalAPISettingsDeactivateView,
)
from .page_access import RolePageAccessListView, RolePageAccessDetailView
from .audit_logs import AuditLogListView
from .dashboard import AdminDashboardStatsView
from .ownership_claims import (
    OwnershipClaimListView,
    OwnershipClaimDetailView,
    OwnershipClaimApproveView,
    OwnershipClaimRejectView,
    OwnershipClaimRequestDocsView,
)
from .cms import (
    SiteBlockListView,
    SiteBlockDetailView,
    AnnouncementListView,
    AnnouncementDetailView,
    FAQListView,
    FAQDetailView,
    QuickLinkListView,
    QuickLinkDetailView,
    QuickLinkLogoDeleteView,
    QuickLinkActivateView,
    QuickLinkDeactivateView,
    NewsSourceListView,
    NewsSourceDetailView,
    NewsSourceLogoDeleteView,
    NewsSourceActivateView,
    NewsSourceDeactivateView,
    TeamMemberListView,
    TeamMemberDetailView,
    TeamMemberPhotoDeleteView,
    TeamMemberActivateView,
    TeamMemberDeactivateView,
    GalleryListView,
    GalleryDetailView,
    GalleryActivateView,
    GalleryDeactivateView,
    DocumentLibraryListView,
    DocumentLibraryDetailView,
    DocumentLibraryActivateView,
    DocumentLibraryDeactivateView,
    FeedbackListView,
    FeedbackDetailView,
)
from .schemes import (
    SchemeListView,
    SchemeDetailView,
    SchemeActivateView,
    SchemeDeactivateView,
)
from .experts import (
    ExpertListView,
    ExpertDetailView,
    ExpertActivateView,
    ExpertDeactivateView,
    ExpertEnquiriesView,
)
from .fpo_users import (
    FPOUserListView,
    FPOUserDetailView,
    FPOUserActivateView,
    FPOUserDeactivateView,
    FPOUserResetPasswordView,
)
from .reports import FPOSummaryReportView
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
    path('applications/',                                                    ApplicationListView.as_view(),            name='admin-applications-list'),
    path('applications/<int:fpo_id>/',                                       ApplicationDetailView.as_view(),          name='admin-applications-detail'),
    path('applications/<int:fpo_id>/reject/',                                ApplicationRejectView.as_view(),          name='admin-applications-reject'),
    path('applications/<int:fpo_id>/request-info/',                          ApplicationRequestInfoView.as_view(),     name='admin-applications-request-info'),
    path('applications/<int:fpo_id>/verify-document/<int:doc_id>/',          ApplicationVerifyDocumentView.as_view(),  name='admin-applications-verify-doc'),
    path('applications/<int:fpo_id>/set-user-limit/',                        ApplicationSetUserLimitView.as_view(),    name='admin-applications-set-limit'),
    path('applications/<int:fpo_id>/assign-tier/',                           ApplicationAssignTierView.as_view(),      name='admin-applications-assign-tier'),
    path('applications/<int:fpo_id>/tier-history/',                          ApplicationTierHistoryView.as_view(),     name='admin-applications-tier-history'),
    path('applications/<int:fpo_id>/activate/',                              ApplicationActivateView.as_view(),        name='admin-applications-activate'),
    path('applications/<int:fpo_id>/deactivate/',                            ApplicationDeactivateView.as_view(),      name='admin-applications-deactivate'),
    # Dashboard
    path('dashboard/stats/',               AdminDashboardStatsView.as_view(),            name='admin-dashboard-stats'),
    # Audit Logs
    path('audit-logs/',                     AuditLogListView.as_view(),                  name='admin-audit-logs'),
    # Ownership Claims
    path('ownership-claims/',                           OwnershipClaimListView.as_view(),   name='admin-claims-list'),
    path('ownership-claims/<int:claim_id>/',            OwnershipClaimDetailView.as_view(), name='admin-claims-detail'),
    path('ownership-claims/<int:claim_id>/approve/',    OwnershipClaimApproveView.as_view(),name='admin-claims-approve'),
    path('ownership-claims/<int:claim_id>/reject/',            OwnershipClaimRejectView.as_view(),      name='admin-claims-reject'),
    path('ownership-claims/<int:claim_id>/request-documents/', OwnershipClaimRequestDocsView.as_view(), name='admin-claims-request-docs'),
    # Role Page Access
    path('page-access/',                    RolePageAccessListView.as_view(),            name='admin-page-access-list'),
    path('page-access/<int:role_id>/',      RolePageAccessDetailView.as_view(),          name='admin-page-access-detail'),
    # External API Settings
    path('external-apis/',                  ExternalAPISettingsListView.as_view(),       name='admin-external-apis-list'),
    path('external-apis/<int:pk>/',        ExternalAPISettingsDetailView.as_view(),     name='admin-external-apis-detail'),
    path('external-apis/<int:pk>/activate/',   ExternalAPISettingsActivateView.as_view(),   name='admin-external-apis-activate'),
    path('external-apis/<int:pk>/deactivate/', ExternalAPISettingsDeactivateView.as_view(),  name='admin-external-apis-deactivate'),
    # Site Content CMS
    path('site-content/',             SiteBlockListView.as_view(),      name='admin-site-content-list'),
    path('site-content/<str:key>/',   SiteBlockDetailView.as_view(),    name='admin-site-content-detail'),
    path('announcements/',            AnnouncementListView.as_view(),   name='admin-announcements-list'),
    path('announcements/<int:pk>/',   AnnouncementDetailView.as_view(), name='admin-announcements-detail'),
    path('faqs/',                     FAQListView.as_view(),            name='admin-faqs-list'),
    path('faqs/<int:pk>/',            FAQDetailView.as_view(),          name='admin-faqs-detail'),

    path('quick-links/',                          QuickLinkListView.as_view(),       name='admin-quick-links-list'),
    path('quick-links/<int:pk>/',                 QuickLinkDetailView.as_view(),     name='admin-quick-links-detail'),
    path('quick-links/<int:pk>/logo/',            QuickLinkLogoDeleteView.as_view(), name='admin-quick-links-logo-delete'),
    path('quick-links/<int:pk>/activate/',        QuickLinkActivateView.as_view(),   name='admin-quick-links-activate'),
    path('quick-links/<int:pk>/deactivate/',      QuickLinkDeactivateView.as_view(), name='admin-quick-links-deactivate'),

    path('news-sources/',                          NewsSourceListView.as_view(),       name='admin-news-sources-list'),
    path('news-sources/<int:pk>/',                 NewsSourceDetailView.as_view(),     name='admin-news-sources-detail'),
    path('news-sources/<int:pk>/logo/',            NewsSourceLogoDeleteView.as_view(), name='admin-news-sources-logo-delete'),
    path('news-sources/<int:pk>/activate/',        NewsSourceActivateView.as_view(),   name='admin-news-sources-activate'),
    path('news-sources/<int:pk>/deactivate/',      NewsSourceDeactivateView.as_view(), name='admin-news-sources-deactivate'),

    path('team/',                          TeamMemberListView.as_view(),        name='admin-team-list'),
    path('team/<int:pk>/',                 TeamMemberDetailView.as_view(),      name='admin-team-detail'),
    path('team/<int:pk>/photo/',           TeamMemberPhotoDeleteView.as_view(), name='admin-team-photo-delete'),
    path('team/<int:pk>/activate/',        TeamMemberActivateView.as_view(),    name='admin-team-activate'),
    path('team/<int:pk>/deactivate/',      TeamMemberDeactivateView.as_view(),  name='admin-team-deactivate'),

    path('reports/fpo-summary/',             FPOSummaryReportView.as_view(),   name='admin-reports-fpo-summary'),

    path('feedback/',                        FeedbackListView.as_view(),       name='admin-feedback-list'),
    path('feedback/<int:pk>/',               FeedbackDetailView.as_view(),     name='admin-feedback-detail'),

    path('gallery/',                         GalleryListView.as_view(),        name='admin-gallery-list'),
    path('gallery/<int:pk>/',                GalleryDetailView.as_view(),      name='admin-gallery-detail'),
    path('gallery/<int:pk>/activate/',       GalleryActivateView.as_view(),    name='admin-gallery-activate'),
    path('gallery/<int:pk>/deactivate/',     GalleryDeactivateView.as_view(),  name='admin-gallery-deactivate'),

    path('documents/',                         DocumentLibraryListView.as_view(),       name='admin-documents-list'),
    path('documents/<int:pk>/',                DocumentLibraryDetailView.as_view(),     name='admin-documents-detail'),
    path('documents/<int:pk>/activate/',       DocumentLibraryActivateView.as_view(),   name='admin-documents-activate'),
    path('documents/<int:pk>/deactivate/',     DocumentLibraryDeactivateView.as_view(), name='admin-documents-deactivate'),
    # Schemes & Subsidies
    path('schemes/',                       SchemeListView.as_view(),        name='admin-schemes-list'),
    path('schemes/<int:pk>/',              SchemeDetailView.as_view(),      name='admin-schemes-detail'),
    path('schemes/<int:pk>/activate/',     SchemeActivateView.as_view(),    name='admin-schemes-activate'),
    path('schemes/<int:pk>/deactivate/',   SchemeDeactivateView.as_view(),  name='admin-schemes-deactivate'),
    # FPO User Management
    path('fpo-users/',                              FPOUserListView.as_view(),          name='admin-fpo-users-list'),
    path('fpo-users/<int:user_id>/',                FPOUserDetailView.as_view(),        name='admin-fpo-users-detail'),
    path('fpo-users/<int:user_id>/activate/',        FPOUserActivateView.as_view(),      name='admin-fpo-users-activate'),
    path('fpo-users/<int:user_id>/deactivate/',      FPOUserDeactivateView.as_view(),    name='admin-fpo-users-deactivate'),
    path('fpo-users/<int:user_id>/reset-password/',  FPOUserResetPasswordView.as_view(), name='admin-fpo-users-reset-password'),
    # Expert Directory
    path('experts/',                       ExpertListView.as_view(),        name='admin-experts-list'),
    path('experts/<int:pk>/',              ExpertDetailView.as_view(),      name='admin-experts-detail'),
    path('experts/<int:pk>/activate/',     ExpertActivateView.as_view(),    name='admin-experts-activate'),
    path('experts/<int:pk>/deactivate/',   ExpertDeactivateView.as_view(),  name='admin-experts-deactivate'),
    path('experts/<int:pk>/enquiries/',    ExpertEnquiriesView.as_view(),   name='admin-experts-enquiries'),
]
