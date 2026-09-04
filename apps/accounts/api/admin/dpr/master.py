"""
DPR Master Data — Admin CRUD endpoints for KAU staff.

Base view + 33 subclass pairs (list-create + detail).
Every write invalidates the corresponding public-read cache
(see apps/fpo/api/dpr/master.py — invalidate_master_cache).

Permissions: IsSubAdminOrSuperAdmin.
"""

from functools import lru_cache

from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions.rbac import IsSubAdminOrSuperAdmin
from apps.core.utils.responses import StandardResponse
from apps.database.models import (
    DPRProjectType, DPRProjectObjective, DPRProjectOutcome, DPRProjectRationale,
    DPRNatureOfBusiness, DPRComponent, DPRCapacityUnit, DPRCapacityBasis,
    DPRProductType, DPRProductCategory, DPRRawMaterialSource, DPRProcurementModel,
    DPRQualityParameter, DPRQualityStandard, DPRMarketingChannel, DPRCustomerCategory,
    DPRBuyerType, DPRPromotionalActivity, DPRTechnologyReason, DPRLandOwnershipType,
    DPRSiteStatus, DPRBuildingType, DPRCivilCategory, DPRMachineryCategory,
    DPRSupportingAsset, DPRFuelType, DPRWasteType, DPRRenewableInitiative,
    DPRTrainingArea, DPREnvironmentalImpact, DPRClimateRisk, DPRRiskCategory,
    DPRStatutoryRegistration, DPRIntendedMarket,
)
from apps.fpo.api.dpr.master import invalidate_master_cache


# ─────────────────────────────────────────────────────────────────────────────
# Serializer factory — full ModelSerializer (all fields writable)
# ─────────────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=64)
def _make_admin_serializer(model_cls):
    _model = model_cls

    class Serializer(serializers.ModelSerializer):
        class Meta:
            model = _model
            exclude = ('created_at', 'updated_at', 'created_by', 'updated_by')

    Serializer.__name__ = f'{model_cls.__name__}AdminSerializer'
    return Serializer


# ─────────────────────────────────────────────────────────────────────────────
# Base views — subclasses set `model`
# ─────────────────────────────────────────────────────────────────────────────

class BaseDPRMasterAdminListCreateView(APIView):
    """GET (list) + POST (create). Subclass sets `model`."""
    permission_classes = [IsAuthenticated, IsSubAdminOrSuperAdmin]
    model = None

    def get(self, request):
        serializer_cls = _make_admin_serializer(self.model)
        rows = self.model.objects.all().order_by('order', 'code')
        data = serializer_cls(rows, many=True).data
        return StandardResponse.success(data, f'{self.model._meta.verbose_name_plural} retrieved')

    def post(self, request):
        serializer_cls = _make_admin_serializer(self.model)
        ser = serializer_cls(data=request.data)
        if not ser.is_valid():
            return StandardResponse.error(ser.errors, status_code=400)
        obj = ser.save(created_by=request.user, updated_by=request.user)
        invalidate_master_cache(self.model)
        return StandardResponse.success(
            serializer_cls(obj).data,
            f'{self.model._meta.verbose_name} created',
            status_code=201,
        )


class BaseDPRMasterAdminDetailView(APIView):
    """GET / PATCH / DELETE by id. Subclass sets `model`."""
    permission_classes = [IsAuthenticated, IsSubAdminOrSuperAdmin]
    model = None

    def _get_obj(self, pk):
        try:
            return self.model.objects.get(pk=pk)
        except self.model.DoesNotExist:
            return None

    def get(self, request, pk):
        obj = self._get_obj(pk)
        if obj is None:
            return StandardResponse.error(f'{self.model._meta.verbose_name} not found', status_code=404)
        serializer_cls = _make_admin_serializer(self.model)
        return StandardResponse.success(serializer_cls(obj).data, 'Retrieved')

    def patch(self, request, pk):
        obj = self._get_obj(pk)
        if obj is None:
            return StandardResponse.error(f'{self.model._meta.verbose_name} not found', status_code=404)
        serializer_cls = _make_admin_serializer(self.model)
        ser = serializer_cls(obj, data=request.data, partial=True)
        if not ser.is_valid():
            return StandardResponse.error(ser.errors, status_code=400)
        obj = ser.save(updated_by=request.user)
        invalidate_master_cache(self.model)
        return StandardResponse.success(serializer_cls(obj).data, 'Updated')

    def delete(self, request, pk):
        obj = self._get_obj(pk)
        if obj is None:
            return StandardResponse.error(f'{self.model._meta.verbose_name} not found', status_code=404)
        obj.delete()
        invalidate_master_cache(self.model)
        return StandardResponse.success(None, 'Deleted', status_code=200)


# ─────────────────────────────────────────────────────────────────────────────
# 33 × 2 = 66 subclasses — list-create + detail per master model
# ─────────────────────────────────────────────────────────────────────────────

_ADMIN_TAG = ['Admin - DPR Master Data']


def _make_pair(model_cls, label):
    """Factory that returns (ListCreateView, DetailView) tuple for a model."""

    @extend_schema(tags=_ADMIN_TAG, summary=f'List / create {label}')
    class ListCreate(BaseDPRMasterAdminListCreateView):
        model = model_cls
    ListCreate.__name__ = f'{model_cls.__name__}AdminListCreateView'

    @extend_schema(tags=_ADMIN_TAG, summary=f'Retrieve / update / delete {label}')
    class Detail(BaseDPRMasterAdminDetailView):
        model = model_cls
    Detail.__name__ = f'{model_cls.__name__}AdminDetailView'

    return ListCreate, Detail


# Build all 33 pairs
ProjectTypeAdminListCreateView,          ProjectTypeAdminDetailView          = _make_pair(DPRProjectType,          'project type')
ProjectObjectiveAdminListCreateView,     ProjectObjectiveAdminDetailView     = _make_pair(DPRProjectObjective,     'project objective')
ProjectOutcomeAdminListCreateView,       ProjectOutcomeAdminDetailView       = _make_pair(DPRProjectOutcome,       'expected outcome')
ProjectRationaleAdminListCreateView,     ProjectRationaleAdminDetailView     = _make_pair(DPRProjectRationale,     'project rationale')
NatureOfBusinessAdminListCreateView,     NatureOfBusinessAdminDetailView     = _make_pair(DPRNatureOfBusiness,     'nature of business')
ProjectComponentAdminListCreateView,     ProjectComponentAdminDetailView     = _make_pair(DPRComponent,            'project component')
CapacityUnitAdminListCreateView,         CapacityUnitAdminDetailView         = _make_pair(DPRCapacityUnit,         'capacity unit')
CapacityBasisAdminListCreateView,        CapacityBasisAdminDetailView        = _make_pair(DPRCapacityBasis,        'capacity basis')
ProductTypeAdminListCreateView,          ProductTypeAdminDetailView          = _make_pair(DPRProductType,          'product type')
ProductCategoryAdminListCreateView,      ProductCategoryAdminDetailView      = _make_pair(DPRProductCategory,      'product category')
RawMaterialSourceAdminListCreateView,    RawMaterialSourceAdminDetailView    = _make_pair(DPRRawMaterialSource,    'raw material source')
ProcurementModelAdminListCreateView,     ProcurementModelAdminDetailView     = _make_pair(DPRProcurementModel,     'procurement model')
QualityParameterAdminListCreateView,     QualityParameterAdminDetailView     = _make_pair(DPRQualityParameter,     'quality parameter')
QualityStandardAdminListCreateView,      QualityStandardAdminDetailView      = _make_pair(DPRQualityStandard,      'quality standard')
MarketingChannelAdminListCreateView,     MarketingChannelAdminDetailView     = _make_pair(DPRMarketingChannel,     'marketing channel')
CustomerCategoryAdminListCreateView,     CustomerCategoryAdminDetailView     = _make_pair(DPRCustomerCategory,     'customer category')
BuyerTypeAdminListCreateView,            BuyerTypeAdminDetailView            = _make_pair(DPRBuyerType,            'buyer type')
IntendedMarketAdminListCreateView,       IntendedMarketAdminDetailView       = _make_pair(DPRIntendedMarket,       'intended market')
PromotionalActivityAdminListCreateView,  PromotionalActivityAdminDetailView  = _make_pair(DPRPromotionalActivity,  'promotional activity')
TechnologyReasonAdminListCreateView,     TechnologyReasonAdminDetailView     = _make_pair(DPRTechnologyReason,     'technology selection reason')
LandOwnershipTypeAdminListCreateView,    LandOwnershipTypeAdminDetailView    = _make_pair(DPRLandOwnershipType,    'land ownership type')
SiteStatusAdminListCreateView,           SiteStatusAdminDetailView           = _make_pair(DPRSiteStatus,           'site status')
BuildingTypeAdminListCreateView,         BuildingTypeAdminDetailView         = _make_pair(DPRBuildingType,         'building type')
CivilCategoryAdminListCreateView,        CivilCategoryAdminDetailView        = _make_pair(DPRCivilCategory,        'civil work category')
MachineryCategoryAdminListCreateView,    MachineryCategoryAdminDetailView    = _make_pair(DPRMachineryCategory,    'machinery category')
SupportingAssetAdminListCreateView,      SupportingAssetAdminDetailView      = _make_pair(DPRSupportingAsset,      'supporting asset')
FuelTypeAdminListCreateView,             FuelTypeAdminDetailView             = _make_pair(DPRFuelType,             'fuel type')
WasteTypeAdminListCreateView,            WasteTypeAdminDetailView            = _make_pair(DPRWasteType,            'waste type')
RenewableInitiativeAdminListCreateView,  RenewableInitiativeAdminDetailView  = _make_pair(DPRRenewableInitiative,  'renewable initiative')
TrainingAreaAdminListCreateView,         TrainingAreaAdminDetailView         = _make_pair(DPRTrainingArea,         'training area')
EnvironmentalImpactAdminListCreateView,  EnvironmentalImpactAdminDetailView  = _make_pair(DPREnvironmentalImpact,  'environmental impact')
ClimateRiskAdminListCreateView,          ClimateRiskAdminDetailView          = _make_pair(DPRClimateRisk,          'climate risk')
RiskCategoryAdminListCreateView,         RiskCategoryAdminDetailView         = _make_pair(DPRRiskCategory,         'risk category')
StatutoryRegistrationAdminListCreateView, StatutoryRegistrationAdminDetailView = _make_pair(DPRStatutoryRegistration, 'statutory registration')
