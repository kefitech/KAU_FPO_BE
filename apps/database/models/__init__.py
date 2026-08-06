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
]
