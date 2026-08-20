# Aravind — P2-05 GIS + P2-06 Crop Recommendations

## What You Are Building

Two modules:
1. **GIS Integration** — map Kerala's agro-climatic zones and district boundaries in PostGIS. Auto-detect which zone an FPO is in when they save their GPS location.
2. **AI Crop Recommendations** — Django proxy that calls a FastAPI ML service and stores results. Build everything except the real ML model (that comes when KAU provides training data).

---

## Models (Already Written — Do Not Change)

All models are in `apps/database/models/`. Your models are:

| Model | File |
|---|---|
| `AgroClimaticZone` | `apps/database/models/gis.py` |
| `DistrictBoundary` | `apps/database/models/gis.py` |
| `MLModelVersion` | `apps/database/models/recommendations.py` |
| `CropRecommendation` | `apps/database/models/recommendations.py` |

**Do not move models out of `apps/database/models/`.** Models live there. API logic goes in `apps/gis_module/` and `apps/recommendations/`.

---

## Step 1 — Enable PostGIS on Dev DB (Do This First)

```bash
# Connect to your local PostgreSQL
psql -U athul_dasp -d kau_fpo

# Run this once
CREATE EXTENSION IF NOT EXISTS postgis;
\q
```

Then add `django.contrib.gis` to `INSTALLED_APPS` in `config/settings/base.py` — ask Athul before doing this, he will do it centrally.

---

## Step 2 — Run Migrations

```bash
source venv/bin/activate
python manage.py migrate
```

Confirm it runs clean with no errors before touching any API code.

---

## Step 3 — Build GIS APIs First (P2-05)

P2-06 depends on `FPO.agro_zone` being populated, so build GIS first.

**App folder:** `apps/gis_module/api/`

Files to create:
```
apps/gis_module/api/
├── zones.py       ← AgroClimaticZone endpoints
├── districts.py   ← DistrictBoundary endpoints
└── urls.py
```

### Endpoints to build

```
GET  /api/gis/zones/                  — list all agro-climatic zones (name + boundary GeoJSON)
GET  /api/gis/zones/{code}/           — single zone detail
GET  /api/gis/districts/              — list all district boundaries
GET  /api/gis/fpo-location/           — FPO's map pin + zone name (FPO auth only)
POST /api/gis/detect-zone/            — given {lat, lng} → return which zone it falls in
```

### Auto-populate FPO.agro_zone

When an FPO saves their `location` (PointField), auto-detect their zone. Add this signal in `apps/gis_module/signals.py`:

```python
from django.db.models.signals import post_save
from django.dispatch import receiver
from apps.database.models import FPO, AgroClimaticZone

@receiver(post_save, sender=FPO)
def detect_fpo_agro_zone(sender, instance, **kwargs):
    if instance.location:
        zone = AgroClimaticZone.objects.filter(
            boundary__contains=instance.location
        ).first()
        if zone and instance.agro_zone != zone.code:
            FPO.objects.filter(pk=instance.pk).update(agro_zone=zone.code)
```

### Seed zone boundaries

Once KAU provides a GeoJSON file for Kerala agro-climatic zones, create `scripts/seed_gis_zones.py`. Until then, seed 5 placeholder zones with dummy polygons for testing.

---

## Step 4 — Build Crop Recommendation APIs (P2-06)

**App folder:** `apps/recommendations/api/`

Files to create:
```
apps/recommendations/api/
├── recommendations.py   ← main endpoints
└── urls.py
```

### Endpoints to build

```
GET  /api/recommendations/me/              — FPO's current year recommendation (from DB cache)
POST /api/recommendations/me/request/      — request fresh recommendation (triggers FastAPI call)
POST /api/recommendations/me/feedback/     — FPO submits 1–5 rating + comment

GET  /api/admin/ml-models/                 — list all ML model versions (admin only)
POST /api/admin/ml-models/                 — register new model version
POST /api/admin/ml-models/{id}/activate/   — set as active model
```

### How to call FastAPI (proxy pattern)

```python
import httpx
from django.conf import settings

def get_crop_recommendation(fpo, model_version):
    payload = {
        "district": fpo.district,
        "agro_zone": fpo.agro_zone,
        "financial_year": "2025-26",
    }
    try:
        response = httpx.post(
            f"{settings.ML_SERVICE_URL}/predict/crops/",
            json=payload,
            timeout=10.0
        )
        response.raise_for_status()
        return response.json()
    except Exception:
        # Graceful degradation — return last cached recommendation
        last = CropRecommendation.objects.filter(fpo=fpo).order_by('-created_at').first()
        if last:
            return {"cached": True, "recommendations": last.recommendations}
        return {"cached": True, "recommendations": [], "warning": "AI service unavailable"}
```

`ML_SERVICE_URL` will be `http://localhost:8001` in dev. Add it to `.env`.

### Mock response until real model is ready

When FastAPI is not running, the fallback above handles it. Also create a mock endpoint in FastAPI:

```python
# ml_service/main.py
@app.post("/predict/crops/")
def predict_crops(payload: dict):
    return {
        "recommendations": [
            {"crop": "rice", "confidence": 0.87, "reasoning": "Mock response — model not yet loaded", "estimated_yield": "3.2 MT/ha"},
            {"crop": "banana", "confidence": 0.74, "reasoning": "Mock response", "estimated_yield": "25 MT/ha"},
        ]
    }
```

---

## How to Write a ViewSet — Copy This Pattern

```python
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema
from apps.core.views import TranslatedViewSet
from apps.core.utils.responses import StandardResponse
from apps.core.utils.pagination import StandardPagination
from apps.core.permissions.rbac import IsAdmin
from apps.core.services.translation import t

class AgroClimaticZoneViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    TranslatedViewSet
):
    queryset = AgroClimaticZone.objects.all()
    serializer_class = AgroClimaticZoneSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination
    lookup_field = 'code'

    list_message = 'gis.zones_retrieved'
    create_message = 'gis.zone_created'
    update_message = 'gis.zone_updated'
    destroy_message = 'gis.zone_deleted'

    @extend_schema(tags=["GIS"])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
```

---

## Swagger Tags to Use

```python
@extend_schema(tags=["GIS"])                        # for gis endpoints
@extend_schema(tags=["Recommendations"])            # for recommendation endpoints
@extend_schema(tags=["Admin - ML Models"])          # for admin ML version management
```

---

## Translation Keys to Add

Add these to `scripts/seed_translations.py` under a new `gis` and `recommendations` category:

```
gis.zones_retrieved
gis.zone_not_found
gis.zone_detected
recommendations.retrieved
recommendations.requested
recommendations.feedback_saved
recommendations.service_unavailable
```

---

## Git Workflow

```bash
# Your branch names
feature/p2-05-gis-zones
feature/p2-05-agro-zone-detection
feature/p2-06-recommendations-api

# Raise PR to develop when each is done
# Never push to main
```

---

## Files You Will Create

```
apps/gis_module/api/zones.py
apps/gis_module/api/districts.py
apps/gis_module/api/urls.py
apps/gis_module/signals.py
apps/recommendations/api/recommendations.py
apps/recommendations/api/urls.py
apps/recommendations/services.py        ← FastAPI proxy logic
scripts/seed_gis_zones.py
```

---

## What NOT to Build Yet

- Real XGBoost/LightGBM model loading in FastAPI (waiting for KAU dataset)
- Bhuvan WMS live map tiles (frontend concern, not backend)
- GeoJSON file for zone boundaries (waiting for KAU to provide the file)
