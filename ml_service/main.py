"""
KAU-FPO Crop Recommendation Service — MOCK

This is NOT a trained model. Per the P2-06 doc: "Real XGBoost/LightGBM
model loading in FastAPI" is explicitly out of scope until KAU provides
training data. This mock exists so the full pipeline (Django proxy →
FastAPI → response → cached in CropRecommendation) can be built and
tested end to end now, with a swap-in point for the real model later.

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

# Shared folder — sibling to both this service and the Django project,
# matching settings.ML_MODELS_DIR on the Django side and the doc's
# eventual Docker volume plan. Override via env var if the mount point
# differs (e.g. in a container).
ML_MODELS_DIR = Path(os.environ.get("ML_MODELS_DIR", Path(__file__).resolve().parent.parent.parent / "ml_models"))

# In-memory record of the currently active model — updated by
# /reload-model/, read by predict_crops(). NOT the actual loaded model
# object yet (no real model exists to load) — this tracks WHICH FILE
# would be loaded once real inference code replaces the mock lookup
# table below. version_code/model_file_path are what Django's activate
# endpoint sends.
_active_model_state = {
    "version_code": None,
    "model_file_path": None,
    "file_exists": None,
}


class ReloadModelRequest(BaseModel):
    model_file_path: str
    version_code: str


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
# Mock "model" — deterministic, varies by zone/soil/season/tier
# ---------------------------------------------------------------------------

ZONE_CROP_PROFILES = {
    "coastal_zone": [
        {
            "crop": "coconut", "confidence": 0.91, "estimated_yield": "12 MT/ha",
            "reasoning_template": "Coastal sandy-alluvial soil and humid conditions strongly favor coconut.",
        },
        {
            "crop": "rice", "confidence": 0.78, "estimated_yield": "3.5 MT/ha",
            "reasoning_template": "Alluvial soil near the coast suits paddy cultivation during the monsoon.",
        },
    ],
    "high_ranges": [
        {
            "crop": "cardamom", "confidence": 0.93, "estimated_yield": "180 kg/ha",
            "reasoning_template": "Cool, high-elevation forest loam is ideal for cardamom.",
        },
        {
            "crop": "tea", "confidence": 0.85, "estimated_yield": "2200 kg/ha",
            "reasoning_template": "High rainfall and elevation favor tea cultivation.",
        },
    ],
    "southern_zone": [
        {
            "crop": "rubber", "confidence": 0.88, "estimated_yield": "1600 kg/ha",
            "reasoning_template": "Laterite soil in this zone is well suited to rubber plantations.",
        },
        {
            "crop": "tapioca", "confidence": 0.75, "estimated_yield": "20 MT/ha",
            "reasoning_template": "Well-drained laterite soil suits tapioca.",
        },
    ],
    "central_zone": [
        {
            "crop": "arecanut", "confidence": 0.82, "estimated_yield": "2 MT/ha",
            "reasoning_template": "Riverine alluvial soil supports arecanut well.",
        },
        {
            "crop": "rice", "confidence": 0.80, "estimated_yield": "4 MT/ha",
            "reasoning_template": "Fertile alluvial soil suits paddy cultivation.",
        },
    ],
    "northern_zone": [
        {
            "crop": "cashew", "confidence": 0.86, "estimated_yield": "900 kg/ha",
            "reasoning_template": "Sandy laterite soil favors cashew cultivation.",
        },
        {
            "crop": "coconut", "confidence": 0.79, "estimated_yield": "10 MT/ha",
            "reasoning_template": "Suitable soil and rainfall conditions for coconut.",
        },
    ],
}

DEFAULT_PROFILE = [
    {
        "crop": "rice", "confidence": 0.65, "estimated_yield": "3 MT/ha",
        "reasoning_template": "Zone not recognized — falling back to a common Kerala staple crop.",
    },
]

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


@app.post("/predict/crops/", response_model=RecommendationResponse)
def predict_crops(payload: RecommendationRequest) -> RecommendationResponse:
    profile = ZONE_CROP_PROFILES.get(payload.agro_zone, DEFAULT_PROFILE)
    season_note = SEASON_NOTES.get(payload.season, "")
    tier_note = TIER_GUIDANCE.get(payload.tier, "Consider KAU's tier assessment for tailored scheme eligibility.")

    recommendations = []
    for item in profile:
        reasoning = item["reasoning_template"]
        if payload.soil_type:
            reasoning += f" Detected soil: {payload.soil_type}."
        if season_note:
            reasoning += f" {season_note}"

        recommendations.append(
            CropRecommendationItem(
                crop=item["crop"],
                confidence=item["confidence"],
                reasoning=reasoning,
                estimated_yield=item["estimated_yield"],
                business_guidance=(
                    f"Consider forming buyer linkages for {item['crop']} through KAU's "
                    f"market channels. {tier_note}"
                ),
            )
        )

    return RecommendationResponse(
        recommendations=recommendations,
        model_version=payload.model_version or "mock-v0",
    )


@app.post("/reload-model/")
def reload_model(payload: ReloadModelRequest):
    """
    Called by Django's MLModelVersionActivateView right after a model
    version is marked active. Right now this only RECORDS which file
    is "active" — it does not actually load a real model, since none
    exists yet (predict_crops() still uses the mock lookup table below
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
            "mock lookup table — real model loading isn't implemented yet."
            if file_exists else
            "WARNING: file not found at the resolved shared-folder path. "
            "Check ML_MODELS_DIR matches Django's settings.ML_MODELS_DIR."
        ),
    }


@app.get("/model-status/")
def model_status():
    """Quick way to check what Django last told this service to activate."""
    return _active_model_state


@app.get("/health")
def health():
    """Simple liveness check — useful for confirming the service is up during dev."""
    return {"status": "ok", "service": "crop-recommendation-mock"}