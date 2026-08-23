"""
Database Models for KAU-FPO Platform
====================================

All business and system models centralized in this app.

Author: Athul Gopan (Kefi Tech Solutions)
Created: 28-04-2026
"""

# Multilingual System Models
from .language import (
    Language,
    TranslationCategory,
    Translation,
    NotificationTemplateCode,
    NotificationTemplate,
)

# Notification System Models
from .notification import (
    NotificationChannelSettings,
    NotificationLog,
    InAppNotification,
)

# Menu Models
from .menu import MenuItem

# Two-Factor Auth
from .two_factor import AdminTwoFactor

# User Profile
from .user import UserProfile

# External API Settings
from .external_api import ExternalAPISettings

# Schemes & Expert Directory
from .schemes import (
    Scheme,
    SchemeCategory,
    Expert,
    ExpertCategory,
    ExpertEnquiry,
)

# Site Content CMS
from .cms import (
    SiteBlock,
    Announcement,
    AnnouncementCategory,
    FAQ,
    FAQCategory,
    QuickLink,
    Partner,
    NewsSource,
    NewsSourceCategory,
    TeamMember,
    GalleryAlbum,
    GalleryPhoto,
    DocumentLibrary,
    Feedback,
    FeedbackStatus,
    VisitorCount,
)

# FPO Module
from .fpo import (
    FPO,
    ApplicationStatusHistory,
    FPODocument,
    FPOUserMembership,
    TierCriteria,
    FPOTierHistory,
    FPOOwnershipClaim,
    FPOAction,
    RoleActionPermission,
    FPOMemberOverride,
    RolePageAccess,
    TierChoice,
    ClaimStatus,
    LEGAL_STRUCTURES_REQUIRING_CIN,
    TierDomain,
    TierCriterion,
    TierQuestion,
    FPOAssessment,
    AssessmentAnswer,
    AssessmentUpload,
)

# Phase 2 — Government Portal
from .government import GovernmentOfficialProfile

# Phase 2 — CBBO Portal
from .cbbo import CapacityBuildingReport, TrainingSession, TrainingAttendance

# Phase 2 — GIS (requires PostGIS + django.contrib.gis in INSTALLED_APPS)
from .gis import AgroClimaticZone, DistrictBoundary, FPOZoneAssignment, FPOCultivationArea, FPOWeatherSnapshot
# Phase 2 — AI Crop Recommendations
from .recommendations import MLModelVersion, CropRecommendation

# Phase 2 — AI DPR Generation
from .dpr import (
    DPRProject,
    DPRSection,
    DPRCalculation,
    DPRAIContent,
    DPRDocument,
    DPRMasterConfig,
)

# Phase 2 — Expert Booking
from .expert_booking import ExpertAvailability, ExpertBooking

# Phase 2 — Analytics
from .analytics import AnalyticsSnapshot

# Phase 2 — AI Chatbot
from .chat import ChatConversation, ChatMessage

# Phase 2 — Marketplace
from .marketplace import Product, BuyerDirectory, BuyerSellerMatch, MarketPrice

# Phase 2 — AI Marketing
from .marketing import MarketingStrategy


__all__ = [
    # Multilingual
    'Language',
    'TranslationCategory',
    'Translation',
    # Notification Templates
    'NotificationTemplateCode',
    'NotificationTemplate',
    # Notification System
    'NotificationChannelSettings',
    'NotificationLog',
    'InAppNotification',
    # Menu
    'MenuItem',
    # Two-Factor Auth
    'AdminTwoFactor',
    # User Profile
    'UserProfile',
    # FPO Module
    'FPO',
    'ApplicationStatusHistory',
    'FPODocument',
    'FPOUserMembership',
    'TierCriteria',
    'FPOTierHistory',
    'FPOOwnershipClaim',
    'FPOAction',
    'RoleActionPermission',
    'FPOMemberOverride',
    'RolePageAccess',
    'TierChoice',
    'ClaimStatus',
    'LEGAL_STRUCTURES_REQUIRING_CIN',
    # Tier Assessment Framework
    'TierDomain',
    'TierCriterion',
    'TierQuestion',
    'FPOAssessment',
    'AssessmentAnswer',
    'AssessmentUpload',
    # External API Settings
    'ExternalAPISettings',
    # Schemes & Expert Directory
    'Scheme',
    'SchemeCategory',
    'Expert',
    'ExpertCategory',
    'ExpertEnquiry',
    # Site Content CMS
    'SiteBlock',
    'Announcement',
    'AnnouncementCategory',
    'FAQ',
    'FAQCategory',
    # Phase 2 — Government Portal
    'GovernmentOfficialProfile',
    # Phase 2 — CBBO Portal
    'CapacityBuildingReport',
    'TrainingSession',
    'TrainingAttendance',
    # Phase 2 — GIS
    'AgroClimaticZone',
    'DistrictBoundary',
    'FPOZoneAssignment',
    'FPOCultivationArea',
    'FPOWeatherSnapshot',
    # Phase 2 — AI Crop Recommendations
    'MLModelVersion',
    'CropRecommendation',
    # Phase 2 — AI DPR Generation
    'DPRProject',
    'DPRSection',
    'DPRCalculation',
    'DPRAIContent',
    'DPRDocument',
    'DPRMasterConfig',
    # Phase 2 — Expert Booking
    'ExpertAvailability',
    'ExpertBooking',
    # Phase 2 — Analytics
    'AnalyticsSnapshot',
    # Phase 2 — AI Chatbot
    'ChatConversation',
    'ChatMessage',
    # Phase 2 — Marketplace
    'Product',
    'BuyerDirectory',
    'BuyerSellerMatch',
    'MarketPrice',
    # Phase 2 — AI Marketing
    'MarketingStrategy',
]
