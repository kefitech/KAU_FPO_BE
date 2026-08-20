# P2-06: AI Crop Recommendations

**Status:** ⬜ Not started
**SRS Ref:** §3.2.1
**Depends on:** P2-05 (GIS — for agro-zone data)
**App:** `apps/recommendations/` (scaffolded)

---

## What This Module Does

AI-powered crop suitability recommendations for FPOs based on their district, agro-climatic zone, soil type, season, and commodity profile. Runs as a **separate FastAPI microservice** (port 8001, internal only). Django acts as a proxy.

Key SRS requirement: recommendations must include **plain-language reasoning** — not just a ranked list.

**Note on ML model:** SRS §5.1 does not specify a particular algorithm. Final model selection (XGBoost, LightGBM, Random Forest, or ensemble) will be determined after data analysis with KAU. The architecture below is model-agnostic — the FastAPI service wraps whichever model is chosen.

---

## Architecture

```
FPO request
    ↓
Django /api/recommendations/crops/
    ↓ (internal HTTP, port 8001)
FastAPI microservice
    ↓
ML model (ml_models Docker volume — XGBoost / LightGBM / Random Forest TBD)
    ↓
{ crops: [...], reasoning: "..." }
    ↑
Django stores result → returns to FPO
```

---

## New Models

**File:** `apps/database/models/recommendations.py`

```python
class MLModelVersion(BaseModel):
    version_code  = CharField(unique=True)      # e.g. "v1.2.0"
    description   = TextField()
    is_active     = BooleanField(default=False) # only one active at a time
    deployed_at   = DateTimeField()
    model_file_path = CharField()               # path in ml_models volume

class CropRecommendation(BaseModel):
    fpo            = FK(FPO)
    model_version  = FK(MLModelVersion)
    financial_year = CharField()                # e.g. "2025-26"
    input_snapshot = JSONField()                # district, zone, soil, season at time of request
    recommendations = JSONField()              # ranked list: [{ crop, confidence, reasoning }]
    feedback_rating = IntegerField(null=True)  # FPO rates quality 1–5
    feedback_comment = TextField(blank=True)
```

---

## API Endpoints

| Method | Endpoint | Who | Description |
|--------|----------|-----|-------------|
| GET | `/api/recommendations/crops/` | FPO | Get recommendation for my FPO (cached per financial year) |
| POST | `/api/recommendations/crops/refresh/` | FPO | Force re-run model with latest data |
| POST | `/api/recommendations/feedback/` | FPO | Rate recommendation quality 1–5 + comment |
| GET | `/api/admin/ml-models/` | Super Admin | List all model versions |
| POST | `/api/admin/ml-models/{id}/activate/` | Super Admin | Switch active model version |

**Swagger tag:** `tags=["Recommendations"]`

---

## FastAPI Request/Response Contract

**Request (Django → FastAPI):**
```json
{
  "fpo_id": "uuid",
  "district": "TRS",
  "agro_zone": "central_kerala",
  "soil_type": "laterite",
  "season": "kharif",
  "commodities": ["rice", "banana"],
  "tier": "B",
  "model_version": "v1.2.0"
}
```

**Response (FastAPI → Django):**
```json
{
  "recommendations": [
    {
      "crop": "banana",
      "confidence": 0.92,
      "reasoning": "Your district's rainfall pattern and laterite soil are well-suited for banana cultivation. Market demand in Thrissur shows 18% YoY growth.",
      "estimated_yield": "25 MT/acre",
      "business_guidance": "Consider Nendran variety for premium pricing..."
    }
  ],
  "model_version": "v1.2.0"
}
```

---

## Business Rules

1. One active recommendation per FPO per financial year — cached, refreshed on demand
2. All recommendations stored with `model_version` — mandatory for audit/explainability (SRS)
3. Recommendations include plain-language reasoning (SRS §3.2.1 — not just confidence scores)
4. Graceful degradation: if FastAPI unavailable → return cached last recommendation + warning banner
5. Only one `MLModelVersion` can have `is_active=True` at a time
6. Admin switches model version → next recommendation request uses new model
7. Feedback (1–5 rating) tracked for model retraining

---

## Testing Guide

### Setup
- FastAPI ML service running on port 8001 (use mock/stub for testing)
- At least one `MLModelVersion` with `is_active=True`
- Approved FPO with agro_zone set (requires P2-05 GIS)

### Test Cases

| # | Scenario | Expected Result |
|---|----------|-----------------|
| T01 | FPO calls `GET /api/recommendations/crops/` | Returns ranked crops with reasoning |
| T02 | Call again same financial year | Returns cached result (no new FastAPI call) |
| T03 | `POST /api/recommendations/crops/refresh/` | Forces new FastAPI call, updates cached result |
| T04 | FastAPI service is down | Returns last cached result + warning message |
| T05 | FPO submits feedback rating 4 | `CropRecommendation.feedback_rating` updated |
| T06 | Admin activates new model version | Next refresh uses new version |
| T07 | Two model versions exist, only one `is_active=True` | Activating new one deactivates old one |
| T08 | Check `CropRecommendation.model_version` after recommendation | Matches the active version at time of request |
| T09 | Response includes `reasoning` field | Non-empty plain-language text |
| T10 | CBBO user calls `/api/recommendations/crops/` | HTTP 403 |
