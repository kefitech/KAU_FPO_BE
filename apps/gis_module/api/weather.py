"""
FPO Weather API — apps/gis_module/api/weather.py
Endpoints:
    GET  /api/gis/weather/me/          — cached weather snapshot (from DB)
    POST /api/gis/weather/me/refresh/  — fetch fresh, store, return it

Location resolution order:
    1. FPO's cultivation area centroid (if drawn)
    2. FPO's own latitude/longitude (fallback)
    3. 404 if neither exists

NOTE: get_weather_for_point() is currently a simulated seasonal mock,
not a real weather API — see apps/gis_module/services.py docstring.
"""
from rest_framework import serializers, status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema

from apps.core.utils.responses import StandardResponse
from apps.core.services.translation import t

from apps.database.models import FPOWeatherSnapshot
from apps.gis_module.api.zones import _get_fpo_or_404
from apps.gis_module.services import get_weather_for_point, resolve_fpo_location


# ---------------------------------------------------------------------------
# Serializer
# ---------------------------------------------------------------------------

class FPOWeatherSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = FPOWeatherSnapshot
        fields = [
            'temperature_c', 'humidity_percent', 'rainfall_mm',
            'season', 'description', 'is_simulated', 'fetched_at',
        ]


# ---------------------------------------------------------------------------
# View
# ---------------------------------------------------------------------------

class FPOWeatherView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["GIS"])
    def get(self, request, *args, **kwargs):
        """GET /api/gis/weather/me/ — cached snapshot, does not fetch fresh."""
        lang = request.language

        fpo, err = _get_fpo_or_404(request.user, lang)
        if err:
            return err

        snapshot = getattr(fpo, 'weather_snapshot', None)
        if not snapshot:
            return StandardResponse.error(
                t('gis.weather_not_found', lang),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        serializer = FPOWeatherSnapshotSerializer(snapshot)
        return StandardResponse.success(
            data=serializer.data,
            message=t('gis.weather_retrieved', lang),
        )

    @extend_schema(tags=["GIS"])
    def post(self, request, *args, **kwargs):
        """POST /api/gis/weather/me/refresh/ — fetch fresh and store it."""
        lang = request.language

        fpo, err = _get_fpo_or_404(request.user, lang)
        if err:
            return err

        lat, lng = resolve_fpo_location(fpo)
        if lat is None or lng is None:
            return StandardResponse.error(
                t('gis.location_not_set', lang),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        result = get_weather_for_point(lat, lng)

        snapshot, _created = FPOWeatherSnapshot.objects.update_or_create(
            fpo=fpo,
            defaults={
                'temperature_c': result['temperature_c'],
                'humidity_percent': result['humidity_percent'],
                'rainfall_mm': result['rainfall_mm'],
                'season': result['season'],
                'description': result['description'],
                'is_simulated': result['is_simulated'],
            },
        )

        serializer = FPOWeatherSnapshotSerializer(snapshot)
        return StandardResponse.success(
            data=serializer.data,
            message=t('gis.weather_refreshed', lang),
        )