"""
DPR Master Data — read-only endpoints for authenticated FPO users.

Base view + 33 thin subclasses (one per DPR master model).
Response is cached in Redis (24h TTL), invalidated when admin edits master data
(see apps/accounts/api/admin/dpr/master.py).

Language: respects X-Language header (via LocaleMiddleware → request.language).
Returns `label` in requested language, plus `label_en` and `label_ml` always.

URLs mounted at /api/fpo/dpr/master/<slug>/ via apps/fpo/api/dpr/urls.py
"""

from functools import lru_cache

from django.core.cache import cache
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

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


# ─────────────────────────────────────────────────────────────────────────────
# Serializer factory — one ModelSerializer per model, cached
# ─────────────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=64)
def _make_read_serializer(model_cls):
    """
    Create a ModelSerializer for a DPR master model.
    Excludes audit fields; adds a language-aware `label` computed field.
    """
    _model = model_cls

    class Serializer(serializers.ModelSerializer):
        label = serializers.SerializerMethodField(
            help_text='Language-aware label — returns label_ml if X-Language: ml and label_ml is set, else label_en',
        )

        class Meta:
            model = _model
            exclude = ('created_at', 'updated_at', 'created_by', 'updated_by')

        def get_label(self, obj):
            return obj.label(self.context.get('language', 'en'))

    Serializer.__name__ = f'{model_cls.__name__}ReadSerializer'
    return Serializer


# ─────────────────────────────────────────────────────────────────────────────
# Base view — subclass just sets `model`
# ─────────────────────────────────────────────────────────────────────────────

CACHE_TTL_SECONDS = 86400  # 24 hours
CACHE_KEY_PREFIX = 'dpr_master_read'


def make_cache_key(model_cls, language):
    return f'{CACHE_KEY_PREFIX}:{model_cls._meta.db_table}:{language}'


def invalidate_master_cache(model_cls):
    """Called from admin CRUD after write. Clears cached responses for all languages."""
    for lang in ('en', 'ml'):
        cache.delete(make_cache_key(model_cls, lang))


class BaseDPRMasterReadView(APIView):
    """
    Base for all read-only DPR master data endpoints.
    Subclass sets `model = <DPRXxx>`.
    Override `get_queryset()` for category-specific ordering.
    """
    permission_classes = [IsAuthenticated]
    model = None
    tags = ['FPO - DPR Master Data']

    def get_queryset(self):
        return self.model.objects.filter(is_active=True)

    def get(self, request):
        language = getattr(request, 'language', 'en')
        key = make_cache_key(self.model, language)

        cached = cache.get(key)
        if cached is not None:
            return StandardResponse.success(
                cached, f'{self.model._meta.verbose_name_plural} retrieved (cached)',
            )

        serializer_cls = _make_read_serializer(self.model)
        data = serializer_cls(
            self.get_queryset(), many=True, context={'language': language},
        ).data

        cache.set(key, data, CACHE_TTL_SECONDS)
        return StandardResponse.success(
            data, f'{self.model._meta.verbose_name_plural} retrieved',
        )


# ─────────────────────────────────────────────────────────────────────────────
# 33 subclasses — one per DPR master model
# ─────────────────────────────────────────────────────────────────────────────

# --- Project definition ---

@extend_schema(tags=['FPO - DPR Master Data'], summary='List project types')
class ProjectTypeReadView(BaseDPRMasterReadView):
    model = DPRProjectType


@extend_schema(tags=['FPO - DPR Master Data'], summary='List project objectives')
class ProjectObjectiveReadView(BaseDPRMasterReadView):
    model = DPRProjectObjective


@extend_schema(tags=['FPO - DPR Master Data'], summary='List expected outcomes')
class ProjectOutcomeReadView(BaseDPRMasterReadView):
    model = DPRProjectOutcome


@extend_schema(tags=['FPO - DPR Master Data'], summary='List project rationales (29 KAU options)')
class ProjectRationaleReadView(BaseDPRMasterReadView):
    model = DPRProjectRationale


@extend_schema(tags=['FPO - DPR Master Data'], summary='List nature of business options (14 multi-select)')
class NatureOfBusinessReadView(BaseDPRMasterReadView):
    model = DPRNatureOfBusiness


@extend_schema(
    tags=['FPO - DPR Master Data'],
    summary='List project components (40 across 6 groups)',
    description='Grouped into 6 KAU spec groups: primary_production, processing_value_addition, storage_post_harvest, marketing_business_dev, service_enterprises, supporting_infrastructure.',
)
class ProjectComponentReadView(BaseDPRMasterReadView):
    model = DPRComponent

    def get_queryset(self):
        return super().get_queryset().order_by('group', 'order', 'code')


# --- Capacity & Products ---

@extend_schema(tags=['FPO - DPR Master Data'], summary='List capacity units')
class CapacityUnitReadView(BaseDPRMasterReadView):
    model = DPRCapacityUnit


@extend_schema(tags=['FPO - DPR Master Data'], summary='List capacity basis (per hour/shift/day/etc)')
class CapacityBasisReadView(BaseDPRMasterReadView):
    model = DPRCapacityBasis


@extend_schema(tags=['FPO - DPR Master Data'], summary='List product types (finished/intermediate/by-product/service)')
class ProductTypeReadView(BaseDPRMasterReadView):
    model = DPRProductType


@extend_schema(tags=['FPO - DPR Master Data'], summary='List product categories')
class ProductCategoryReadView(BaseDPRMasterReadView):
    model = DPRProductCategory


# --- Raw material & quality ---

@extend_schema(tags=['FPO - DPR Master Data'], summary='List raw material sources (11 KAU options)')
class RawMaterialSourceReadView(BaseDPRMasterReadView):
    model = DPRRawMaterialSource


@extend_schema(tags=['FPO - DPR Master Data'], summary='List procurement models')
class ProcurementModelReadView(BaseDPRMasterReadView):
    model = DPRProcurementModel


@extend_schema(tags=['FPO - DPR Master Data'], summary='List quality parameters')
class QualityParameterReadView(BaseDPRMasterReadView):
    model = DPRQualityParameter


@extend_schema(tags=['FPO - DPR Master Data'], summary='List quality standards / certifications')
class QualityStandardReadView(BaseDPRMasterReadView):
    model = DPRQualityStandard


# --- Market ---

@extend_schema(tags=['FPO - DPR Master Data'], summary='List marketing channels (16 options)')
class MarketingChannelReadView(BaseDPRMasterReadView):
    model = DPRMarketingChannel


@extend_schema(tags=['FPO - DPR Master Data'], summary='List customer categories')
class CustomerCategoryReadView(BaseDPRMasterReadView):
    model = DPRCustomerCategory


@extend_schema(tags=['FPO - DPR Master Data'], summary='List buyer types')
class BuyerTypeReadView(BaseDPRMasterReadView):
    model = DPRBuyerType


@extend_schema(tags=['FPO - DPR Master Data'], summary='List intended market scopes (local/state/national/export/etc)')
class IntendedMarketReadView(BaseDPRMasterReadView):
    model = DPRIntendedMarket


@extend_schema(
    tags=['FPO - DPR Master Data'],
    summary='List promotional activities',
    description='Each includes `is_digital` flag used by AI content generator.',
)
class PromotionalActivityReadView(BaseDPRMasterReadView):
    model = DPRPromotionalActivity


@extend_schema(
    tags=['FPO - DPR Master Data'],
    summary='List technology selection reasons',
    description='Each includes `requires_justification` flag — if True, user must write brief justification.',
)
class TechnologyReasonReadView(BaseDPRMasterReadView):
    model = DPRTechnologyReason


# --- Infrastructure & Machinery ---

@extend_schema(tags=['FPO - DPR Master Data'], summary='List land ownership types (7 options)')
class LandOwnershipTypeReadView(BaseDPRMasterReadView):
    model = DPRLandOwnershipType


@extend_schema(tags=['FPO - DPR Master Data'], summary='List site statuses')
class SiteStatusReadView(BaseDPRMasterReadView):
    model = DPRSiteStatus


@extend_schema(tags=['FPO - DPR Master Data'], summary='List building types (19 options)')
class BuildingTypeReadView(BaseDPRMasterReadView):
    model = DPRBuildingType


@extend_schema(tags=['FPO - DPR Master Data'], summary='List civil work categories')
class CivilCategoryReadView(BaseDPRMasterReadView):
    model = DPRCivilCategory


@extend_schema(
    tags=['FPO - DPR Master Data'],
    summary='List machinery categories',
    description='Each includes default depreciation rate and useful life used by the calculation engine (spec Ch 4.8).',
)
class MachineryCategoryReadView(BaseDPRMasterReadView):
    model = DPRMachineryCategory


@extend_schema(tags=['FPO - DPR Master Data'], summary='List supporting assets')
class SupportingAssetReadView(BaseDPRMasterReadView):
    model = DPRSupportingAsset


# --- Utilities & HR ---

@extend_schema(tags=['FPO - DPR Master Data'], summary='List fuel types (10 options)')
class FuelTypeReadView(BaseDPRMasterReadView):
    model = DPRFuelType


@extend_schema(tags=['FPO - DPR Master Data'], summary='List waste types (8 options)')
class WasteTypeReadView(BaseDPRMasterReadView):
    model = DPRWasteType


@extend_schema(tags=['FPO - DPR Master Data'], summary='List renewable energy initiatives')
class RenewableInitiativeReadView(BaseDPRMasterReadView):
    model = DPRRenewableInitiative


@extend_schema(tags=['FPO - DPR Master Data'], summary='List training areas')
class TrainingAreaReadView(BaseDPRMasterReadView):
    model = DPRTrainingArea


# --- Environment & Risk ---

@extend_schema(tags=['FPO - DPR Master Data'], summary='List environmental impact categories')
class EnvironmentalImpactReadView(BaseDPRMasterReadView):
    model = DPREnvironmentalImpact


@extend_schema(tags=['FPO - DPR Master Data'], summary='List climate risks')
class ClimateRiskReadView(BaseDPRMasterReadView):
    model = DPRClimateRisk


@extend_schema(tags=['FPO - DPR Master Data'], summary='List risk category groupings')
class RiskCategoryReadView(BaseDPRMasterReadView):
    model = DPRRiskCategory


# --- Compliance ---

@extend_schema(
    tags=['FPO - DPR Master Data'],
    summary='List statutory registrations (51 items across 6 KAU categories)',
    description='Each includes `category` (business/project/environmental/food_quality/labour/insurance), `default_mandatory` flag, and `issuing_authority_default`.',
)
class StatutoryRegistrationReadView(BaseDPRMasterReadView):
    model = DPRStatutoryRegistration

    def get_queryset(self):
        return super().get_queryset().order_by('category', 'order', 'code')
