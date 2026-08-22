"""
GIS Module URLs — P2-05

NOTE: AgroClimaticZoneViewSet and DistrictBoundaryViewSet inherit from
TranslatedViewSet, which is a full ModelViewSet (supports create/update/
destroy). Using a DRF DefaultRouter here would auto-expose POST/PUT/PATCH/
DELETE on these routes, which isn't wanted — both are read-only reference
datasets (zones/districts are seeded from KAU-provided GeoJSON, not
created via the API). So routes are wired explicitly below, restricted to
GET only. Confirm this approach with Athul/the team before merging —
alternative would be a read-only router or overriding get_queryset /
http_method_names on the ViewSets themselves.
"""
from django.urls import path

from apps.gis_module.api.zones import (
    AgroClimaticZoneViewSet,
    FPOLocationView,
    DetectZoneView,
)
from apps.gis_module.api.districts import DistrictBoundaryViewSet
from apps.gis_module.api.cultivation_area import CultivationAreaView
from apps.gis_module.api.weather import FPOWeatherView

zone_list = AgroClimaticZoneViewSet.as_view({'get': 'list'})
zone_detail = AgroClimaticZoneViewSet.as_view({'get': 'retrieve'})

district_list = DistrictBoundaryViewSet.as_view({'get': 'list'})
district_detail = DistrictBoundaryViewSet.as_view({'get': 'retrieve'})

weather_view = FPOWeatherView.as_view()

urlpatterns = [
    path('zones/', zone_list, name='zone-list'),
    path('zones/<str:code>/', zone_detail, name='zone-detail'),

    path('districts/', district_list, name='district-list'),
    path('districts/<str:code>/', district_detail, name='district-detail'),

    path('fpo-location/', FPOLocationView.as_view(), name='fpo-location'),
    path('detect-zone/', DetectZoneView.as_view(), name='detect-zone'),

    path('cultivation-area/me/', CultivationAreaView.as_view(), name='cultivation-area'),

    # Same FPOWeatherView handles both — GET here routes to .get() (cached),
    # POST at the /refresh/ path routes to .post() (fetch fresh). Two URL
    # patterns sharing one view class, dispatched by HTTP method as usual.
    path('weather/me/', weather_view, name='weather-get'),
    path('weather/me/refresh/', weather_view, name='weather-refresh'),
]