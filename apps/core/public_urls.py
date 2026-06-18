"""
Public API URLs (no authentication required)
=============================================
Mounted at /api/public/ in config/urls.py
"""

from django.urls import path
from .api.master_data import PublicMasterDataView
from .api.cms_public import (
    PublicSiteContentView,
    PublicSiteBlockDetailView,
    PublicAnnouncementView,
    PublicFAQView,
    PublicPlatformStatsView,
    PublicLanguagesView,
)

urlpatterns = [
    path('master-data/',              PublicMasterDataView.as_view(),       name='public-master-data'),
    path('languages/',                PublicLanguagesView.as_view(),        name='public-languages'),
    path('site-content/',             PublicSiteContentView.as_view(),      name='public-site-content'),
    path('site-content/<str:key>/',   PublicSiteBlockDetailView.as_view(),  name='public-site-block'),
    path('announcements/',            PublicAnnouncementView.as_view(),     name='public-announcements'),
    path('faqs/',                     PublicFAQView.as_view(),              name='public-faqs'),
    path('stats/',                    PublicPlatformStatsView.as_view(),    name='public-stats'),
]
