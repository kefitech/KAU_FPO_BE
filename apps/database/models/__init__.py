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
# v1 removed 2026-08-24. Fresh rebuild in progress under `dpr/` package.
# See context/phase2/Dpr/DPR_V2_CONTEXT.md
from .dpr import (
    DPRProject,
    DPRSectionRawMaterial,
    DPRRawMaterial,
    DPRRawMaterialRisk,
    DPRPackagingMaterial,
    DPRConsumable,
    DPRSectionMarket,
    DPRMarketingProduct,
    DPRMarketingBuyer,
    DPRMarketingChannelSelection,
    DPRMarketingCompetitor,
    DPRMarketingRisk,
    DPRSectionComponents,
    DPRSectionNatureOfBusiness,
    DPRSectionInvestment,
    DPRSectionProducts,
    DPRProductItem,
    DPRSectionLocation,
    DPRSectionRationale,
    DPRRationaleSelection,
    DPRSectionBaseline,
    DPRSectionCapacity,
    DPRSectionTechnology,
    DPRTechnology,
    DPRTechnologyRisk,
    DPRSectionSite,
    DPRLandParcel,
    DPRExistingInfrastructure,
    DPRSiteConstraint,
    DPRSectionCivil,
    DPRExistingBuilding,
    DPRProposedBuilding,
    DPRSiteDevelopmentItem,
    DPRSectionMachinery,
    DPRMachineryItem,
    DPRSupportingAssetItem,
    DPRSectionUtilities,
    DPRFuelUsage,
    DPRProcessUtility,
    DPRWasteManagement,
    DPRRenewableInitiativeSelection,
    DPRSectionHR,
    DPREmployeeCategory,
    DPRDepartmentStaffing,
    DPRTrainingRequirement,
    DPRSectionFinance,
    DPRRevenueAssumption,
    DPRFinancialYearHistory,
    DPRSectionCompliance,
    DPRComplianceItem,
    DPRSectionESS,
    DPREnvironmentalImpactSelection,
    DPRClimateRiskSelection,
    DPRSectionImplementation,
    DPRImplementationActivity,
    DPRImplementationMilestone,
    DPRSectionRisk,
    DPRRiskItem,
)
from .dpr.master import (
    DPRProjectType,
    DPRProjectObjective,
    DPRProjectOutcome,
    DPRProjectRationale,
    DPRNatureOfBusiness,
    DPRCapacityUnit,
    DPRCapacityBasis,
    DPRProductCategory,
    DPRProductType,
    DPRRawMaterialSource,
    DPRProcurementModel,
    DPRQualityParameter,
    DPRQualityStandard,
    DPRMarketingChannel,
    DPRCustomerCategory,
    DPRBuyerType,
    DPREnvironmentalImpact,
    DPRClimateRisk,
    DPRTrainingArea,
    DPRFuelType,
    DPRRenewableInitiative,
    DPRWasteType,
    DPRCivilCategory,
    DPRBuildingType,
    DPRSupportingAsset,
    DPRLandOwnershipType,
    DPRSiteStatus,
    DPRRiskCategory,
    DPRComponent,
    DPRStatutoryRegistration,
    DPRMachineryCategory,
    DPRTechnologyReason,
    DPRPromotionalActivity,
    DPRIntendedMarket,
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

# Phase 2 — AI Service Control & Usage Tracking
from .ai_config import AIServiceConfig, AIUsageLog


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
    # Phase 2 — AI DPR Generation — Project + Sections
    'DPRProject',
    'DPRSectionRawMaterial',
    'DPRRawMaterial',
    'DPRRawMaterialRisk',
    'DPRPackagingMaterial',
    'DPRConsumable',
    'DPRSectionMarket',
    'DPRMarketingProduct',
    'DPRMarketingBuyer',
    'DPRMarketingChannelSelection',
    'DPRMarketingCompetitor',
    'DPRMarketingRisk',
    'DPRSectionComponents',
    'DPRSectionNatureOfBusiness',
    'DPRSectionInvestment',
    'DPRSectionProducts',
    'DPRProductItem',
    'DPRSectionLocation',
    'DPRSectionRationale',
    'DPRRationaleSelection',
    'DPRSectionBaseline',
    'DPRSectionCapacity',
    'DPRSectionTechnology',
    'DPRTechnology',
    'DPRTechnologyRisk',
    'DPRSectionSite',
    'DPRLandParcel',
    'DPRExistingInfrastructure',
    'DPRSiteConstraint',
    'DPRSectionCivil',
    'DPRExistingBuilding',
    'DPRProposedBuilding',
    'DPRSiteDevelopmentItem',
    'DPRSectionMachinery',
    'DPRMachineryItem',
    'DPRSupportingAssetItem',
    'DPRSectionUtilities',
    'DPRFuelUsage',
    'DPRProcessUtility',
    'DPRWasteManagement',
    'DPRRenewableInitiativeSelection',
    'DPRSectionHR',
    'DPREmployeeCategory',
    'DPRDepartmentStaffing',
    'DPRTrainingRequirement',
    'DPRSectionFinance',
    'DPRRevenueAssumption',
    'DPRFinancialYearHistory',
    'DPRSectionCompliance',
    'DPRComplianceItem',
    'DPRSectionESS',
    'DPREnvironmentalImpactSelection',
    'DPRClimateRiskSelection',
    'DPRSectionImplementation',
    'DPRImplementationActivity',
    'DPRImplementationMilestone',
    'DPRSectionRisk',
    'DPRRiskItem',
    # Phase 2 — AI DPR Generation — Master Data
    'DPRProjectType',
    'DPRProjectObjective',
    'DPRProjectOutcome',
    'DPRProjectRationale',
    'DPRNatureOfBusiness',
    'DPRCapacityUnit',
    'DPRCapacityBasis',
    'DPRProductCategory',
    'DPRProductType',
    'DPRRawMaterialSource',
    'DPRProcurementModel',
    'DPRQualityParameter',
    'DPRQualityStandard',
    'DPRMarketingChannel',
    'DPRCustomerCategory',
    'DPRBuyerType',
    'DPREnvironmentalImpact',
    'DPRClimateRisk',
    'DPRTrainingArea',
    'DPRFuelType',
    'DPRRenewableInitiative',
    'DPRWasteType',
    'DPRCivilCategory',
    'DPRBuildingType',
    'DPRSupportingAsset',
    'DPRLandOwnershipType',
    'DPRSiteStatus',
    'DPRRiskCategory',
    'DPRComponent',
    'DPRStatutoryRegistration',
    'DPRMachineryCategory',
    'DPRTechnologyReason',
    'DPRPromotionalActivity',
    'DPRIntendedMarket',
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
    # Phase 2 — AI Service Control & Usage Tracking
    'AIServiceConfig',
    'AIUsageLog',
]
