"""
DPR API URL routes — mounted at /api/fpo/dpr/

Registered:
  - GET   /master/<slug>/                                          — 33 read-only master data endpoints (authenticated)
  - GET   /projects/                                               — list current FPO's DPR projects
  - POST  /projects/                                               — create a new DPR project
  - GET   /projects/<uuid>/                                        — retrieve a project
  - GET/PATCH /projects/<uuid>/sections/raw-material/              — §2.3.10 section GET + update
  - GET   /projects/<uuid>/sections/raw-material/readiness/        — §2.3.10 dry-run validators

Section CRUD endpoints for the remaining 20 data elements follow the same pattern.
"""

from django.urls import path

from . import master as m
from . import projects as p
from . import raw_material as rm
from . import market as mk
from . import components as cp
from . import nature_of_business as nb
from . import investment as inv
from . import products as pd
from . import location as loc
from . import rationale as rat
from . import baseline as bl
from . import capacity as cap
from . import technology as tech
from . import site as si
from . import civil as cv
from . import machinery as mch
from . import utilities as util
from . import hr as hr_mod
from . import finance as fin
from . import compliance as comp
from . import ess as ess_mod
from . import implementation as impl
from . import risk as rsk

master_patterns = [
    # --- Project definition ---
    path('master/project-types/',           m.ProjectTypeReadView.as_view(),           name='dpr-master-project-types'),
    path('master/project-objectives/',      m.ProjectObjectiveReadView.as_view(),      name='dpr-master-project-objectives'),
    path('master/project-outcomes/',        m.ProjectOutcomeReadView.as_view(),        name='dpr-master-project-outcomes'),
    path('master/project-rationales/',      m.ProjectRationaleReadView.as_view(),      name='dpr-master-project-rationales'),
    path('master/nature-of-business/',      m.NatureOfBusinessReadView.as_view(),      name='dpr-master-nature-of-business'),
    path('master/components/',              m.ProjectComponentReadView.as_view(),      name='dpr-master-components'),

    # --- Capacity & Products ---
    path('master/capacity-units/',          m.CapacityUnitReadView.as_view(),          name='dpr-master-capacity-units'),
    path('master/capacity-basis/',          m.CapacityBasisReadView.as_view(),         name='dpr-master-capacity-basis'),
    path('master/product-types/',           m.ProductTypeReadView.as_view(),           name='dpr-master-product-types'),
    path('master/product-categories/',      m.ProductCategoryReadView.as_view(),       name='dpr-master-product-categories'),

    # --- Raw material & quality ---
    path('master/raw-material-sources/',    m.RawMaterialSourceReadView.as_view(),     name='dpr-master-raw-material-sources'),
    path('master/procurement-models/',      m.ProcurementModelReadView.as_view(),      name='dpr-master-procurement-models'),
    path('master/quality-parameters/',      m.QualityParameterReadView.as_view(),      name='dpr-master-quality-parameters'),
    path('master/quality-standards/',       m.QualityStandardReadView.as_view(),       name='dpr-master-quality-standards'),

    # --- Market ---
    path('master/marketing-channels/',      m.MarketingChannelReadView.as_view(),      name='dpr-master-marketing-channels'),
    path('master/customer-categories/',     m.CustomerCategoryReadView.as_view(),      name='dpr-master-customer-categories'),
    path('master/buyer-types/',             m.BuyerTypeReadView.as_view(),             name='dpr-master-buyer-types'),
    path('master/intended-markets/',        m.IntendedMarketReadView.as_view(),        name='dpr-master-intended-markets'),
    path('master/promotional-activities/',  m.PromotionalActivityReadView.as_view(),   name='dpr-master-promotional-activities'),
    path('master/technology-reasons/',      m.TechnologyReasonReadView.as_view(),      name='dpr-master-technology-reasons'),

    # --- Infrastructure & Machinery ---
    path('master/land-ownership-types/',    m.LandOwnershipTypeReadView.as_view(),     name='dpr-master-land-ownership-types'),
    path('master/site-statuses/',           m.SiteStatusReadView.as_view(),            name='dpr-master-site-statuses'),
    path('master/building-types/',          m.BuildingTypeReadView.as_view(),          name='dpr-master-building-types'),
    path('master/civil-categories/',        m.CivilCategoryReadView.as_view(),         name='dpr-master-civil-categories'),
    path('master/machinery-categories/',    m.MachineryCategoryReadView.as_view(),     name='dpr-master-machinery-categories'),
    path('master/supporting-assets/',       m.SupportingAssetReadView.as_view(),       name='dpr-master-supporting-assets'),

    # --- Utilities & HR ---
    path('master/fuel-types/',              m.FuelTypeReadView.as_view(),              name='dpr-master-fuel-types'),
    path('master/waste-types/',             m.WasteTypeReadView.as_view(),             name='dpr-master-waste-types'),
    path('master/renewable-initiatives/',   m.RenewableInitiativeReadView.as_view(),   name='dpr-master-renewable-initiatives'),
    path('master/training-areas/',          m.TrainingAreaReadView.as_view(),          name='dpr-master-training-areas'),

    # --- Environment & Risk ---
    path('master/environmental-impacts/',   m.EnvironmentalImpactReadView.as_view(),   name='dpr-master-environmental-impacts'),
    path('master/climate-risks/',           m.ClimateRiskReadView.as_view(),           name='dpr-master-climate-risks'),
    path('master/risk-categories/',         m.RiskCategoryReadView.as_view(),          name='dpr-master-risk-categories'),

    # --- Compliance ---
    path('master/statutory-registrations/', m.StatutoryRegistrationReadView.as_view(), name='dpr-master-statutory-registrations'),
]

project_patterns = [
    path('projects/', p.DPRProjectListCreateView.as_view(), name='dpr-projects-list-create'),
    path('projects/<uuid:project_uuid>/', p.DPRProjectDetailView.as_view(), name='dpr-project-detail'),
    path(
        'projects/<uuid:project_uuid>/readiness/',
        p.DPRProjectIdentificationReadinessView.as_view(),
        name='dpr-project-identification-readiness',
    ),
]

section_patterns = [
    # §2.3.10 Raw Material (pilot pattern)
    path(
        'projects/<uuid:project_uuid>/sections/raw-material/',
        rm.DPRRawMaterialSectionView.as_view(),
        name='dpr-section-raw-material',
    ),
    path(
        'projects/<uuid:project_uuid>/sections/raw-material/readiness/',
        rm.DPRRawMaterialSectionReadinessView.as_view(),
        name='dpr-section-raw-material-readiness',
    ),
    # §2.3.11 Market Assessment
    path(
        'projects/<uuid:project_uuid>/sections/market/',
        mk.DPRMarketSectionView.as_view(),
        name='dpr-section-market',
    ),
    path(
        'projects/<uuid:project_uuid>/sections/market/readiness/',
        mk.DPRMarketSectionReadinessView.as_view(),
        name='dpr-section-market-readiness',
    ),
    # §2.3.2 Project Components
    path(
        'projects/<uuid:project_uuid>/sections/components/',
        cp.DPRComponentsSectionView.as_view(),
        name='dpr-section-components',
    ),
    path(
        'projects/<uuid:project_uuid>/sections/components/readiness/',
        cp.DPRComponentsSectionReadinessView.as_view(),
        name='dpr-section-components-readiness',
    ),
    # §2.3.3 Nature of Business
    path(
        'projects/<uuid:project_uuid>/sections/nature-of-business/',
        nb.DPRNatureOfBusinessSectionView.as_view(),
        name='dpr-section-nature-of-business',
    ),
    path(
        'projects/<uuid:project_uuid>/sections/nature-of-business/readiness/',
        nb.DPRNatureOfBusinessSectionReadinessView.as_view(),
        name='dpr-section-nature-of-business-readiness',
    ),
    # §2.3.4 Proposed Project Investment
    path(
        'projects/<uuid:project_uuid>/sections/investment/',
        inv.DPRInvestmentSectionView.as_view(),
        name='dpr-section-investment',
    ),
    path(
        'projects/<uuid:project_uuid>/sections/investment/readiness/',
        inv.DPRInvestmentSectionReadinessView.as_view(),
        name='dpr-section-investment-readiness',
    ),
    # §2.3.5 Proposed Products and Services
    path(
        'projects/<uuid:project_uuid>/sections/products/',
        pd.DPRProductsSectionView.as_view(),
        name='dpr-section-products',
    ),
    path(
        'projects/<uuid:project_uuid>/sections/products/readiness/',
        pd.DPRProductsSectionReadinessView.as_view(),
        name='dpr-section-products-readiness',
    ),
    # §2.3.6 Proposed Project Location
    path(
        'projects/<uuid:project_uuid>/sections/location/',
        loc.DPRLocationSectionView.as_view(),
        name='dpr-section-location',
    ),
    path(
        'projects/<uuid:project_uuid>/sections/location/readiness/',
        loc.DPRLocationSectionReadinessView.as_view(),
        name='dpr-section-location-readiness',
    ),
    # §2.3.7 Project Rationale
    path(
        'projects/<uuid:project_uuid>/sections/rationale/',
        rat.DPRRationaleSectionView.as_view(),
        name='dpr-section-rationale',
    ),
    path(
        'projects/<uuid:project_uuid>/sections/rationale/readiness/',
        rat.DPRRationaleSectionReadinessView.as_view(),
        name='dpr-section-rationale-readiness',
    ),
    # §2.3.8 Current Status / Baseline
    path(
        'projects/<uuid:project_uuid>/sections/baseline/',
        bl.DPRBaselineSectionView.as_view(),
        name='dpr-section-baseline',
    ),
    path(
        'projects/<uuid:project_uuid>/sections/baseline/readiness/',
        bl.DPRBaselineSectionReadinessView.as_view(),
        name='dpr-section-baseline-readiness',
    ),
    # §2.3.9 Capacity & Production
    path(
        'projects/<uuid:project_uuid>/sections/capacity/',
        cap.DPRCapacitySectionView.as_view(),
        name='dpr-section-capacity',
    ),
    path(
        'projects/<uuid:project_uuid>/sections/capacity/readiness/',
        cap.DPRCapacitySectionReadinessView.as_view(),
        name='dpr-section-capacity-readiness',
    ),
    # §2.3.12 Technology Selection & Technical Feasibility
    path(
        'projects/<uuid:project_uuid>/sections/technology/',
        tech.DPRTechnologySectionView.as_view(),
        name='dpr-section-technology',
    ),
    path(
        'projects/<uuid:project_uuid>/sections/technology/readiness/',
        tech.DPRTechnologySectionReadinessView.as_view(),
        name='dpr-section-technology-readiness',
    ),
    # §2.3.13 Land & Site Suitability
    path(
        'projects/<uuid:project_uuid>/sections/site/',
        si.DPRSiteSectionView.as_view(),
        name='dpr-section-site',
    ),
    path(
        'projects/<uuid:project_uuid>/sections/site/readiness/',
        si.DPRSiteSectionReadinessView.as_view(),
        name='dpr-section-site-readiness',
    ),
    # §2.3.14 Civil Works
    path(
        'projects/<uuid:project_uuid>/sections/civil/',
        cv.DPRCivilSectionView.as_view(),
        name='dpr-section-civil',
    ),
    path(
        'projects/<uuid:project_uuid>/sections/civil/readiness/',
        cv.DPRCivilSectionReadinessView.as_view(),
        name='dpr-section-civil-readiness',
    ),
    # §2.3.15 Plant & Machinery
    path(
        'projects/<uuid:project_uuid>/sections/machinery/',
        mch.DPRMachinerySectionView.as_view(),
        name='dpr-section-machinery',
    ),
    path(
        'projects/<uuid:project_uuid>/sections/machinery/readiness/',
        mch.DPRMachinerySectionReadinessView.as_view(),
        name='dpr-section-machinery-readiness',
    ),
    # §2.3.16 Utilities & Support Services
    path(
        'projects/<uuid:project_uuid>/sections/utilities/',
        util.DPRUtilitiesSectionView.as_view(),
        name='dpr-section-utilities',
    ),
    path(
        'projects/<uuid:project_uuid>/sections/utilities/readiness/',
        util.DPRUtilitiesSectionReadinessView.as_view(),
        name='dpr-section-utilities-readiness',
    ),
    # §2.3.17 HR & Organisational Structure
    path(
        'projects/<uuid:project_uuid>/sections/hr/',
        hr_mod.DPRHRSectionView.as_view(),
        name='dpr-section-hr',
    ),
    path(
        'projects/<uuid:project_uuid>/sections/hr/readiness/',
        hr_mod.DPRHRSectionReadinessView.as_view(),
        name='dpr-section-hr-readiness',
    ),
    # §2.3.18 Finance & Means of Finance
    path(
        'projects/<uuid:project_uuid>/sections/finance/',
        fin.DPRFinanceSectionView.as_view(),
        name='dpr-section-finance',
    ),
    path(
        'projects/<uuid:project_uuid>/sections/finance/readiness/',
        fin.DPRFinanceSectionReadinessView.as_view(),
        name='dpr-section-finance-readiness',
    ),
    # §2.3.19 Statutory Compliance
    path(
        'projects/<uuid:project_uuid>/sections/compliance/',
        comp.DPRComplianceSectionView.as_view(),
        name='dpr-section-compliance',
    ),
    path(
        'projects/<uuid:project_uuid>/sections/compliance/readiness/',
        comp.DPRComplianceSectionReadinessView.as_view(),
        name='dpr-section-compliance-readiness',
    ),
    # §2.3.20 Environmental, Social & Sustainability Assessment
    path(
        'projects/<uuid:project_uuid>/sections/ess/',
        ess_mod.DPRESSSectionView.as_view(),
        name='dpr-section-ess',
    ),
    path(
        'projects/<uuid:project_uuid>/sections/ess/readiness/',
        ess_mod.DPRESSSectionReadinessView.as_view(),
        name='dpr-section-ess-readiness',
    ),
    # §2.3.21 Project Implementation Plan
    path(
        'projects/<uuid:project_uuid>/sections/implementation/',
        impl.DPRImplementationSectionView.as_view(),
        name='dpr-section-implementation',
    ),
    path(
        'projects/<uuid:project_uuid>/sections/implementation/readiness/',
        impl.DPRImplementationSectionReadinessView.as_view(),
        name='dpr-section-implementation-readiness',
    ),
    # §2.3.22 Risk Assessment and Mitigation Plan
    path(
        'projects/<uuid:project_uuid>/sections/risk/',
        rsk.DPRRiskSectionView.as_view(),
        name='dpr-section-risk',
    ),
    path(
        'projects/<uuid:project_uuid>/sections/risk/readiness/',
        rsk.DPRRiskSectionReadinessView.as_view(),
        name='dpr-section-risk-readiness',
    ),
]

urlpatterns = [
    *master_patterns,
    *project_patterns,
    *section_patterns,
]
