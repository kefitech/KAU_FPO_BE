"""
KAU-FPO Crop Recommendation Service — MOCK

This is NOT a trained model. Per the P2-06 doc: "Real XGBoost/LightGBM
model loading in FastAPI" is explicitly out of scope until KAU provides
training data. This mock exists so the full pipeline (Django proxy →
FastAPI → response → cached in CropRecommendation) can be built and
tested end to end now, with a swap-in point for the real model later.

Design note: the doc's stated objective is recommendations "based on
district, agro-climatic zone, soil type, season, and commodity
profile." This version genuinely scores crops using ZONE (eligibility
— which crops are geographically plausible), then SOIL/SEASON/
COMMODITIES (ranking — confidence and ordering within that pool) —
not just a static zone-keyed lookup table. district isn't scored
directly (no district-level crop data exists yet, only zone-level) but
is accepted and echoed for audit/API-contract completeness.

Run:
    source ml_service/venv/bin/activate
    uvicorn main:app --reload --port 8001
"""
import os
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="KAU-FPO Crop Recommendation Service (MOCK)")


# ---------------------------------------------------------------------------
# Request/response contract — matches the doc's specified shape
# ---------------------------------------------------------------------------

class RecommendationRequest(BaseModel):
    fpo_id: Optional[str] = None
    district: Optional[str] = None
    agro_zone: Optional[str] = None
    soil_type: Optional[str] = None
    season: Optional[str] = None
    commodities: List[str] = []
    tier: Optional[str] = None
    model_version: Optional[str] = None
    financial_year: Optional[str] = None


class CropRecommendationItem(BaseModel):
    crop: str
    confidence: float
    reasoning: str
    estimated_yield: str
    business_guidance: str


class RecommendationResponse(BaseModel):
    recommendations: List[CropRecommendationItem]
    model_version: str


# ---------------------------------------------------------------------------
# Crop knowledge base — each crop's zone eligibility + soil/season affinity
# ---------------------------------------------------------------------------
# Illustrative agronomic associations for Kerala, not derived from a
# dataset — same "placeholder until real data" spirit as the rest of
# this mock. soil_keywords are matched as case-insensitive substrings
# against the zone's soil_type string.

CROPS = [
    {
        "crop": "coconut", "zones": ["coastal_zone", "southern_zone", "central_zone", "northern_zone"],
        "soil_keywords": ["sandy", "alluvial", "laterite"],
        "preferred_seasons": ["southwest_monsoon", "northeast_monsoon", "dry_season"],
        "base_confidence": 0.72, "estimated_yield": "10-12 MT/ha",
        "description": "Coconut is a resilient, widely-suited Kerala staple crop.",
    },
    {
        "crop": "rice", "zones": ["coastal_zone", "central_zone", "northern_zone"],
        "soil_keywords": ["alluvial", "riverine"],
        "preferred_seasons": ["southwest_monsoon"],
        "base_confidence": 0.68, "estimated_yield": "3.5-4 MT/ha",
        "description": "Paddy cultivation suits fertile alluvial soils during the monsoon.",
    },
    {
        "crop": "banana", "zones": ["coastal_zone", "central_zone"],
        "soil_keywords": ["alluvial", "loam"],
        "preferred_seasons": ["southwest_monsoon", "northeast_monsoon"],
        "base_confidence": 0.65, "estimated_yield": "25 MT/ha",
        "description": "Banana thrives in moisture-retentive loamy soils.",
    },
    {
        "crop": "cardamom", "zones": ["high_ranges"],
        "soil_keywords": ["forest loam", "organic"],
        "preferred_seasons": ["southwest_monsoon", "northeast_monsoon"],
        "base_confidence": 0.75, "estimated_yield": "150-180 kg/ha",
        "description": "Cardamom needs cool high-elevation conditions and rich forest loam.",
    },
    {
        "crop": "tea", "zones": ["high_ranges"],
        "soil_keywords": ["forest loam"],
        "preferred_seasons": ["southwest_monsoon", "northeast_monsoon", "dry_season"],
        "base_confidence": 0.70, "estimated_yield": "2000-2200 kg/ha",
        "description": "Tea suits sustained high-elevation rainfall and acidic forest soils.",
    },
    {
        "crop": "pepper", "zones": ["high_ranges", "southern_zone", "northern_zone"],
        "soil_keywords": ["laterite", "forest loam"],
        "preferred_seasons": ["southwest_monsoon"],
        "base_confidence": 0.66, "estimated_yield": "300-400 kg/ha",
        "description": "Black pepper does well as an intercrop in laterite and forest-loam soils.",
    },
    {
        "crop": "rubber", "zones": ["southern_zone"],
        "soil_keywords": ["laterite"],
        "preferred_seasons": ["southwest_monsoon", "dry_season"],
        "base_confidence": 0.70, "estimated_yield": "1500-1700 kg/ha",
        "description": "Rubber plantations are well established on southern Kerala's laterite soils.",
    },
    {
        "crop": "tapioca", "zones": ["southern_zone", "northern_zone"],
        "soil_keywords": ["laterite", "sandy"],
        "preferred_seasons": ["dry_season", "northeast_monsoon"],
        "base_confidence": 0.62, "estimated_yield": "18-20 MT/ha",
        "description": "Tapioca is drought-tolerant and suits well-drained laterite/sandy soils.",
    },
    {
        "crop": "arecanut", "zones": ["central_zone"],
        "soil_keywords": ["alluvial", "riverine"],
        "preferred_seasons": ["southwest_monsoon"],
        "base_confidence": 0.68, "estimated_yield": "2 MT/ha",
        "description": "Arecanut favors fertile riverine soils in central Kerala.",
    },
    {
        "crop": "cashew", "zones": ["northern_zone", "coastal_zone"],
        "soil_keywords": ["laterite", "sandy"],
        "preferred_seasons": ["dry_season"],
        "base_confidence": 0.64, "estimated_yield": "800-900 kg/ha",
        "description": "Cashew tolerates dry, sandy-laterite coastal conditions well.",
    },
]

DEFAULT_CROP = {
    "crop": "rice", "zones": [],
    "soil_keywords": [], "preferred_seasons": [],
    "base_confidence": 0.55, "estimated_yield": "3 MT/ha",
    "description": "Zone not recognized — falling back to a common Kerala staple crop.",
}

SEASON_NOTES = {
    "southwest_monsoon": "Heavy monsoon rainfall favors water-intensive crops right now.",
    "northeast_monsoon": "Retreating monsoon — a good window for transplanting.",
    "dry_season": "Dry conditions — prioritize drought-tolerant crops or ensure irrigation.",
}

TIER_GUIDANCE = {
    "A": "As a Tier A FPO, you likely qualify for premium buyer linkages and export-oriented schemes.",
    "B": "Tier B FPOs often qualify for state-level market linkage and subsidy programs.",
    "C": "Consider KAU's capacity-building programs to help move toward higher-tier market access.",
    "D": "Starting-tier FPOs should prioritize basic infrastructure and KAU extension support first.",
}


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_crop(crop: dict, payload: RecommendationRequest):
    """
    Returns (confidence, reasoning). Starts from the crop's base
    confidence, then adjusts based on soil/season/commodity match —
    this is what makes the recommendation genuinely depend on more
    than just zone, per the doc's stated objective.
    """
    score = crop["base_confidence"]
    reasoning_parts = [crop["description"]]

    soil_type = (payload.soil_type or "").lower()
    if any(kw in soil_type for kw in crop["soil_keywords"]):
        score += 0.12
        reasoning_parts.append(f"Detected soil ({payload.soil_type}) is a strong match for this crop.")
    elif payload.soil_type:
        reasoning_parts.append(f"Detected soil: {payload.soil_type}.")

    if payload.season in crop["preferred_seasons"]:
        score += 0.08
    else:
        score -= 0.05
    season_note = SEASON_NOTES.get(payload.season)
    if season_note:
        reasoning_parts.append(season_note)

    commodities_lower = [c.lower() for c in (payload.commodities or [])]
    crop_name = crop["crop"].lower()
    if any(crop_name in c for c in commodities_lower):
        score += 0.07
        reasoning_parts.append(
            f"You already handle {crop['crop']}-related commodities — a natural fit to expand on."
        )

    score = max(0.30, min(round(score, 2), 0.97))
    return score, " ".join(reasoning_parts)


@app.post("/predict/crops/", response_model=RecommendationResponse)
def predict_crops(payload: RecommendationRequest) -> RecommendationResponse:
    # Zone determines the eligible candidate pool — geographic plausibility.
    candidates = [c for c in CROPS if payload.agro_zone in c["zones"]]
    if not candidates:
        candidates = [DEFAULT_CROP]

    tier_note = TIER_GUIDANCE.get(payload.tier, "Consider KAU's tier assessment for tailored scheme eligibility.")

    scored = []
    for crop in candidates:
        confidence, reasoning = score_crop(crop, payload)
        scored.append(
            CropRecommendationItem(
                crop=crop["crop"],
                confidence=confidence,
                reasoning=reasoning,
                estimated_yield=crop["estimated_yield"],
                business_guidance=(
                    f"Consider forming buyer linkages for {crop['crop']} through KAU's "
                    f"market channels. {tier_note}"
                ),
            )
        )

    # Soil/season/commodity scoring can reorder crops within the zone-eligible
    # pool — this is the actual "smarter than a static lookup" behavior.
    scored.sort(key=lambda item: -item.confidence)
    top_results = scored[:3]

    return RecommendationResponse(
        recommendations=top_results,
        model_version=payload.model_version or "mock-v1-scoring",
    )


@app.get("/health")
def health():
    """Simple liveness check — useful for confirming the service is up during dev."""
    return {"status": "ok", "service": "crop-recommendation-mock"}


# ---------------------------------------------------------------------------
# Model file management (P2-06 admin upload/activate flow)
# ---------------------------------------------------------------------------

# Shared folder — sibling to KAU_FPO_BE (this service lives at
# KAU_FPO_BE/ml_service/main.py, so it's THREE levels up: main.py ->
# ml_service -> KAU_FPO_BE -> KAU_FPO/ml_models). Matches
# settings.ML_MODELS_DIR on the Django side. Override via env var if
# your layout differs (e.g. in a Docker container) — explicit env var
# is safer than relying on relative-path math matching exactly.
ML_MODELS_DIR = Path(os.environ.get("ML_MODELS_DIR", Path(__file__).resolve().parent.parent.parent / "ml_models"))

_active_model_state = {
    "version_code": None,
    "model_file_path": None,
    "file_exists": None,
}


class ReloadModelRequest(BaseModel):
    model_file_path: str
    version_code: str


@app.post("/reload-model/")
def reload_model(payload: ReloadModelRequest):
    """
    Called by Django's MLModelVersionActivateView right after a model
    version is marked active. Right now this only RECORDS which file
    is "active" — it does not actually load a real model, since none
    exists yet (predict_crops() still uses the scoring mock above
    regardless of what's recorded here).

    Once a real model exists: this is where you'd add
    `model = joblib.load(full_path)` (or your library's loader) and
    store the loaded object for predict_crops() to actually use.
    """
    full_path = ML_MODELS_DIR / payload.model_file_path
    file_exists = full_path.is_file()

    _active_model_state["version_code"] = payload.version_code
    _active_model_state["model_file_path"] = payload.model_file_path
    _active_model_state["file_exists"] = file_exists

    return {
        "status": "acknowledged",
        "version_code": payload.version_code,
        "resolved_path": str(full_path),
        "file_exists": file_exists,
        "note": (
            "File found and recorded, but predict_crops() still uses the "
            "scoring mock — real model loading isn't implemented yet."
            if file_exists else
            "WARNING: file not found at the resolved shared-folder path. "
            "Check ML_MODELS_DIR matches Django's settings.ML_MODELS_DIR."
        ),
    }


@app.get("/model-status/")
def model_status():
    """Quick way to check what Django last told this service to activate."""
    return _active_model_state