"""
DPR Data Element Models — matches KAU spec Ch 2 (23 data elements).

Layout: one file per KAU data element (2.2 and 2.3.2 through 2.3.23).
Each file exposes its model classes; this __init__ re-exports them all
so `from apps.database.models.dpr import DPRProject` works.

Adding a new data element:
1. Create `<data_element_name>.py` in this directory
2. Define main model + any nested item models
3. Add imports to this __init__ file
4. Add to `apps/database/models/__init__.py` main registry

Spec: context/phase2/Dpr/Data Collection Module V1.0.pdf
Plan: context/phase2/Dpr/BUILD_PLAN.md
Context: context/phase2/Dpr/DPR_V2_CONTEXT.md
"""

from .project import DPRProject
from .raw_material import (
    DPRSectionRawMaterial,
    DPRRawMaterial,
    DPRRawMaterialRisk,
    DPRPackagingMaterial,
    DPRConsumable,
)
from .market import (
    DPRSectionMarket,
    DPRMarketingProduct,
    DPRMarketingBuyer,
    DPRMarketingChannelSelection,
    DPRMarketingCompetitor,
    DPRMarketingRisk,
)
from .components import DPRSectionComponents
from .nature_of_business import DPRSectionNatureOfBusiness
from .investment import DPRSectionInvestment
from .products import DPRSectionProducts, DPRProductItem
from .location import DPRSectionLocation
from .rationale import DPRSectionRationale, DPRRationaleSelection
from .baseline import DPRSectionBaseline
from .capacity import DPRSectionCapacity
from .technology import DPRSectionTechnology, DPRTechnology, DPRTechnologyRisk
from .site import (
    DPRSectionSite,
    DPRLandParcel,
    DPRExistingInfrastructure,
    DPRSiteConstraint,
)
from .civil import (
    DPRSectionCivil,
    DPRExistingBuilding,
    DPRProposedBuilding,
    DPRSiteDevelopmentItem,
)
from .machinery import (
    DPRSectionMachinery,
    DPRMachineryItem,
    DPRSupportingAssetItem,
)
from .utilities import (
    DPRSectionUtilities,
    DPRFuelUsage,
    DPRProcessUtility,
    DPRWasteManagement,
    DPRRenewableInitiativeSelection,
)
from .hr import (
    DPRSectionHR,
    DPREmployeeCategory,
    DPRDepartmentStaffing,
    DPRTrainingRequirement,
)
from .finance import (
    DPRSectionFinance,
    DPRRevenueAssumption,
    DPRFinancialYearHistory,
)
from .compliance import (
    DPRSectionCompliance,
    DPRComplianceItem,
)
from .ess import (
    DPRSectionESS,
    DPREnvironmentalImpactSelection,
    DPRClimateRiskSelection,
)
from .implementation import (
    DPRSectionImplementation,
    DPRImplementationActivity,
    DPRImplementationMilestone,
)
from .risk import (
    DPRSectionRisk,
    DPRRiskItem,
)
