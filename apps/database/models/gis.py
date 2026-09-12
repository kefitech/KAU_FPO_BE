"""
GIS Integration Models — P2-05
Requires PostGIS extension: CREATE EXTENSION IF NOT EXISTS postgis;
Requires GeoDjango: django.contrib.gis in INSTALLED_APPS
"""
from django.contrib.gis.db import models as gis_models
from django.conf import settings
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


class FPOZoneAssignment(BaseModel):
    """
    Stores which AgroClimaticZone an FPO belongs to, WITHOUT modifying the
    FPO model directly. FPO already has `latitude`/`longitude` (plain
    DecimalFields) — this model's zone-detection signal builds a Point
    from those on the fly rather than needing a `location` field on FPO.

    One row per FPO (OneToOneField). Created/updated automatically by the
    post_save signal on FPO in apps/gis_module/signals.py.
    """
    fpo = models.OneToOneField(
        'database.FPO', on_delete=models.CASCADE,
        related_name='zone_assignment'
    )
    agro_zone = models.ForeignKey(
        AgroClimaticZone, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='fpo_assignments'
    )
    detected_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'FPO Zone Assignment'
        verbose_name_plural = 'FPO Zone Assignments'

    def __str__(self):
        zone_code = self.agro_zone.code if self.agro_zone else 'unassigned'
        return f"{self.fpo} — {zone_code}"


class FPOCultivationArea(BaseModel):
    """
    The FPO's own farmland boundary, drawn by the FPO itself (e.g. via a
    map-drawing tool on the frontend). One area per FPO — a fresh POST
    replaces the existing polygon rather than adding a second one.

    Distinct from AgroClimaticZone/DistrictBoundary: those are shared
    admin-managed reference data, this is each FPO's own private data,
    editable by that FPO's own manager (not admin-only).
    """
    fpo = models.OneToOneField(
        'database.FPO', on_delete=models.CASCADE,
        related_name='cultivation_area'
    )
    area_polygon = gis_models.MultiPolygonField(
        srid=4326,
        help_text='FPO-drawn cultivation area boundary'
    )
    area_hectares = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text='Computed area in hectares — derived from area_polygon '
                   'when saved, using a projected CRS for accuracy'
    )

    class Meta:
        verbose_name = 'FPO Cultivation Area'
        verbose_name_plural = 'FPO Cultivation Areas'

    def __str__(self):
        return f"Cultivation area — {self.fpo}"


class FPOWeatherSnapshot(BaseModel):
    """
    Cached weather snapshot for an FPO's location (their cultivation
    area's centroid if drawn, else their own latitude/longitude). One
    row per FPO, refreshed on demand via
    POST /api/gis/weather/me/refresh/.

    TEMPORARY: values currently come from a simulated seasonal model
    (apps/gis_module/services.py: get_weather_for_point), NOT a real
    weather API. India Meteorological Department's Agromet Advisories
    API (api.imd.gov.in) is the intended real source — it's a strong
    fit (agriculture-focused, official government data) but requires
    account registration and IP whitelisting, an organizational step
    outside this module's scope. Swap the implementation inside
    get_weather_for_point() once that's set up; no other code needs to
    change. is_simulated tracks which mode produced a given row.
    """
    fpo = models.OneToOneField(
        'database.FPO', on_delete=models.CASCADE,
        related_name='weather_snapshot'
    )
    temperature_c = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    humidity_percent = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    rainfall_mm = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    season = models.CharField(
        max_length=30, blank=True,
        help_text='e.g. southwest_monsoon, northeast_monsoon, dry_season'
    )
    description = models.CharField(max_length=200, blank=True)
    is_simulated = models.BooleanField(
        default=True,
        help_text='True while using the simulated seasonal mock; set '
                   'False once a real weather API is wired in'
    )
    fetched_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'FPO Weather Snapshot'
        verbose_name_plural = 'FPO Weather Snapshots'

    def __str__(self):
        return f"Weather — {self.fpo} ({self.season})"

class ZoneBoundaryVersion(BaseModel):
    """
    A staged, uploaded GeoJSON FeatureCollection for zone boundaries.
    Uploading does NOT immediately affect live AgroClimaticZone data —
    only activating a version does. Same proven pattern as
    MLModelVersion (apps/database/models/recommendations.py):
    activating one version automatically deactivates all others.
    """
    label = models.CharField(
        max_length=150,
        help_text='e.g. the uploaded filename, or a short description'
    )
    geojson_data = models.JSONField(
        help_text='The raw uploaded FeatureCollection — validated at '
                   'upload time but not yet applied to live zones'
    )
    is_active = models.BooleanField(
        default=False,
        help_text='Only ONE version can be active at a time — activating '
                   'applies this data to the live AgroClimaticZone rows'
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='zone_boundary_uploads'
    )

    class Meta:
        verbose_name = 'Zone Boundary Version'
        verbose_name_plural = 'Zone Boundary Versions'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if self.is_active:
            ZoneBoundaryVersion.objects.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.label} {'(active)' if self.is_active else ''}"


class SoilRegion(BaseModel):
    """
    Soil type by location, INDEPENDENT of AgroClimaticZone boundaries — a
    zone can genuinely span several soil regions, so this is deliberately
    its own polygon layer rather than a field on AgroClimaticZone (which
    only ever supported one soil_type per zone). See
    apps.gis_module.services.find_soil_region_for_point().
    """
    code = models.CharField(
        max_length=30, unique=True,
        help_text='e.g. laterite_central, alluvial_coastal'
    )
    name_en = models.CharField(max_length=200)
    name_ml = models.CharField(max_length=200)
    boundary = gis_models.MultiPolygonField(
        srid=4326,
        help_text='Soil region polygon — independent of AgroClimaticZone boundaries'
    )
    soil_type = models.CharField(
        max_length=200,
        help_text='e.g. Laterite, Alluvial, Sandy loam'
    )

    class Meta:
        verbose_name = 'Soil Region'
        verbose_name_plural = 'Soil Regions'

    def __str__(self):
        return f"{self.name_en} ({self.soil_type})"


class SoilRegionVersion(BaseModel):
    """
    A staged, uploaded GeoJSON FeatureCollection for soil regions. Same
    pattern as ZoneBoundaryVersion — uploading does NOT immediately affect
    live SoilRegion data, only activating a version does.
    """
    label = models.CharField(
        max_length=150,
        help_text='e.g. the uploaded filename, or a short description'
    )
    geojson_data = models.JSONField(
        help_text='The raw uploaded FeatureCollection — validated at '
                   'upload time but not yet applied to live soil regions'
    )
    is_active = models.BooleanField(
        default=False,
        help_text='Only ONE version can be active at a time — activating '
                   'replaces the live SoilRegion set with this data'
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='soil_region_uploads'
    )

    class Meta:
        verbose_name = 'Soil Region Version'
        verbose_name_plural = 'Soil Region Versions'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if self.is_active:
            SoilRegionVersion.objects.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.label} {'(active)' if self.is_active else ''}"
