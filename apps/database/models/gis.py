"""
GIS Integration Models — P2-05

Requires PostGIS extension: CREATE EXTENSION IF NOT EXISTS postgis;
Requires GeoDjango: django.contrib.gis in INSTALLED_APPS
"""
from django.contrib.gis.db import models as gis_models
from django.db import models
from apps.core.models.base import BaseModel


class AgroClimaticZone(BaseModel):
    code = models.CharField(
        max_length=30, unique=True,
        help_text='e.g. central_kerala, high_ranges, coastal_zone'
    )
    name_en = models.CharField(max_length=200)
    name_ml = models.CharField(max_length=200)
    boundary = gis_models.MultiPolygonField(
        srid=4326,
        help_text='GeoJSON polygon — from Bhuvan WMS or KAU-provided file'
    )
    suitable_crops = models.JSONField(
        default=list,
        help_text='List of MasterLookup commodity codes e.g. ["rice","banana","coconut"]'
    )

    class Meta:
        verbose_name = 'Agro Climatic Zone'
        verbose_name_plural = 'Agro Climatic Zones'

    def __str__(self):
        return f"{self.name_en} ({self.code})"


class DistrictBoundary(BaseModel):
    code = models.CharField(
        max_length=10, unique=True,
        help_text='Matches District enum in constants.py e.g. TRS, EKM'
    )
    boundary = gis_models.MultiPolygonField(srid=4326)
    centroid = gis_models.PointField(srid=4326)

    class Meta:
        verbose_name = 'District Boundary'
        verbose_name_plural = 'District Boundaries'

    def __str__(self):
        return self.code
