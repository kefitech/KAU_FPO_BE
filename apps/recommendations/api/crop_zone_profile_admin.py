"""
Admin — Crop Zone Profile CRUD (ml_service's live crop-eligibility knowledge base)
====================================================================================
GET/POST          /api/admin/crop-zone-profiles/
GET/PATCH/DELETE  /api/admin/crop-zone-profiles/{id}/
POST              /api/admin/crop-zone-profiles/{id}/activate/
POST              /api/admin/crop-zone-profiles/{id}/deactivate/

NOT the same data as CropPackageOfPractices (pop_admin.py) -- this is upstream
of that: it drives which crops ml_service's predict_crops() even considers as
candidates for a zone, and the documented temperature/pH/season text shown in
a recommendation's reasoning. See CropZoneProfile's model docstring.

Every mutation (create/update/delete/activate/deactivate) re-exports ALL active
rows to ml_service's crop_profiles_service_zones.csv and asks ml_service to
hot-reload its in-memory knowledge base -- best-effort: the DB write always
succeeds even if ml_service is unreachable (same graceful-degradation stance
as MLModelVersionActivateView, not the stricter block-on-failure stance
MLModelVersionAdminView takes for a brand new predictive artifact -- this is
documentation content, not a new model).
"""
import csv
import logging
from pathlib import Path

import httpx
from django.conf import settings
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import filters, serializers
from rest_framework.decorators import action

from apps.core.permissions.rbac import IsAdmin, IsAuthenticated
from apps.core.services.lookup import resolve_master_name
from apps.core.services.translation import t
from apps.core.utils.pagination import StandardPagination
from apps.core.utils.responses import StandardResponse
from apps.core.views import TranslatedViewSet
from apps.database.models import CropZoneProfile

logger = logging.getLogger(__name__)

# Mirrors ml_service/retrain_pipeline.py's KAU_TO_SERVICE_ZONE exactly -- a KAU
# book zone expands into these service zones. Duplicated (not imported) because
# ml_service is a separate process/deployment; ml_service/data_access_v3.py
# already duplicates its own zone/soil tables the same way. Keep these two in
# sync if either ever changes.
KAU_TO_SERVICE_ZONE = {
    'Coastal Plain': ['coastal_zone'],
    'High Hills': ['high_ranges'],
    'Midland Laterites': ['northern_zone', 'central_zone', 'southern_zone'],
    'Foothills': ['northern_zone', 'central_zone', 'southern_zone'],
    'Palakkad Plain': ['central_zone'],
    'General (all zones)': ['coastal_zone', 'southern_zone', 'central_zone', 'northern_zone', 'high_ranges'],
}

EXPORT_CSV_COLUMNS = [
    'crop_name', 'agro_zone', 'crop_group', 'temp_lo', 'temp_hi', 'ph_lo', 'ph_hi',
    'seasons_text', 'ph_is_real', 'temp_is_real', 'service_zone', 'kau_zone_source',
]


def export_and_notify():
    """
    Writes every active CropZoneProfile row, expanded per service zone via
    KAU_TO_SERVICE_ZONE, to ML_SERVICE_DATA_DIR/crop_profiles_service_zones.csv
    -- same shape ml_service's CropKnowledgeBase already expects -- then asks
    ml_service to hot-reload from it. Never raises: a write failure or an
    unreachable ml_service is logged, not surfaced to the caller, since the DB
    write (the source of truth) already succeeded by the time this runs.
    """
    rows = []
    profiles = CropZoneProfile.objects.filter(is_active=True, is_deleted=False).order_by('crop_name', 'kau_zone')
    for p in profiles:
        for service_zone in KAU_TO_SERVICE_ZONE.get(p.kau_zone, []):
            rows.append({
                'crop_name': p.crop_name, 'agro_zone': p.kau_zone, 'crop_group': p.crop_group,
                'temp_lo': p.temp_lo, 'temp_hi': p.temp_hi, 'ph_lo': p.ph_lo, 'ph_hi': p.ph_hi,
                'seasons_text': p.seasons_text, 'ph_is_real': p.ph_is_real, 'temp_is_real': p.temp_is_real,
                'service_zone': service_zone, 'kau_zone_source': p.kau_zone,
            })

    try:
        out_dir = Path(settings.ML_SERVICE_DATA_DIR)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / 'crop_profiles_service_zones.csv'
        with open(out_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=EXPORT_CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
    except OSError:
        logger.exception('export_and_notify: failed to write crop_profiles_service_zones.csv')
        return

    try:
        response = httpx.post(f'{settings.ML_SERVICE_URL}/reload-knowledge-base/', timeout=10.0)
        response.raise_for_status()
    except httpx.HTTPError:
        logger.warning(
            'export_and_notify: wrote %d rows but could not reach ml_service to hot-reload -- '
            'it will pick up the change on its next restart instead', len(rows), exc_info=True,
        )


class CropZoneProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = CropZoneProfile
        fields = [
            'id', 'crop_name', 'crop_group', 'kau_zone', 'temp_lo', 'temp_hi', 'ph_lo', 'ph_hi',
            'seasons_text', 'temp_is_real', 'ph_is_real', 'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_crop_name(self, value):
        value = value.strip()
        # Unchanged values pass, so editing other fields of an older row is never blocked
        if self.instance and value == self.instance.crop_name:
            return value
        canonical = resolve_master_name('crop_name', value)
        if canonical is None:
            raise serializers.ValidationError("Choose a crop from the Master Data 'Crop Names' list.")
        return canonical

    def validate_crop_group(self, value):
        value = value.strip()
        if not value or (self.instance and value == self.instance.crop_group):
            return value
        canonical = resolve_master_name('crop_group', value)
        if canonical is None:
            raise serializers.ValidationError("Choose a group from the Master Data 'Crop Groups' list.")
        return canonical

    def validate(self, attrs):
        language = getattr(self.context.get('request'), 'language', 'en')

        temp_lo = attrs.get('temp_lo', getattr(self.instance, 'temp_lo', None))
        temp_hi = attrs.get('temp_hi', getattr(self.instance, 'temp_hi', None))
        if temp_lo is not None and temp_hi is not None and temp_lo > temp_hi:
            raise serializers.ValidationError(
                {'temp_hi': t('recommendations.zone_profile_temp_range', language)}
            )
        ph_lo = attrs.get('ph_lo', getattr(self.instance, 'ph_lo', None))
        ph_hi = attrs.get('ph_hi', getattr(self.instance, 'ph_hi', None))
        if ph_lo is not None and ph_hi is not None and ph_lo > ph_hi:
            raise serializers.ValidationError(
                {'ph_hi': t('recommendations.zone_profile_ph_range', language)}
            )

        crop_name = attrs.get('crop_name', getattr(self.instance, 'crop_name', None))
        kau_zone = attrs.get('kau_zone', getattr(self.instance, 'kau_zone', None))
        if crop_name and kau_zone:
            qs = CropZoneProfile.objects.filter(
                crop_name__iexact=crop_name.strip(), kau_zone=kau_zone, is_deleted=False,
            )
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    t('recommendations.zone_profile_duplicate', language, crop_name=crop_name, kau_zone=kau_zone)
                )
        return attrs


@extend_schema_view(
    list=extend_schema(tags=['Admin - Crop Zone Profiles']),
    create=extend_schema(tags=['Admin - Crop Zone Profiles']),
    retrieve=extend_schema(tags=['Admin - Crop Zone Profiles']),
    update=extend_schema(tags=['Admin - Crop Zone Profiles']),
    partial_update=extend_schema(tags=['Admin - Crop Zone Profiles']),
    destroy=extend_schema(tags=['Admin - Crop Zone Profiles']),
)
class CropZoneProfileViewSet(TranslatedViewSet):
    serializer_class = CropZoneProfileSerializer
    permission_classes = [IsAuthenticated, IsAdmin]
    pagination_class = StandardPagination
    filter_backends = [filters.SearchFilter]
    search_fields = ['crop_name', 'crop_group', 'kau_zone']

    list_message = 'recommendations.zone_profile_list_retrieved'
    create_message = 'recommendations.zone_profile_created'
    update_message = 'recommendations.zone_profile_updated'
    destroy_message = 'recommendations.zone_profile_deleted'

    def get_queryset(self):
        qs = CropZoneProfile.objects.filter(is_deleted=False).order_by('crop_name', 'kau_zone')
        kau_zone = self.request.query_params.get('kau_zone')
        if kau_zone:
            qs = qs.filter(kau_zone=kau_zone)
        crop_group = self.request.query_params.get('crop_group')
        if crop_group:
            qs = qs.filter(crop_group__iexact=crop_group)
        return qs

    def perform_create(self, serializer):
        instance = serializer.save()
        if instance.is_active:
            export_and_notify()

    def perform_update(self, serializer):
        was_active = serializer.instance.is_active
        instance = serializer.save()
        if was_active or instance.is_active:
            export_and_notify()

    def perform_destroy(self, instance):
        was_active = instance.is_active
        # Hard delete: (crop_name, kau_zone) is unique, so a soft-deleted row would block re-creating it.
        instance.delete()
        if was_active:
            export_and_notify()

    @extend_schema(tags=['Admin - Crop Zone Profiles'])
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        obj = self.get_object()
        obj.is_active = True
        obj.save(update_fields=['is_active', 'updated_at'])
        export_and_notify()
        return StandardResponse.success(
            data=self.get_serializer(obj).data,
            message=t('recommendations.zone_profile_activated', self.get_language()),
        )

    @extend_schema(tags=['Admin - Crop Zone Profiles'])
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        obj = self.get_object()
        obj.is_active = False
        obj.save(update_fields=['is_active', 'updated_at'])
        export_and_notify()
        return StandardResponse.success(
            data=self.get_serializer(obj).data,
            message=t('recommendations.zone_profile_deactivated', self.get_language()),
        )
