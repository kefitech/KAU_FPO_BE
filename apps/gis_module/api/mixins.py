"""
Shared GIS serializer fix — apps/gis_module/api/mixins.py

In this project's djangorestframework-gis setup, GeoFeatureModelSerializer's
auto-mapped geometry field renders as a WKT string
(e.g. "SRID=4326;MULTIPOLYGON (((...)))") instead of a proper nested
GeoJSON object. A mapping frontend (Leaflet, react-leaflet) needs real
GeoJSON coordinates to render a shape directly — it can't consume WKT
without extra parsing.

GeoJSONFixMixin forces correct output by reading the geometry straight
off the model instance and converting it via GEOSGeometry.geojson
(which Django's GIS layer already provides), rather than relying on
the serializer's own (currently misbehaving) geometry field encoding.

Usage:
    class MySerializer(GeoJSONFixMixin, GeoFeatureModelSerializer):
        geo_field_name = 'boundary'  # the model field holding the geometry
        class Meta:
            model = MyModel
            geo_field = 'boundary'
            fields = [...]
"""
import json


class GeoJSONFixMixin:
    geo_field_name = None

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        if self.geo_field_name:
            geometry = getattr(instance, self.geo_field_name, None)
            if geometry is not None:
                ret['geometry'] = json.loads(geometry.geojson)
        return ret