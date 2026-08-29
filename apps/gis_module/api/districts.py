"""
GIS District API — P2-05
Endpoints:
    GET  /api/gis/districts/            — list all district boundaries
    GET  /api/gis/districts/{code}/     — single district detail
"""
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework_gis.serializers import GeoFeatureModelSerializer
from drf_spectacular.utils import extend_schema

from apps.core.views import TranslatedViewSet
from apps.core.utils.pagination import StandardPagination

from apps.database.models import DistrictBoundary
from apps.gis_module.api.mixins import GeoJSONFixMixin


# ---------------------------------------------------------------------------
# Serializer
# ---------------------------------------------------------------------------

class DistrictBoundarySerializer(GeoJSONFixMixin, GeoFeatureModelSerializer):
    """
    Outputs each district as a GeoJSON Feature.
    geo_field is the boundary polygon (the one geometry a
    GeoFeatureModelSerializer can encode as the Feature's "geometry" key).
    centroid is a separate PointField on the model, so it's exposed as a
    plain lat/lng pair inside "properties" instead.
    """
    geo_field_name = 'boundary'
    centroid = serializers.SerializerMethodField()

    class Meta:
        model = DistrictBoundary
        geo_field = 'boundary'
        fields = ['id', 'code', 'centroid']

    def get_centroid(self, obj):
        if not obj.centroid:
            return None
        return {'lat': obj.centroid.y, 'lng': obj.centroid.x}


# ---------------------------------------------------------------------------
# ViewSet — list + retrieve for DistrictBoundary
#
# Same MRO note as zones.py: TranslatedViewSet already provides list/
# retrieve via ModelViewSet — do not add mixins.ListModelMixin/
# RetrieveModelMixin as extra bases.
#
# Also read-only reference data — same open question as zones.py on
# whether urls.py should restrict this to list/retrieve only.
# ---------------------------------------------------------------------------

class DistrictBoundaryViewSet(TranslatedViewSet):
    queryset = DistrictBoundary.objects.all()
    serializer_class = DistrictBoundarySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination
    lookup_field = 'code'

    list_message = 'gis.districts_retrieved'

    @extend_schema(tags=["GIS"])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(tags=["GIS"])
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)