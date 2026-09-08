"""
GIS Zone API — P2-05
Endpoints:
    GET  /api/gis/zones/                 — list all agro-climatic zones
    GET  /api/gis/zones/{code}/          — single zone detail
    GET  /api/gis/fpo-location/          — FPO's map pin + zone name (FPO auth only)
    POST /api/gis/detect-zone/           — given {lat, lng} -> return which zone it falls in

Admin (staged upload + activate — apps/database/models/gis.py ZoneBoundaryVersion):
    GET  /api/admin/gis/zone-versions/            — list uploaded versions
    POST /api/admin/gis/zone-versions/            — upload + validate a new version (staged, inactive)
    POST /api/admin/gis/zone-versions/{id}/activate/ — apply a staged version to live zones
"""
import json as _json

from django.contrib.gis.geos import Point, GEOSGeometry, MultiPolygon, Polygon
from rest_framework import filters, serializers, status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework_gis.serializers import GeoFeatureModelSerializer
from drf_spectacular.utils import extend_schema, OpenApiExample

from apps.core.views import TranslatedViewSet
from apps.core.utils.responses import StandardResponse
from apps.core.utils.pagination import StandardPagination
from apps.core.services.translation import t
from apps.core.permissions.rbac import IsAdmin
from apps.core.models.generic import AuditLog
from apps.core.services.audit import AuditService

from apps.database.models import AgroClimaticZone, FPO, ZoneBoundaryVersion


# ---------------------------------------------------------------------------
# Serializer
# ---------------------------------------------------------------------------

from apps.gis_module.api.mixins import GeoJSONFixMixin


class AgroClimaticZoneSerializer(GeoJSONFixMixin, GeoFeatureModelSerializer):
    """
    Outputs each zone as a GeoJSON Feature:
    { "type": "Feature", "geometry": {...MultiPolygon...}, "properties": {...} }
    """
    geo_field_name = 'boundary'

    class Meta:
        model = AgroClimaticZone
        geo_field = 'boundary'
        fields = ['id', 'code', 'name_en', 'name_ml', 'suitable_crops', 'soil_type']


# ---------------------------------------------------------------------------
# Helper — mirrors _get_fpo_or_404 convention used in apps/fpo/api/documents.py
# ---------------------------------------------------------------------------

def _get_fpo_or_404(user, lang):
    try:
        return FPO.objects.get(primary_user=user), None
    except FPO.DoesNotExist:
        return None, StandardResponse.error(
            t('gis.fpo_not_found', lang),
            status_code=status.HTTP_404_NOT_FOUND,
        )


# ---------------------------------------------------------------------------
# ViewSet — list + retrieve for AgroClimaticZone
#
# NOTE: TranslatedViewSet already extends viewsets.ModelViewSet, which
# already provides ListModelMixin/RetrieveModelMixin (and Create/Update/
# Destroy) — do NOT list mixins.ListModelMixin/RetrieveModelMixin as
# separate bases alongside it, that causes a Python MRO conflict
# (confirmed via TypeError when tested). Inherit from TranslatedViewSet
# alone and override list()/retrieve() only for the @extend_schema tag.
#
# Because TranslatedViewSet is a full ModelViewSet, registering this with
# a router will also expose create/update/destroy routes unless urls.py
# restricts it — confirm with Athul whether this should be wired as a
# read-only route (e.g. explicit path()s for list/retrieve only) since
# zones are a reference dataset seeded from real taluk boundary data
# (see scripts/seed_gis_zones.py), not something clients should be able
# to POST/PUT/DELETE directly — admin updates go through the staged
# ZoneBoundaryVersion upload/activate flow below instead.
# ---------------------------------------------------------------------------

class AgroClimaticZoneViewSet(TranslatedViewSet):
    queryset = AgroClimaticZone.objects.all()
    serializer_class = AgroClimaticZoneSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination
    lookup_field = 'code'

    list_message = 'gis.zones_retrieved'

    @extend_schema(tags=["GIS"])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(tags=["GIS"])
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)


# ---------------------------------------------------------------------------
# FPO's own location + detected zone
# ---------------------------------------------------------------------------

class FPOLocationView(APIView):
    """
    GET /api/gis/fpo-location/
    Returns the authenticated FPO's saved location + the zone it falls in.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["GIS"])
    def get(self, request, *args, **kwargs):
        lang = request.language

        fpo, err = _get_fpo_or_404(request.user, lang)
        if err:
            return err

        if not fpo.location:
            return StandardResponse.error(
                t('gis.location_not_set', lang),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        zone = AgroClimaticZone.objects.filter(
            boundary__contains=fpo.location
        ).first()

        data = {
            'location': {
                'lat': fpo.location.y,
                'lng': fpo.location.x,
            },
            'zone_code': zone.code if zone else None,
            'zone_name_en': zone.name_en if zone else None,
            'zone_name_ml': zone.name_ml if zone else None,
            'soil_type': zone.soil_type if zone else None,
        }
        return StandardResponse.success(
            data=data,
            message=t('gis.zone_detected', lang),
        )


# ---------------------------------------------------------------------------
# Detect zone from arbitrary lat/lng (not tied to an FPO's saved location)
# ---------------------------------------------------------------------------

class DetectZoneView(APIView):
    """
    POST /api/gis/detect-zone/
    Body: {"lat": 9.9312, "lng": 76.2673}
    Returns which AgroClimaticZone the point falls in, if any.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["GIS"],
        examples=[
            OpenApiExample(
                'Example request',
                value={'lat': 9.9312, 'lng': 76.2673},
                request_only=True,
            )
        ],
    )
    def post(self, request, *args, **kwargs):
        lang = request.language

        lat = request.data.get('lat')
        lng = request.data.get('lng')

        if lat is None or lng is None:
            return StandardResponse.error(
                t('gis.lat_lng_required', lang),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            lat = float(lat)
            lng = float(lng)
        except (TypeError, ValueError):
            return StandardResponse.error(
                t('gis.invalid_coordinates', lang),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        point = Point(lng, lat, srid=4326)  # Point takes (x=lng, y=lat)
        zone = AgroClimaticZone.objects.filter(boundary__contains=point).first()

        if not zone:
            return StandardResponse.error(
                t('gis.zone_not_found', lang),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        data = {
            'zone_code': zone.code,
            'zone_name_en': zone.name_en,
            'zone_name_ml': zone.name_ml,
            'suitable_crops': zone.suitable_crops,
            'soil_type': zone.soil_type,
        }
        return StandardResponse.success(
            data=data,
            message=t('gis.zone_detected', lang),
        )


# ---------------------------------------------------------------------------
# Admin — staged zone boundary upload + activate
#
# Upload validates and stores a GeoJSON FeatureCollection as an
# INACTIVE ZoneBoundaryVersion row — it does NOT touch live
# AgroClimaticZone data. Only activate() applies it. Same proven
# pattern as MLModelVersion's upload/activate flow
# (apps/recommendations/api/recommendations.py) — activating one
# version automatically deactivates any other (see
# ZoneBoundaryVersion.save() in apps/database/models/gis.py).
# ---------------------------------------------------------------------------

MAX_ZONE_FILE_SIZE = 5 * 1024 * 1024  # 5MB — generous for simplified zone
                                        # geometry, but prevents an accidental
                                        # huge upload (the original un-
                                        # simplified data was 1.7MB+ for
                                        # reference — see the bug we found
                                        # and fixed tonight in the live seed)


def _validate_zone_geojson(data: dict) -> list[str]:
    """
    Validates a FeatureCollection's structure and each feature's code +
    geometry, WITHOUT applying anything. Returns a list of error
    strings — empty list means valid. Shared between upload (validate
    only) and activate (validate again defensively, then apply).
    """
    if data.get('type') != 'FeatureCollection' or 'features' not in data:
        return ["File is not a valid GeoJSON FeatureCollection."]

    valid_codes = set(AgroClimaticZone.objects.values_list('code', flat=True))
    errors = []
    for feature in data['features']:
        code = (feature.get('properties') or {}).get('code')
        if code not in valid_codes:
            errors.append(f"Unknown or missing zone code: {code!r}")
            continue
        try:
            geometry = GEOSGeometry(_json.dumps(feature['geometry']), srid=4326)
            if not isinstance(geometry, (Polygon, MultiPolygon)):
                errors.append(f"Geometry for {code} is not a Polygon/MultiPolygon.")
        except Exception as e:
            errors.append(f"Invalid geometry for {code}: {e}")
    return errors


class ZoneBoundaryVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ZoneBoundaryVersion
        fields = ['id', 'label', 'is_active', 'created_at', 'updated_at']


class ZoneBoundaryVersionListView(APIView):
    """
    GET  /api/admin/gis/zone-versions/  — list uploaded versions (paginated)
    POST /api/admin/gis/zone-versions/  — upload + VALIDATE a new version,
                                           staged as inactive. Does NOT
                                           touch live AgroClimaticZone data.
    """
    permission_classes = [IsAdmin]
    parser_classes = [MultiPartParser, FormParser]
    pagination_class = StandardPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['label']
    ordering_fields = ['label', 'created_at', 'updated_at']

    @extend_schema(tags=["Admin - GIS"])
    def get(self, request, *args, **kwargs):
        versions = ZoneBoundaryVersion.objects.filter(is_deleted=False)
        for backend in self.filter_backends:
            versions = backend().filter_queryset(request, versions, self)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(versions, request, view=self)
        serializer = ZoneBoundaryVersionSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(tags=["Admin - GIS"])
    def post(self, request, *args, **kwargs):
        lang = request.language

        file = request.FILES.get('geojson_file')
        if not file:
            return StandardResponse.error(
                t('gis.zone_file_required', lang),
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        if file.size > MAX_ZONE_FILE_SIZE:
            return StandardResponse.error(
                t('gis.zone_file_too_large', lang),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            data = _json.loads(file.read())
        except (_json.JSONDecodeError, UnicodeDecodeError):
            return StandardResponse.error(
                t('gis.zone_file_invalid_json', lang),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        errors = _validate_zone_geojson(data)
        if errors:
            return StandardResponse.error(
                t('gis.zone_upload_failed', lang),
                errors=errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        version = ZoneBoundaryVersion.objects.create(
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

        serializer = ZoneBoundaryVersionSerializer(version)
        return StandardResponse.success(
            data=serializer.data,
            message=t('gis.zone_version_uploaded', lang),
            status_code=status.HTTP_201_CREATED,
        )


class ZoneBoundaryVersionActivateView(APIView):
    """
    POST /api/admin/gis/zone-versions/{id}/activate/
    Applies a staged version's geometry to the live AgroClimaticZone
    rows, and marks this version active (deactivating any other).
    """
    permission_classes = [IsAdmin]

    @extend_schema(tags=["Admin - GIS"])
    def post(self, request, pk, *args, **kwargs):
        lang = request.language

        try:
            version = ZoneBoundaryVersion.objects.get(pk=pk, is_deleted=False)
        except ZoneBoundaryVersion.DoesNotExist:
            return StandardResponse.error(
                t('gis.zone_version_not_found', lang),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        errors = _validate_zone_geojson(version.geojson_data)
        if errors:
            return StandardResponse.error(
                t('gis.zone_upload_failed', lang),
                errors=errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        updated = []
        for feature in version.geojson_data['features']:
            code = feature['properties']['code']
            geometry = GEOSGeometry(_json.dumps(feature['geometry']), srid=4326)
            if isinstance(geometry, Polygon):
                geometry = MultiPolygon(geometry, srid=4326)
            AgroClimaticZone.objects.filter(code=code).update(boundary=geometry)
            updated.append(code)

        version.is_active = True
        version.save(update_fields=['is_active', 'updated_at'])

        AuditService.log(
            user=request.user,
            action=AuditLog.Action.UPDATE,
            instance=version,
            request=request,
            changes={'activated_version': version.label, 'updated_zones': updated},
        )

        return StandardResponse.success(
            data={'updated_zones': updated},
            message=t('gis.zone_version_activated', lang),
        )

    # ── Add this class to the end of apps/gis_module/api/zones.py ──
# ── Add this class to the end of apps/gis_module/api/zones.py ──

class ZoneBoundaryVersionDetailView(APIView):
    """
    GET    /api/admin/gis/zone-versions/{id}/  — full record including
                                                  geojson_data, used for
                                                  the admin's "preview
                                                  this version on the
                                                  map" feature — does
                                                  NOT affect live zones.
    DELETE /api/admin/gis/zone-versions/{id}/  — soft-deletes a staged/
                                                  inactive version. Blocks
                                                  deleting the currently
                                                  ACTIVE version.
    """
    permission_classes = [IsAdmin]

    @extend_schema(tags=["Admin - GIS"])
    def get(self, request, pk, *args, **kwargs):
        lang = request.language
        try:
            version = ZoneBoundaryVersion.objects.get(pk=pk, is_deleted=False)
        except ZoneBoundaryVersion.DoesNotExist:
            return StandardResponse.error(
                t('gis.zone_version_not_found', lang),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        return StandardResponse.success(
            data={
                'id': version.id,
                'label': version.label,
                'is_active': version.is_active,
                'geojson_data': version.geojson_data,
            },
            message=t('gis.zone_version_retrieved', lang),
        )

    @extend_schema(tags=["Admin - GIS"])
    def delete(self, request, pk, *args, **kwargs):
        lang = request.language

        try:
            version = ZoneBoundaryVersion.objects.get(pk=pk, is_deleted=False)
        except ZoneBoundaryVersion.DoesNotExist:
            return StandardResponse.error(
                t('gis.zone_version_not_found', lang),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        if version.is_active:
            return StandardResponse.error(
                t('gis.zone_version_cannot_delete_active', lang),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        version.soft_delete(user=request.user)
        AuditService.log_soft_delete(user=request.user, instance=version, request=request)
        return StandardResponse.success(
            data=None,
            message=t('gis.zone_version_deleted', lang),
        )