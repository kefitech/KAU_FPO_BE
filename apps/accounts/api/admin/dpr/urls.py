"""
DPR Admin API URL routes — mounted at /api/admin/dpr/

Currently registered:
  - GET          /projects/                  — list all FPO DPR projects (paginated, filters)
  - GET/POST     /master/<slug>/             — 33 list-create endpoints
  - GET/PATCH/DELETE /master/<slug>/<id>/    — 33 detail endpoints

Section admin endpoints will be added when Phase 2 backend is built.

Author: Athul Gopan (Kefi Tech Solutions)
"""

from django.urls import path

from . import master as m
from .project_detail import DPRProjectAdminDetailView
from .projects import DPRProjectAdminListView


master_patterns = []


def _add(slug, list_cls, detail_cls):
    """Helper — add list-create + detail routes for a master category."""
    master_patterns.append(
        path(f'master/{slug}/', list_cls.as_view(), name=f'admin-dpr-master-{slug}-list')
    )
    master_patterns.append(
        path(f'master/{slug}/<int:pk>/', detail_cls.as_view(), name=f'admin-dpr-master-{slug}-detail')
    )


# --- Project definition ---
_add('project-types',           m.ProjectTypeAdminListCreateView,          m.ProjectTypeAdminDetailView)
_add('project-objectives',      m.ProjectObjectiveAdminListCreateView,     m.ProjectObjectiveAdminDetailView)
_add('project-outcomes',        m.ProjectOutcomeAdminListCreateView,       m.ProjectOutcomeAdminDetailView)
_add('project-rationales',      m.ProjectRationaleAdminListCreateView,     m.ProjectRationaleAdminDetailView)
_add('nature-of-business',      m.NatureOfBusinessAdminListCreateView,     m.NatureOfBusinessAdminDetailView)
_add('components',              m.ProjectComponentAdminListCreateView,     m.ProjectComponentAdminDetailView)

# --- Capacity & Products ---
_add('capacity-units',          m.CapacityUnitAdminListCreateView,         m.CapacityUnitAdminDetailView)
_add('capacity-basis',          m.CapacityBasisAdminListCreateView,        m.CapacityBasisAdminDetailView)
_add('product-types',           m.ProductTypeAdminListCreateView,          m.ProductTypeAdminDetailView)
_add('product-categories',      m.ProductCategoryAdminListCreateView,      m.ProductCategoryAdminDetailView)

# --- Raw material & quality ---
_add('raw-material-sources',    m.RawMaterialSourceAdminListCreateView,    m.RawMaterialSourceAdminDetailView)
_add('procurement-models',      m.ProcurementModelAdminListCreateView,     m.ProcurementModelAdminDetailView)
_add('quality-parameters',      m.QualityParameterAdminListCreateView,     m.QualityParameterAdminDetailView)
_add('quality-standards',       m.QualityStandardAdminListCreateView,      m.QualityStandardAdminDetailView)

# --- Market ---
_add('marketing-channels',      m.MarketingChannelAdminListCreateView,     m.MarketingChannelAdminDetailView)
_add('customer-categories',     m.CustomerCategoryAdminListCreateView,     m.CustomerCategoryAdminDetailView)
_add('buyer-types',             m.BuyerTypeAdminListCreateView,            m.BuyerTypeAdminDetailView)
_add('intended-markets',        m.IntendedMarketAdminListCreateView,       m.IntendedMarketAdminDetailView)
_add('promotional-activities',  m.PromotionalActivityAdminListCreateView,  m.PromotionalActivityAdminDetailView)
_add('technology-reasons',      m.TechnologyReasonAdminListCreateView,     m.TechnologyReasonAdminDetailView)

# --- Infrastructure & Machinery ---
_add('land-ownership-types',    m.LandOwnershipTypeAdminListCreateView,    m.LandOwnershipTypeAdminDetailView)
_add('site-statuses',           m.SiteStatusAdminListCreateView,           m.SiteStatusAdminDetailView)
_add('building-types',          m.BuildingTypeAdminListCreateView,         m.BuildingTypeAdminDetailView)
_add('civil-categories',        m.CivilCategoryAdminListCreateView,        m.CivilCategoryAdminDetailView)
_add('machinery-categories',    m.MachineryCategoryAdminListCreateView,    m.MachineryCategoryAdminDetailView)
_add('supporting-assets',       m.SupportingAssetAdminListCreateView,      m.SupportingAssetAdminDetailView)

# --- Utilities & HR ---
_add('fuel-types',              m.FuelTypeAdminListCreateView,             m.FuelTypeAdminDetailView)
_add('waste-types',             m.WasteTypeAdminListCreateView,            m.WasteTypeAdminDetailView)
_add('renewable-initiatives',   m.RenewableInitiativeAdminListCreateView,  m.RenewableInitiativeAdminDetailView)
_add('training-areas',          m.TrainingAreaAdminListCreateView,         m.TrainingAreaAdminDetailView)

# --- Environment & Risk ---
_add('environmental-impacts',   m.EnvironmentalImpactAdminListCreateView,  m.EnvironmentalImpactAdminDetailView)
_add('climate-risks',           m.ClimateRiskAdminListCreateView,          m.ClimateRiskAdminDetailView)
_add('risk-categories',         m.RiskCategoryAdminListCreateView,         m.RiskCategoryAdminDetailView)

# --- Compliance ---
_add('statutory-registrations', m.StatutoryRegistrationAdminListCreateView, m.StatutoryRegistrationAdminDetailView)


urlpatterns = [
    # Projects
    path('projects/', DPRProjectAdminListView.as_view(), name='admin-dpr-projects-list'),
    path('projects/<uuid:project_uuid>/', DPRProjectAdminDetailView.as_view(), name='admin-dpr-projects-detail'),
    # Master data (33 categories, list-create + detail each)
    *master_patterns,
]
