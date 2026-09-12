"""
Soil Region API — location-wise soil data, independent of AgroClimaticZone
boundaries (see apps/database/models/gis.py's SoilRegion/SoilRegionVersion
and apps/gis_module/services.py's find_soil_region_for_point()).

Endpoints:
    GET  /api/gis/soil-regions/          — list all soil regions
    GET  /api/gis/soil-regions/{code}/   — single soil region detail

Admin (staged upload + activate — same pattern as ZoneBoundaryVersion in
apps/gis_module/api/zones.py):
    GET  /api/admin/gis/soil-region-versions/               — list uploaded versions
    POST /api/admin/gis/soil-region-versions/               — upload + validate a new version (staged, inactive)
    POST /api/admin/gis/soil-region-versions/{id}/activate/ — apply a staged version to live soil regions
    GET  /api/admin/gis/soil-region-versions/{id}/          — full record, used for map preview
    DELETE /api/admin/gis/soil-region-versions/{id}/        — soft-delete a staged/inactive version

Unlike zones (a fixed set of 5 known codes, where activation only updates
boundary on existing rows), a soil-region upload defines the WHOLE region
set — activation fully syncs live SoilRegion rows to match the uploaded
FeatureCollection (upsert what's present, delete what's no longer there).
"""
import json as _json

from django.contrib.gis.geos import GEOSGeometry, MultiPolygon, Polygon
from rest_framework import filters, serializers, status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework_gis.serializers import GeoFeatureModelSerializer
from drf_spectacular.utils import extend_schema

from apps.core.views import TranslatedViewSet
from apps.core.utils.responses import StandardResponse
from apps.core.utils.pagination import StandardPagination
from apps.core.services.translation import t
from apps.core.permissions.rbac import IsAdmin
from apps.core.models.generic import AuditLog
from apps.core.services.audit import AuditService

from apps.database.models import SoilRegion, SoilRegionVersion
from apps.gis_module.api.mixins import GeoJSONFixMixin

MAX_SOIL_REGION_FILE_SIZE = 5 * 1024 * 1024  # 5MB — same cap as zone uploads


# ---------------------------------------------------------------------------
# Serializer
# ---------------------------------------------------------------------------

class SoilRegionSerializer(GeoJSONFixMixin, GeoFeatureModelSerializer):
    """
    Outputs each soil region as a GeoJSON Feature:
    { "type": "Feature", "geometry": {...MultiPolygon...}, "properties": {...} }
    """
    geo_field_name = 'boundary'

    class Meta:
        model = SoilRegion
        geo_field = 'boundary'
        fields = ['id', 'code', 'name_en', 'name_ml', 'soil_type']


# ---------------------------------------------------------------------------
# ViewSet — list + retrieve for SoilRegion (read-only reference dataset,
# same reasoning as AgroClimaticZoneViewSet — admin updates go through the
# staged SoilRegionVersion upload/activate flow below instead)
# ---------------------------------------------------------------------------

class SoilRegionViewSet(TranslatedViewSet):
    queryset = SoilRegion.objects.all()
    serializer_class = SoilRegionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination
    lookup_field = 'code'

    list_message = 'gis.soil_regions_retrieved'

    @extend_schema(tags=["GIS"])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(tags=["GIS"])
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)


# ---------------------------------------------------------------------------
# Admin — staged upload + activate for SoilRegionVersion
# ---------------------------------------------------------------------------

def _validate_soil_geojson(data: dict) -> list[str]:
    """
    Validates a FeatureCollection's structure and each feature's code,
    soil_type, and geometry, WITHOUT applying anything. Returns a list of
    error strings — empty list means valid. Shared between upload
    (validate only) and activate (validate again defensively, then apply).

    Unlike _validate_zone_geojson (apps/gis_module/api/zones.py), there is
    NO fixed pre-existing set of valid codes to check against — a soil
    region upload defines its own complete code set. Only checks each
    feature's code is present and unique within THIS file.
    """
    if data.get('type') != 'FeatureCollection' or 'features' not in data:
        return ["File is not a valid GeoJSON FeatureCollection."]

    errors = []
    seen_codes = set()
    for feature in data['features']:
        props = feature.get('properties') or {}
        code = props.get('code')
        soil_type = props.get('soil_type')
        if not code:
            errors.append("Feature is missing a 'code' property.")
            continue
        if code in seen_codes:
            errors.append(f"Duplicate soil region code in this file: {code!r}")
            continue
        seen_codes.add(code)
        if not soil_type:
            errors.append(f"Feature {code!r} is missing a 'soil_type' property.")
        try:
            geometry = GEOSGeometry(_json.dumps(feature['geometry']), srid=4326)
            if not isinstance(geometry, (Polygon, MultiPolygon)):
                errors.append(f"Geometry for {code} is not a Polygon/MultiPolygon.")
        except Exception as e:
            errors.append(f"Invalid geometry for {code}: {e}")
    return errors


class SoilRegionVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SoilRegionVersion
        fields = ['id', 'label', 'is_active', 'created_at', 'updated_at']


class SoilRegionVersionListView(APIView):
    """
    GET  /api/admin/gis/soil-region-versions/  — list uploaded versions (paginated)
    POST /api/admin/gis/soil-region-versions/  — upload + VALIDATE a new version,
                                                  staged as inactive. Does NOT
                                                  touch live SoilRegion data.
    """
    permission_classes = [IsAdmin]
    parser_classes = [MultiPartParser, FormParser]
    pagination_class = StandardPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['label']
    ordering_fields = ['label', 'created_at', 'updated_at']

    @extend_schema(tags=["Admin - GIS"])
    def get(self, request, *args, **kwargs):
        versions = SoilRegionVersion.objects.filter(is_deleted=False)
        for backend in self.filter_backends:
            versions = backend().filter_queryset(request, versions, self)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(versions, request, view=self)
        serializer = SoilRegionVersionSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(tags=["Admin - GIS"])
    def post(self, request, *args, **kwargs):
        lang = request.language

        file = request.FILES.get('geojson_file')
        if not file:
            return StandardResponse.error(
                t('gis.soil_region_file_required', lang),
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        if file.size > MAX_SOIL_REGION_FILE_SIZE:
            return StandardResponse.error(
                t('gis.soil_region_file_too_large', lang),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            data = _json.loads(file.read())
        except (_json.JSONDecodeError, UnicodeDecodeError):
            return StandardResponse.error(
                t('gis.soil_region_file_invalid_json', lang),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        errors = _validate_soil_geojson(data)
        if errors:
            return StandardResponse.error(
                t('gis.soil_region_upload_failed', lang),
                errors=errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        version = SoilRegionVersion.objects.create(
            label=file.name,
            geojson_data=data,
            uploaded_by=request.user,
            is_active=False,
        )

        AuditService.log(
            user=request.user,
            action=AuditLog.Action.CREATE,
            instance=version,
            request=request,
            changes={'label': version.label, 'feature_count': len(data.get('features') or [])},
        )

        serializer = SoilRegionVersionSerializer(version)
        return StandardResponse.success(
            data=serializer.data,
            message=t('gis.soil_region_version_uploaded', lang),
            status_code=status.HTTP_201_CREATED,
        )


class SoilRegionVersionActivateView(APIView):
    """
    POST /api/admin/gis/soil-region-versions/{id}/activate/
    Applies a staged version's geometry to the live SoilRegion rows, and
    marks this version active (deactivating any other).

    Full sync, not a partial update: for each feature, upsert a SoilRegion
    by code; any existing SoilRegion whose code isn't present in this
    version's features is removed. Soil regions aren't a fixed pre-known
    set like zones — an upload defines the entire live set.
    """
    permission_classes = [IsAdmin]

    @extend_schema(tags=["Admin - GIS"])
    def post(self, request, pk, *args, **kwargs):
        lang = request.language

        try:
            version = SoilRegionVersion.objects.get(pk=pk, is_deleted=False)
        except SoilRegionVersion.DoesNotExist:
            return StandardResponse.error(
                t('gis.soil_region_version_not_found', lang),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        errors = _validate_soil_geojson(version.geojson_data)
        if errors:
            return StandardResponse.error(
                t('gis.soil_region_upload_failed', lang),
                errors=errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        uploaded_codes = []
        for feature in version.geojson_data['features']:
            props = feature['properties']
            code = props['code']
            geometry = GEOSGeometry(_json.dumps(feature['geometry']), srid=4326)
            if isinstance(geometry, Polygon):
                geometry = MultiPolygon(geometry, srid=4326)
            SoilRegion.objects.update_or_create(
                code=code,
                defaults={
                    'name_en': props.get('name_en') or code,
                    'name_ml': props.get('name_ml') or code,
                    'boundary': geometry,
                    'soil_type': props['soil_type'],
                },
            )
            uploaded_codes.append(code)

        removed = list(
            SoilRegion.objects.exclude(code__in=uploaded_codes).values_list('code', flat=True)
        )
        SoilRegion.objects.exclude(code__in=uploaded_codes).delete()

        version.is_active = True
        version.save(update_fields=['is_active', 'updated_at'])

        AuditService.log(
            user=request.user,
            action=AuditLog.Action.UPDATE,
            instance=version,
            request=request,
            changes={'activated_version': version.label, 'upserted_regions': uploaded_codes, 'removed_regions': removed},
        )

        return StandardResponse.success(
            data={'upserted_regions': uploaded_codes, 'removed_regions': removed},
            message=t('gis.soil_region_version_activated', lang),
        )


class SoilRegionVersionDetailView(APIView):
    """
    GET    /api/admin/gis/soil-region-versions/{id}/  — full record including
                                                          geojson_data, used for
                                                          the admin's "preview
                                                          this version on the
                                                          map" feature — does
                                                          NOT affect live regions.
    DELETE /api/admin/gis/soil-region-versions/{id}/  — soft-deletes a staged/
                                                          inactive version. Blocks
                                                          deleting the currently
                                                          ACTIVE version.
    """
    permission_classes = [IsAdmin]

    @extend_schema(tags=["Admin - GIS"])
    def get(self, request, pk, *args, **kwargs):
        lang = request.language
        try:
            version = SoilRegionVersion.objects.get(pk=pk, is_deleted=False)
        except SoilRegionVersion.DoesNotExist:
            return StandardResponse.error(
                t('gis.soil_region_version_not_found', lang),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        return StandardResponse.success(
            data={
                'id': version.id,
                'label': version.label,
                'is_active': version.is_active,
                'geojson_data': version.geojson_data,
            },
            message=t('gis.soil_region_version_retrieved', lang),
        )

    @extend_schema(tags=["Admin - GIS"])
    def delete(self, request, pk, *args, **kwargs):
        lang = request.language

        try:
            version = SoilRegionVersion.objects.get(pk=pk, is_deleted=False)
        except SoilRegionVersion.DoesNotExist:
            return StandardResponse.error(
                t('gis.soil_region_version_not_found', lang),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        if version.is_active:
            return StandardResponse.error(
                t('gis.soil_region_version_cannot_delete_active', lang),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        version.soft_delete(user=request.user)
        AuditService.log_soft_delete(user=request.user, instance=version, request=request)
        return StandardResponse.success(
            data=None,
            message=t('gis.soil_region_version_deleted', lang),
        )
