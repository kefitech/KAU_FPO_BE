"""
GIS Zone API — P2-05
Endpoints:
    GET  /api/gis/zones/                 — list all agro-climatic zones
    GET  /api/gis/zones/{code}/          — single zone detail
    GET  /api/gis/fpo-location/          — FPO's map pin + zone name (FPO auth only)
    POST /api/gis/detect-zone/           — given {lat, lng} -> return which zone it falls in
"""
from django.contrib.gis.geos import Point
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework_gis.serializers import GeoFeatureModelSerializer
from drf_spectacular.utils import extend_schema, OpenApiExample

from apps.core.views import TranslatedViewSet
from apps.core.utils.responses import StandardResponse
from apps.core.utils.pagination import StandardPagination
from apps.core.services.translation import t

from apps.database.models import AgroClimaticZone, FPO


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
        fields = ['id', 'code', 'name_en', 'name_ml', 'suitable_crops']


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
# zones are a reference dataset seeded from KAU's GeoJSON, not something
# clients should be able to POST/PUT/DELETE.
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
        }
        return StandardResponse.success(
            data=data,
            message=t('gis.zone_detected', lang),
        )