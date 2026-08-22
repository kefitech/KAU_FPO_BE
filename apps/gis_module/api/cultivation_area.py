"""
FPO Cultivation Area API — self-service farm boundary drawing
Endpoints:
    GET    /api/gis/cultivation-area/me/  — fetch own drawn area
    POST   /api/gis/cultivation-area/me/  — create or replace own area
    DELETE /api/gis/cultivation-area/me/  — remove own area

Distinct from zones.py/districts.py: those are shared admin-managed
reference data (read-only to regular users). This is each FPO's own
private data — any authenticated FPO manager can create/edit/delete
their OWN cultivation area, but never another FPO's.
"""
import json

from django.contrib.gis.geos import GEOSGeometry, MultiPolygon, Polygon
from rest_framework import serializers, status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework_gis.serializers import GeoFeatureModelSerializer
from drf_spectacular.utils import extend_schema

from apps.core.utils.responses import StandardResponse
from apps.core.services.translation import t

from apps.database.models import FPOCultivationArea
from apps.gis_module.api.zones import _get_fpo_or_404
from apps.gis_module.api.mixins import GeoJSONFixMixin
from apps.gis_module.services import find_zone_for_point


# ---------------------------------------------------------------------------
# Serializer
# ---------------------------------------------------------------------------

class FPOCultivationAreaSerializer(GeoJSONFixMixin, GeoFeatureModelSerializer):
    """
    Reads/writes as a GeoJSON Feature. area_polygon is the writable
    geometry; area_hectares is computed server-side (see
    _compute_hectares below) and read-only — clients never set it
    directly, even if they include it in the request body.

    zone_code/zone_name_en/zone_name_ml/soil_type are derived from
    WHERE THIS PLOT ACTUALLY IS — a live spatial lookup (find_zone_for_point,
    shared with weather.py and recommendations) against the cultivation
    area's own centroid — NOT from the FPO's separate FPOZoneAssignment
    (which reflects the FPO's registered office/contact address via
    FPO.latitude/longitude). These can legitimately differ: an FPO's
    registered address and their farmland don't have to be in the same
    zone, which is the whole reason this is a separate lookup rather
    than reusing fpo.zone_assignment.
    """
    geo_field_name = 'area_polygon'
    zone_code = serializers.SerializerMethodField()
    zone_name_en = serializers.SerializerMethodField()
    zone_name_ml = serializers.SerializerMethodField()
    soil_type = serializers.SerializerMethodField()

    class Meta:
        model = FPOCultivationArea
        geo_field = 'area_polygon'
        fields = [
            'id', 'area_hectares',
            'zone_code', 'zone_name_en', 'zone_name_ml', 'soil_type',
        ]
        read_only_fields = [
            'area_hectares',
            'zone_code', 'zone_name_en', 'zone_name_ml', 'soil_type',
        ]

    def _get_zone(self, obj):
        if not obj.area_polygon:
            return None
        centroid = obj.area_polygon.centroid
        return find_zone_for_point(centroid.y, centroid.x)

    def get_zone_code(self, obj):
        zone = self._get_zone(obj)
        return zone.code if zone else None

    def get_zone_name_en(self, obj):
        zone = self._get_zone(obj)
        return zone.name_en if zone else None

    def get_zone_name_ml(self, obj):
        zone = self._get_zone(obj)
        return zone.name_ml if zone else None

    def get_soil_type(self, obj):
        zone = self._get_zone(obj)
        return zone.soil_type if zone else None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_multipolygon(geometry):
    """
    Normalizes incoming geometry to a MultiPolygon GEOSGeometry object.

    In this project's djangorestframework-gis version, validated_data
    for the geo_field can come back as a raw dict (parsed GeoJSON)
    rather than an already-constructed GEOSGeometry — convert
    explicitly rather than assuming.

    Also accepts a plain Polygon (a real map-drawing tool naturally
    produces a single Polygon for one farm boundary, not a
    MultiPolygon) and wraps it, since the model field requires
    MultiPolygonField specifically.
    """
    if isinstance(geometry, dict):
        geometry = GEOSGeometry(json.dumps(geometry))

    if isinstance(geometry, Polygon):
        geometry = MultiPolygon(geometry)

    if not isinstance(geometry, MultiPolygon):
        raise ValueError(
            f"Expected Polygon or MultiPolygon geometry, got {type(geometry).__name__}"
        )

    if geometry.srid is None:
        geometry.srid = 4326

    return geometry


def _compute_hectares(multipolygon):
    """
    Transforms the geometry to UTM Zone 43N (EPSG:32643 — covers Kerala)
    to get an accurate area in square meters, then converts to hectares.
    The stored srid=4326 (plain lat/lng degrees) can't give accurate
    area directly — degrees aren't a consistent real-world distance.
    """
    projected = multipolygon.transform(32643, clone=True)
    square_meters = projected.area
    return round(square_meters / 10000, 2)  # 1 hectare = 10,000 sq meters


# ---------------------------------------------------------------------------
# View
# ---------------------------------------------------------------------------

class CultivationAreaView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["GIS"])
    def get(self, request, *args, **kwargs):
        lang = request.language

        fpo, err = _get_fpo_or_404(request.user, lang)
        if err:
            return err

        area = getattr(fpo, 'cultivation_area', None)
        if not area:
            return StandardResponse.error(
                t('gis.cultivation_area_not_found', lang),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        serializer = FPOCultivationAreaSerializer(area)
        return StandardResponse.success(
            data=serializer.data,
            message=t('gis.cultivation_area_retrieved', lang),
        )

    @extend_schema(tags=["GIS"])
    def post(self, request, *args, **kwargs):
        lang = request.language

        fpo, err = _get_fpo_or_404(request.user, lang)
        if err:
            return err

        serializer = FPOCultivationAreaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            area_polygon = _to_multipolygon(serializer.validated_data['area_polygon'])
        except ValueError as exc:
            return StandardResponse.error(
                str(exc),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        area_hectares = _compute_hectares(area_polygon)

        area, _created = FPOCultivationArea.objects.update_or_create(
            fpo=fpo,
            defaults={
                'area_polygon': area_polygon,
                'area_hectares': area_hectares,
            },
        )

        out_serializer = FPOCultivationAreaSerializer(area)
        return StandardResponse.success(
            data=out_serializer.data,
            message=t('gis.cultivation_area_saved', lang),
            status_code=status.HTTP_201_CREATED if _created else status.HTTP_200_OK,
        )

    @extend_schema(tags=["GIS"])
    def delete(self, request, *args, **kwargs):
        lang = request.language

        fpo, err = _get_fpo_or_404(request.user, lang)
        if err:
            return err

        deleted_count, _ = FPOCultivationArea.objects.filter(fpo=fpo).delete()
        if not deleted_count:
            return StandardResponse.error(
                t('gis.cultivation_area_not_found', lang),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        return StandardResponse.success(
            message=t('gis.cultivation_area_deleted', lang),
        )