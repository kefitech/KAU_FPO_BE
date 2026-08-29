"""
DPR Master Data models — admin-editable dropdown lists per KAU spec Ch 2.

Every DPR-specific dropdown that isn't already covered by cross-module master data
(commodity, district, block, bank_name, legal_structure — those stay in MasterLookup)
gets its own dedicated table here.

Naming: DPR<Thing> — e.g. DPRComponent, DPRFuelType, DPRStatutoryRegistration.

All models inherit from `DPRMasterBase` which provides:
  - code, label_en, label_ml, order, is_active
  - created_at, updated_at (via TimeStampedModel)
  - created_by, updated_by (via AuditModel)

Spec: context/phase2/Dpr/Data Collection Module V1.0.pdf
Context: context/phase2/Dpr/DPR_V2_CONTEXT.md
"""

from ._base import DPRMasterBase

# Simple flat dropdowns — just code + label
from .project_type import DPRProjectType
from .project_objective import DPRProjectObjective
from .project_outcome import DPRProjectOutcome
from .project_rationale import DPRProjectRationale
from .nature_of_business import DPRNatureOfBusiness
from .capacity_unit import DPRCapacityUnit
from .capacity_basis import DPRCapacityBasis
from .product_category import DPRProductCategory
from .product_type import DPRProductType
from .raw_material_source import DPRRawMaterialSource
from .procurement_model import DPRProcurementModel
from .quality_parameter import DPRQualityParameter
from .quality_standard import DPRQualityStandard
from .marketing_channel import DPRMarketingChannel
from .customer_category import DPRCustomerCategory
from .buyer_type import DPRBuyerType
from .environmental_impact import DPREnvironmentalImpact
from .climate_risk import DPRClimateRisk
from .training_area import DPRTrainingArea
from .fuel_type import DPRFuelType
from .renewable_initiative import DPRRenewableInitiative
from .waste_type import DPRWasteType
from .civil_category import DPRCivilCategory
from .building_type import DPRBuildingType
from .supporting_asset import DPRSupportingAsset
from .land_ownership_type import DPRLandOwnershipType
from .site_status import DPRSiteStatus
from .risk_category import DPRRiskCategory
from .intended_market import DPRIntendedMarket

# Structured dropdowns — with per-category extra fields
from .component import DPRComponent
from .statutory_registration import DPRStatutoryRegistration
from .machinery_category import DPRMachineryCategory
from .technology_reason import DPRTechnologyReason
from .promotional_activity import DPRPromotionalActivity


__all__ = [
    'DPRMasterBase',
    # Simple
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
    'DPRIntendedMarket',
    # Structured
    'DPRComponent',
    'DPRStatutoryRegistration',
    'DPRMachineryCategory',
    'DPRTechnologyReason',
    'DPRPromotionalActivity',
]
