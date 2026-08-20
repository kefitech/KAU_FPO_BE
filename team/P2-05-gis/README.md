# P2-05: GIS Integration

**Status:** ⬜ Not started
**SRS Ref:** §3.2.2
**Depends on:** Nothing (but must be done before Recommendations)
**App:** `apps/gis_module/`

---

## What This Module Does

Adds interactive map capabilities to the platform:
- FPOs see their location and agro-climatic zone on a map
- Admins see district-level FPO density heatmap
- GIS zone data feeds into the AI crop recommendation engine
- FPOs can draw their cultivation area as a polygon

---

## Infrastructure Required First

- [ ] PostGIS extension enabled on RDS (`CREATE EXTENSION postgis;`)
- [ ] GeoDjango installed — GDAL + GEOS system packages in Dockerfile
- [ ] Bhuvan/ISRO Kerala dataset files downloaded and loaded into DB

---

## Model Changes

**File:** `apps/database/models/fpo.py`
```python
# Add PostGIS fields (Phase 1 lat/lng stays for backward compat)
from django.contrib.gis.db import models as gis_models
location       = gis_models.PointField(null=True, srid=4326)
cultivation_area = gis_models.PolygonField(null=True, blank=True)
agro_zone      = CharField(max_length=20, null=True, blank=True)  # auto-detected from location
```

**File:** `apps/database/models/gis.py` (new file)
```python
class AgroClimaticZone(BaseModel):
    code          = CharField(unique=True)
    name_en       = CharField()
    name_ml       = CharField()
    boundary      = gis_models.MultiPolygonField(srid=4326)
    suitable_crops = JSONField()    # list of commodity codes

class DistrictBoundary(BaseModel):
    code     = CharField(unique=True)   # matches District enum in constants.py
    boundary = gis_models.MultiPolygonField(srid=4326)
    centroid = gis_models.PointField()
```

---

## API Endpoints

| Method | Endpoint | Who | Description |
|--------|----------|-----|-------------|
| GET | `/api/gis/zones/` | All | All agro-climatic zone boundaries (GeoJSON) |
| GET | `/api/gis/zones/{code}/` | All | Single zone + suitable crops list |
| GET | `/api/gis/fpo-map/` | Admin / Govt | All approved FPO locations as GeoJSON points |
| GET | `/api/gis/district/{code}/` | Admin / Govt | District boundary + FPO density |
| GET | `/api/gis/fpo/{id}/location/` | FPO owner / Admin | FPO location + zone info |
| POST | `/api/gis/fpo/{id}/cultivation/` | FPO owner | Set cultivation area polygon |

**Swagger tag:** `tags=["GIS"]`

---

## Business Rules

1. Phase 1 `latitude`/`longitude` fields migrated to PostGIS `PointField` via data migration
2. When FPO sets location → system auto-detects agro-climatic zone from Bhuvan data
3. `AgroClimaticZone.suitable_crops` is a list — feeds into recommendation engine as zone filter
4. Cultivation area polygon is optional — FPO can skip it
5. FPO can only set/update their own location
6. GIS zone + district boundary data is read-only — loaded once from Bhuvan, updated by admin

---

## Testing Guide

### Setup
- Enable PostGIS on test DB
- Load sample zone + district boundary data (at least Thrissur district)
- Have 2–3 approved FPOs with lat/lng already set

### Test Cases

| # | Scenario | Expected Result |
|---|----------|-----------------|
| T01 | `GET /api/gis/zones/` | Returns GeoJSON with zone boundaries |
| T02 | `GET /api/gis/district/TRS/` | Returns Thrissur boundary + FPO count |
| T03 | `GET /api/gis/fpo-map/` | GeoJSON FeatureCollection of all FPO points |
| T04 | FPO sets cultivation area polygon | Saved, appears in `GET /api/gis/fpo/{id}/location/` |
| T05 | FPO sets location → check `fpo.agro_zone` | Auto-populated from zone intersection |
| T06 | Unauthenticated user calls `GET /api/gis/fpo-map/` | HTTP 401 |
| T07 | FPO user calls `GET /api/gis/fpo-map/` (admin-only endpoint) | HTTP 403 |
| T08 | Phase 1 FPO with lat/lng — check PostGIS field | Migrated correctly via data migration |
| T09 | `GET /api/gis/zones/{code}/` | Returns zone + `suitable_crops` list |
| T10 | FPO tries to set another FPO's cultivation area | HTTP 403 |
