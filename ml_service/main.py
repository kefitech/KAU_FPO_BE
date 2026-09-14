"""
KAU-FPO Crop Recommendation Service -- multiclass model version (v4).

Same Pydantic request/response contract, same `/predict/crops/` endpoint
path, same `/health`, `/reload-model/`, `/model-status/` and
`ML_MODELS_DIR` mechanism as the earlier v2/v3 services -- but the model
itself is now architecturally different from both.

v4 CHANGE, CONCRETELY: crop_name is now the model's TARGET, never an
input feature. v2/v3 both trained a BINARY is_suitable classifier with
crop_name as one of the input features -- which let the model shortcut
through crop identity ("if crop_name == Rice, predict suitable=1") instead
of genuinely learning from environmental fit. That shortcut was real and
measured: crop_name's feature importance came out to 30.8% (more than
double any other feature) in the v3 model, while soil_ph_mid -- a real
signal -- got under 1%. In practice it meant a handful of crops the PoP
book documents as broadly/generically suitable (Rice, Cashew, Anthurium)
dominated the top of every zone's recommendations almost regardless of
actual conditions.

v4 removes crop_name (and crop_group) from the FEATURES entirely --
FEATURE_CATEGORICAL/FEATURE_NUMERIC below are purely environmental
(zone, soil_type, season, temperature, rainfall, humidity, soil pH) -- and
makes crop_name the multiclass TARGET instead. `predict_crops()` builds
ONE feature row from the request's resolved environment and calls
predict_proba() ONCE, getting a probability across all ~149 known crops
directly, instead of the old per-candidate loop that scored each crop
independently via its own binary "is this ONE crop suitable, yes/no" call.
This is the standard way real crop-recommendation ML systems are built
(features are the growing conditions; the crop is what's being predicted),
and it makes crop-identity memorization structurally impossible: there is
no crop_name column left for the model to shortcut through.

See retrain_pipeline.py's module docstring and _train()'s docstring for
the full rationale and the top_5_hit_rate metric (the honest evaluation
metric for this framing -- see its own docstring for why plain accuracy
understates quality here).

HONESTY NOTE (carried over from the whole project, still true): the
training label is still RULE-DERIVED (real climate checked against
PoP-stated crop requirements, cross-walked from KAU's 5 physiographic
zones onto this service's 5 geographic zones), not an observed real
planting outcome. Treat `confidence` as "how well this crop's documented
requirements match this zone/season's typical climate, relative to the
other crops documented for this zone," not a market-validated success
probability. See model/training_metrics_v4.json for the leave-one-zone-out
cross-validation (the honest generalization estimate).

Run:
    pip install -r requirements.txt
    uvicorn main:app --reload --port 8001
"""
import json
import logging
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import List, Optional

import joblib
import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from data_access_v3 import CropKnowledgeBase, resolve_soil_category
from logging_config import setup_logging
from retrain_pipeline import (
    run_retrain, validate_source_csv, validate_preexpanded_csv,
    _detect_dataset_format, is_blocking, DatasetValidationError,
    REQUIRED_COLUMNS, REQUIRED_PREEXPANDED_COLUMNS,
)

setup_logging()
logger = logging.getLogger("ml_service")

# Load the SAME .env file Django reads (config('ML_MODELS_DIR', ...) in
# config/settings/base.py), so both services agree on ML_MODELS_DIR from one
# place instead of each computing its own default and hoping they match.
# This assumes ml_service/ sits directly inside the Django project root
# (KAU_FPO_BE/) -- adjust the parent count below if your layout differs.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

app = FastAPI(title="KAU-FPO Crop Recommendation Service")

SERVED_MODEL_VERSION = "v4.0.0-rf-multiclass"  # updated at runtime by /reload-model/ on a successful swap

MODEL_PATH = "model/crop_suitability_rf_v4.joblib"
# v4: FEATURES are environmental factors only -- crop_name/crop_group are
# deliberately NOT features here, crop_name is the model's predicted TARGET.
# See this module's docstring and retrain_pipeline.py's for why.
FEATURE_CATEGORICAL = ["zone", "soil_type", "season"]
FEATURE_NUMERIC = ["temperature_avg_C", "rainfall_mm", "humidity_pct", "soil_ph_mid"]

VALID_ZONES = {"coastal_zone", "southern_zone", "central_zone", "northern_zone", "high_ranges"}
VALID_SEASONS = {"southwest_monsoon", "northeast_monsoon", "dry_season"}

# Cap on model files accepted by /validate-model/. The real RF model is ~5 MB;
# this is a sanity bound, not a tuning knob.
MAX_MODEL_UPLOAD_BYTES = 200 * 1024 * 1024


# ---------------------------------------------------------------------------
# Model-file validation. Used in THREE places so the check can't be bypassed:
#   - startup (load_artifacts): a service with an incompatible default model
#     fails loudly instead of coming up "healthy" and 500-ing on first predict
#   - /reload-model/: an activated version that doesn't fit is refused, and
#     the previously-loaded model stays in place
#   - /validate-model/: Django's Register Model flow calls this BEFORE saving
#     the file or creating the DB row, so a bad upload never gets registered
# Motivation: a v2-era model (trained with an `elevation_m` column) was
# activated via Register Model -> Activate and only failed at predict time
# with "columns are missing: {'elevation_m'}". Nothing in that chain looked
# inside the file. This does.
# ---------------------------------------------------------------------------

EXPECTED_MODEL_COLUMNS = FEATURE_CATEGORICAL + FEATURE_NUMERIC


def _detect_input_columns(pipe) -> Optional[list]:
    """Best-effort read of the columns a fitted pipeline expects at predict time."""
    if hasattr(pipe, "feature_names_in_"):
        return list(pipe.feature_names_in_)
    # sklearn Pipeline: the first step is normally the ColumnTransformer
    steps = getattr(pipe, "steps", None)
    if steps:
        first = steps[0][1]
        if hasattr(first, "feature_names_in_"):
            return list(first.feature_names_in_)
        transformers = getattr(first, "transformers_", None)
        if transformers:
            cols = []
            for _name, _trans, sel in transformers:
                if isinstance(sel, (list, tuple)):
                    cols.extend(sel)
            return cols or None
    return None


def validate_model_pipeline(pipe) -> tuple[list[str], list[str]]:
    """
    Returns (problems, warnings). Empty `problems` means the model is safe to
    serve. Checks structure only -- it says nothing about whether the model is
    any GOOD (that's what training_metrics are for), just whether predict_crops()
    can call it at all.
    """
    problems: list[str] = []
    warnings_out: list[str] = []

    if not hasattr(pipe, "predict_proba"):
        problems.append(
            f"Loaded object is a {type(pipe).__name__} with no predict_proba() -- "
            "not a classifier pipeline this service can use."
        )
        return problems, warnings_out

    detected = _detect_input_columns(pipe)
    if detected is None:
        warnings_out.append(
            "Could not determine the model's expected input columns from the file; "
            "column-schema check skipped, relying on the smoke prediction below."
        )
    else:
        expected_set, detected_set = set(EXPECTED_MODEL_COLUMNS), set(detected)
        extra = sorted(detected_set - expected_set)
        missing = sorted(expected_set - detected_set)
        if extra or missing:
            msg = "Input columns don't match this service's feature schema."
            if extra:
                msg += (f" The model expects column(s) this service never sends: {extra}"
                        " (a model trained with the old v2 features would show 'elevation_m' here).")
            if missing:
                msg += f" The model lacks column(s) this service always sends: {missing}."
            msg += f" Expected exactly: {EXPECTED_MODEL_COLUMNS}."
            problems.append(msg)

    # v4: classes_ are crop names (a multiclass target), not [0, 1] -- just
    # sanity-check there's more than one class and they're all real strings,
    # rather than requiring an exact known set (a retrained model may
    # legitimately have a different crop count than the one currently served).
    classes = getattr(pipe, "classes_", None)
    if classes is not None:
        if len(classes) < 2:
            problems.append(
                f"Model classes_ has only {len(classes)} class(es); this service expects a multiclass "
                "crop-name classifier with many candidate crops."
            )
        elif not all(isinstance(c, str) and c.strip() for c in classes):
            problems.append(
                "Model classes_ contains non-string or blank values; this service expects classes_ to be "
                "crop_name strings (a model trained with the old v2/v3 binary is_suitable target would "
                "show classes_ == [0, 1] here)."
            )

    # Smoke prediction with one plausible row -- catches anything the structural
    # checks above can't see (broken pickle internals, wrong step order, etc).
    if not problems:
        smoke = pd.DataFrame([{
            "zone": "coastal_zone", "soil_type": "Laterite", "season": "dry_season",
            "temperature_avg_C": 28.0, "rainfall_mm": 100.0, "humidity_pct": 75.0, "soil_ph_mid": 6.0,
        }])
        try:
            proba = pipe.predict_proba(smoke[EXPECTED_MODEL_COLUMNS])
            n_classes = len(classes) if classes is not None else proba.shape[1]
            if getattr(proba, "shape", None) != (1, n_classes):
                problems.append(
                    f"Smoke prediction returned shape {getattr(proba, 'shape', None)}, expected (1, {n_classes})."
                )
        except Exception as exc:  # noqa: BLE001 -- any failure here IS the finding
            problems.append(f"Smoke prediction failed: {type(exc).__name__}: {exc}")

    return problems, warnings_out


def load_model_checked(path) -> tuple[object, list[str], list[str]]:
    """
    joblib.load() with the sklearn version-mismatch warning captured (surfaced
    as a warning instead of a stderr line nobody reads), followed by
    validate_model_pipeline(). Returns (pipe_or_None, problems, warnings).
    """
    import warnings as _warnings
    warns: list[str] = []
    with _warnings.catch_warnings(record=True) as caught:
        _warnings.simplefilter("always")
        try:
            pipe = joblib.load(path)
        except Exception as exc:  # noqa: BLE001
            return None, [f"File could not be loaded with joblib: {type(exc).__name__}: {exc}"], warns
    for w in caught:
        warns.append(f"{w.category.__name__}: {w.message}")
    problems, more_warns = validate_model_pipeline(pipe)
    return pipe, problems, warns + more_warns

DEFAULT_CROP_NAME = "Rice"
DEFAULT_ESTIMATED_YIELD = "3 MT/ha"

SEASON_NOTES = {
    "southwest_monsoon": "Heavy monsoon rainfall favors water-intensive crops right now.",
    "northeast_monsoon": "Retreating monsoon -- a good window for transplanting.",
    "dry_season": "Dry conditions -- prioritize drought-tolerant crops or ensure irrigation.",
}

TIER_GUIDANCE = {
    "A": "As a Tier A FPO, you likely qualify for premium buyer linkages and export-oriented schemes.",
    "B": "Tier B FPOs often qualify for state-level market linkage and subsidy programs.",
    "C": "Consider KAU's capacity-building programs to help move toward higher-tier market access.",
    "D": "Starting-tier FPOs should prioritize basic infrastructure and KAU extension support first.",
}


# ---------------------------------------------------------------------------
# Request/response contract -- IDENTICAL shape to the mock you shared
# ---------------------------------------------------------------------------

class RecommendationRequest(BaseModel):
    fpo_id: Optional[str] = None
    district: Optional[str] = None
    agro_zone: Optional[str] = None
    soil_type: Optional[str] = None
    season: Optional[str] = None
    # Optional manual override: the FPO's actual measured soil pH. When
    # given, this replaces the soil_ph_mid estimate (the resolved soil
    # category's book-documented pH range midpoint) with the real value,
    # which is a more accurate model input than a category-wide estimate.
    soil_ph: Optional[float] = None
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
# Model + knowledge base, loaded at startup (and reloadable, see below)
# ---------------------------------------------------------------------------

_model = None
_kb: Optional[CropKnowledgeBase] = None


@app.on_event("startup")
def load_artifacts():
    global _model, _kb
    pipe, problems, warns = load_model_checked(MODEL_PATH)
    for w in warns:
        logger.warning("startup model warning: %s", w)
    if problems:
        # Refuse to start rather than come up "healthy" and 500 on the first
        # real prediction. The message names the exact mismatch.
        logger.error("startup failed: default model at %s is incompatible: %s", MODEL_PATH, " | ".join(problems))
        raise RuntimeError(
            f"Default model at {MODEL_PATH} is not compatible with this service: " + " | ".join(problems)
        )
    _model = pipe
    _kb = CropKnowledgeBase()
    logger.info("startup complete: loaded %s as model_version=%s", MODEL_PATH, SERVED_MODEL_VERSION)


def build_reasoning(crop_name: str, zone: str, season: str, climate: dict, confidence: float,
                     kb: CropKnowledgeBase, soil_note: str) -> str:
    profile = kb.crop_zone_profile(crop_name, zone)
    parts = []
    if confidence >= 0.6:
        parts.append(f"{crop_name} is a strong fit for {zone} in the {season.replace('_', ' ')}.")
    elif confidence >= 0.4:
        parts.append(f"{crop_name} is a moderate fit for {zone} in the {season.replace('_', ' ')}.")
    else:
        parts.append(f"{crop_name} is a weak fit for {zone} in the {season.replace('_', ' ')} based on current conditions.")
    if profile is not None:
        parts.append(
            f"KAU's Package of Practices states a temperature range of "
            f"{profile['temp_lo']:.0f}-{profile['temp_hi']:.0f} C and pH "
            f"{profile['ph_lo']:.1f}-{profile['ph_hi']:.1f} for {crop_name}."
        )
    parts.append(
        f"{zone}'s typical {season.replace('_', ' ')} conditions are approx. "
        f"{climate['temperature_avg_C']:.1f} C average temperature, "
        f"{climate['rainfall_mm']:.0f}mm rainfall, and {climate['humidity_pct']:.0f}% humidity "
        f"(averaged from {climate['n_samples']} real regional climate records)."
    )
    parts.append(soil_note)
    season_note = SEASON_NOTES.get(season)
    if season_note:
        parts.append(season_note)
    return " ".join(parts)


def build_business_guidance(crop_name: str, tier: Optional[str], kb: CropKnowledgeBase) -> str:
    rows = kb.crop_rows(crop_name)
    ref_row = rows.iloc[0] if len(rows) else None
    guidance = []
    if ref_row is not None and ref_row.get("variety_recommendations"):
        guidance.append(f"KAU-recommended varieties: {ref_row['variety_recommendations']}.")
    else:
        guidance.append("No specific variety recommendation stated in the source material for this crop.")
    guidance.append(TIER_GUIDANCE.get(tier, "Consider KAU's tier assessment for tailored scheme eligibility."))
    # DELIBERATELY NOT included: fabricated market-demand/price-trend claims -- no real
    # market-intelligence data source is wired into this service. See README_v2.md.
    return " ".join(guidance)


def estimated_yield_for(crop_name: str, kb: CropKnowledgeBase) -> str:
    rows = kb.crop_rows(crop_name)
    if len(rows) and rows.iloc[0].get("estimated_yield"):
        return rows.iloc[0]["estimated_yield"]
    return DEFAULT_ESTIMATED_YIELD


@app.post("/predict/crops/", response_model=RecommendationResponse)
def predict_crops(payload: RecommendationRequest) -> RecommendationResponse:
    zone = payload.agro_zone if payload.agro_zone in VALID_ZONES else None
    season = payload.season if payload.season in VALID_SEASONS else None

    # Candidate pool: crops the PoP book documents as suited to this zone (via the
    # KAU-AEZ -> service-zone crosswalk). ZONE ALONE determines eligibility -- this
    # matches your original mock's design exactly (`candidates = [c for c in CROPS
    # if payload.agro_zone in c["zones"]]`), which is also what the SRS actually
    # asks for: commodity profile is listed as one of several INPUTS to consider,
    # not a filter that removes crops from consideration.
    #
    # CHANGELOG NOTE: an earlier version of this file used `commodities` to
    # NARROW the candidate pool instead (i.e. only score crops the FPO already
    # listed). That was my own design choice, not something the SRS or the mock
    # asked for, and it had a real consequence: a farmer who hadn't already
    # registered a crop could never have it recommended, no matter how well
    # suited it was -- caught when a Wayanad FPO whose commodity list only had
    # Rice and Jack could never see Cocoa or Tea surfaced, even though both
    # score higher for that zone. Reverted to the mock's original behavior below.
    candidates = sorted(_kb.crops_in_zone(zone)) if zone else []
    if not candidates:
        candidates = [DEFAULT_CROP_NAME]

    # Resolve requested commodities for the SOFT confidence bonus below (mock's
    # `score += 0.07` for a crop the FPO already handles) -- this no longer
    # touches which crops are eligible, only how they're scored once eligible.
    resolved_requested = set()
    for c in payload.commodities:
        name = _kb.resolve_crop(c)
        if name:
            resolved_requested.add(name)

    effective_zone = zone or "coastal_zone"  # need *some* zone to fetch climate for scoring/fallback
    effective_season = season or "dry_season"
    climate = _kb.representative_climate(effective_zone, effective_season)

    # Resolve the request's free-text soil_type to one of the 6 trained soil categories.
    # If it can't be resolved (missing, or doesn't match any known category), fall back to
    # averaging the model's prediction across the zone's own soil-type mix (see README_v3.md) --
    # this is what v2 always did implicitly with a single zone-average pH; v3 only does that
    # as a fallback, and uses the real requested soil type whenever one is given.
    resolved_soil = resolve_soil_category(payload.soil_type) if payload.soil_type else None
    if resolved_soil:
        soil_categories = [resolved_soil]
        soil_note = f"Using your reported soil type ({payload.soil_type}), matched to the '{resolved_soil}' category."
    else:
        soil_categories = _kb.soil_categories_for_zone(effective_zone)
        soil_note = (f"No soil type was resolved from the request, so this averages across {effective_zone}'s "
                     f"documented soil mix: {', '.join(soil_categories)}.")

    # If the FPO gave their actual measured soil pH, use it directly instead
    # of the resolved soil category's book-documented pH-range midpoint --
    # a real measurement is a strictly better model input than a category
    # estimate. Append this to soil_note (rather than replacing it) since
    # soil_type still drives the categorical feature and reasoning text.
    reported_ph = payload.soil_ph
    if reported_ph is not None:
        soil_note += f" Using your reported soil pH ({reported_ph:g})."

    # v4: ONE feature row per soil category being considered (not one per
    # candidate crop -- crop_name isn't a feature anymore, see this module's
    # docstring), then ONE predict_proba() call returns a probability across
    # ALL known crops at once for that environment.
    feature_rows = []
    for soil_cat in soil_categories:
        if reported_ph is not None:
            soil_ph_mid = reported_ph
        else:
            ph_lo, ph_hi = _kb.soil_ph_range(soil_cat)
            soil_ph_mid = (ph_lo + ph_hi) / 2
        feature_rows.append({
            "zone": effective_zone, "soil_type": soil_cat, "season": effective_season,
            "temperature_avg_C": climate["temperature_avg_C"], "rainfall_mm": climate["rainfall_mm"],
            "humidity_pct": climate["humidity_pct"], "soil_ph_mid": soil_ph_mid,
        })
    feat_df = pd.DataFrame(feature_rows)
    proba_matrix = _model.predict_proba(feat_df[FEATURE_CATEGORICAL + FEATURE_NUMERIC])
    # average across soil categories (a no-op when only 1 row, i.e. soil was resolved)
    avg_proba = proba_matrix.mean(axis=0)
    raw_confidence_by_crop = dict(zip(_model.classes_, avg_proba))

    # The model's raw probabilities are a distribution over ALL ~149 known
    # crops, most of which aren't even documented for this zone -- so a crop
    # genuinely well suited here can still show a small-looking raw share
    # (e.g. 0.06) just because probability mass is spread across many valid
    # options for a generic environment. Restrict to this zone's documented
    # candidates and rescale so the top candidate reads as 1.0 (100% match)
    # and the rest are proportional to it -- an honest RELATIVE confidence
    # ("how strong a match is this, compared to your best option here"),
    # not a claim that the model is more or less certain in an absolute
    # sense than it actually is.
    candidate_mass = {name: raw_confidence_by_crop.get(name, 0.0) for name in candidates}
    best_mass = max(candidate_mass.values()) if candidate_mass else 0.0
    per_crop_confidence = (
        {name: v / best_mass for name, v in candidate_mass.items()} if best_mass > 0
        else dict.fromkeys(candidates, 0.0)
    )

    COMMODITY_MATCH_BONUS = 0.07  # same magnitude as the mock's score_crop() bonus

    scored = []
    for name in candidates:
        raw_confidence = per_crop_confidence[name]
        already_grown = name in resolved_requested
        confidence = raw_confidence
        if already_grown:
            confidence += COMMODITY_MATCH_BONUS
        confidence = max(0.0, min(confidence, 1.0))
        reasoning = build_reasoning(name, effective_zone, effective_season, climate, confidence, _kb, soil_note)
        if already_grown:
            reasoning += f" You already handle {name}-related commodities -- a natural fit to expand on."
        scored.append((
            confidence,
            CropRecommendationItem(
                crop=name,
                confidence=round(float(confidence), 4),
                reasoning=reasoning,
                estimated_yield=estimated_yield_for(name, _kb),
                business_guidance=build_business_guidance(name, payload.tier, _kb),
            ),
        ))

    # Full ranked list, purely by confidence descending -- no top-N cap. The FPO
    # portal now renders the complete scrollable list rather than just a top-3.
    scored.sort(key=lambda t: -t[0])
    top_results = [item for _, item in scored]

    return RecommendationResponse(
        recommendations=top_results,
        model_version=payload.model_version or SERVED_MODEL_VERSION,
    )


@app.get("/health")
def health():
    """Simple liveness check -- useful for confirming the service is up during dev."""
    return {"status": "ok", "service": "crop-recommendation-rf-v4", "model_version": SERVED_MODEL_VERSION}


# ---------------------------------------------------------------------------
# Model file management (P2-06 admin upload/activate flow) -- same mechanism
# as the mock, but /reload-model/ now actually loads the file into memory.
# ---------------------------------------------------------------------------

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
    Called by Django's MLModelVersionActivateView right after a model version
    is marked active. Loads the file, VALIDATES it against this service's
    feature schema (see validate_model_pipeline), and only then swaps it in for
    predict_crops(). If the file is missing, won't load, or doesn't fit, the
    previously-loaded model stays active and this returns HTTP 422 -- a non-2xx
    on purpose, so Django's `response.raise_for_status()` in
    MLModelVersionActivateView trips its warning path instead of reporting a
    clean activation. (Previously this returned 200 "acknowledged" even on
    failure, so Django showed success while the old model kept serving.)
    """
    global _model, SERVED_MODEL_VERSION
    full_path = ML_MODELS_DIR / payload.model_file_path
    file_exists = full_path.is_file()

    _active_model_state["version_code"] = payload.version_code
    _active_model_state["model_file_path"] = payload.model_file_path
    _active_model_state["file_exists"] = file_exists

    if not file_exists:
        _active_model_state["loaded"] = False
        logger.error("reload-model failed: file not found at %s (version_code=%s)", full_path, payload.version_code)
        raise HTTPException(status_code=422, detail={
            "note": ("File not found at the resolved shared-folder path. "
                     "Check ML_MODELS_DIR matches Django's settings.ML_MODELS_DIR."),
            "resolved_path": str(full_path),
            "problems": [],
        })

    pipe, problems, warns = load_model_checked(full_path)
    if problems:
        _active_model_state["loaded"] = False
        logger.error("reload-model rejected version_code=%s: %s", payload.version_code, " | ".join(problems))
        raise HTTPException(status_code=422, detail={
            "note": "Model file rejected; previous model remains active.",
            "resolved_path": str(full_path),
            "problems": problems,
            "warnings": warns,
        })

    previous_version = SERVED_MODEL_VERSION
    _model = pipe
    SERVED_MODEL_VERSION = payload.version_code  # /health and predict responses now report the truth
    _active_model_state["loaded"] = True
    logger.info("reload-model succeeded: %s -> %s (%s)", previous_version, payload.version_code, full_path)

    return {
        "status": "loaded",
        "version_code": payload.version_code,
        "resolved_path": str(full_path),
        "file_exists": True,
        "loaded": True,
        "warnings": warns,
        "note": "Model file validated, loaded, and now active for predict_crops().",
    }


@app.get("/model-status/")
def model_status():
    """Quick way to check what Django last told this service to activate."""
    return _active_model_state


@app.post("/reload-knowledge-base/")
def reload_knowledge_base():
    """
    Called by Django's CropZoneProfileViewSet after any create/update/delete/
    activate/deactivate that changes which rows are active -- re-reads
    crop_profiles_service_zones.csv (and the other CropKnowledgeBase files)
    from disk so an admin's edit takes effect immediately, without needing a
    full service restart (previously the only way -- see
    apps/recommendations/api/crop_zone_profile_admin.py's export_and_notify()).

    Best-effort from Django's side (it logs a warning and moves on if this
    fails or is unreachable, since the DB write already succeeded) -- but this
    endpoint itself still validates before swapping in: a malformed export
    (this service crashing on reload) is worse than continuing to serve the
    previous, working knowledge base.
    """
    global _kb
    try:
        new_kb = CropKnowledgeBase()
    except Exception as exc:  # noqa: BLE001 -- any failure here IS the finding
        logger.error("reload-knowledge-base failed: %s: %s", type(exc).__name__, exc)
        raise HTTPException(status_code=422, detail={
            "note": "Could not load the knowledge base from disk; the previous one remains active.",
            "problem": f"{type(exc).__name__}: {exc}",
        })
    _kb = new_kb
    logger.info("reload-knowledge-base succeeded: %d crops known", len(_kb.known_crop_names()))
    return {
        "status": "loaded",
        "n_crops": len(_kb.known_crop_names()),
        "note": "Knowledge base reloaded from disk and now active for predict_crops().",
    }


class ModelValidationResponse(BaseModel):
    valid: bool
    problems: list[str]
    warnings: list[str]
    expected_columns: list[str]
    detected_columns: Optional[list[str]]


@app.post("/validate-model/", response_model=ModelValidationResponse)
async def validate_model(model_file: UploadFile = File(..., description="A joblib/pickle model file")):
    """
    Called by Django's MLModelVersionAdminView (Register Model) BEFORE it saves
    the uploaded file or creates the MLModelVersion row. Answers one question:
    "can predict_crops() actually call this?" -- correct input columns, binary
    classes, predict_proba works. Always HTTP 200; the verdict is in `valid`.

    This is a structural check, not a quality check: a model can pass here and
    still be worse than the current one. Quality is what training_metrics (from
    the /train/ flow) are for -- a file-uploaded model has none, by design.

    SECURITY: joblib.load() on a pickle can execute arbitrary code. This is the
    same exposure /reload-model/ has always had -- it does not add a new one --
    but it's the reason this port must stay internal-only and the upload path
    admin-only (both already true).
    """
    contents = await model_file.read()
    if len(contents) > MAX_MODEL_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"Model file exceeds {MAX_MODEL_UPLOAD_BYTES // (1024*1024)} MB.")

    tmp_path = Path(tempfile.gettempdir()) / f"validate_model_{uuid.uuid4().hex}.joblib"
    try:
        tmp_path.write_bytes(contents)
        # Same reasoning as /train/: joblib.load + a smoke prediction are
        # blocking work, so keep them off the event loop.
        pipe, problems, warns = await run_in_threadpool(load_model_checked, tmp_path)
        detected = _detect_input_columns(pipe) if pipe is not None else None
    finally:
        tmp_path.unlink(missing_ok=True)

    return ModelValidationResponse(
        valid=not problems,
        problems=problems,
        warnings=warns,
        expected_columns=EXPECTED_MODEL_COLUMNS,
        detected_columns=detected,
    )


# ---------------------------------------------------------------------------
# Retraining from an uploaded dataset (P2-06 "retrain with more data" flow)
# ---------------------------------------------------------------------------
# This is a NEW capability, separate from /reload-model/ above. /reload-model/
# loads an ALREADY-TRAINED model file that Django's MLModelVersionAdminView
# accepted as a raw upload (per its docstring: "any file type is currently
# accepted... model files like .pkl/.joblib can execute arbitrary code when
# loaded"). /train/ below is different: it accepts a raw CSV (same shape as
# data/crop_prediction_dataset_with_commodity_codes.csv), actually RUNS the
# training pipeline here, and writes the resulting model into the same
# shared ML_MODELS_DIR your Django admin already uses -- so the two flows
# compose: Django's existing MLModelVersionAdminView.post() can call this
# endpoint instead of accepting a pre-trained file directly, then register
# the returned model_file_path as a new (inactive) MLModelVersion row exactly
# as it does today. Activation is UNCHANGED -- still a separate admin action
# via MLModelVersionActivateView, which already calls /reload-model/.
#
# This keeps a hard line between "upload data" (this endpoint: runs OUR
# training code against data you provide) and "upload a model" (the
# existing Django flow: accepts an arbitrary file and loads it with
# joblib.load(), which the existing docstring already flags as needing
# tighter access control before production) -- don't blur the two.

class DatasetValidationResponse(BaseModel):
    valid: bool
    problems: list[str]
    warnings: list[str]
    n_rows: int
    detected_format: str  # "rule_based", "pre_expanded", or "unknown" -- see retrain_pipeline._detect_dataset_format()


@app.post("/validate-dataset/", response_model=DatasetValidationResponse)
async def validate_dataset(dataset_file: UploadFile = File(...)):
    """
    Fast structural check of a training CSV -- the same checks /train/ runs
    before training, exposed on their own so Django can refuse a broken file
    immediately (missing columns -> 422) instead of queueing a Celery job that
    is guaranteed to fail. Takes milliseconds; no training happens here.

    Two CSV formats are accepted (see retrain_pipeline.py's module docstring
    and _detect_dataset_format()): the free-text rule-based KAU knowledge-base
    format, and the pre-expanded/factual format. The format is auto-detected
    from the header and reported in `detected_format`.

    `problems` = blocking (would make /train/ return 422).
    `warnings` = non-blocking (training proceeds; surfaced to the admin).
    """
    contents = await dataset_file.read()
    tmp_path = Path(tempfile.gettempdir()) / f"validate_dataset_{uuid.uuid4().hex}.csv"
    try:
        tmp_path.write_bytes(contents)
        try:
            raw = pd.read_csv(tmp_path, dtype=str, keep_default_na=False)
        except Exception as exc:  # noqa: BLE001 -- unparseable CSV is itself the finding
            return DatasetValidationResponse(
                valid=False, problems=[f"Could not parse CSV: {exc}"], warnings=[], n_rows=0, detected_format="unknown"
            )
        fmt = _detect_dataset_format(raw)
        if fmt == "unknown":
            return DatasetValidationResponse(
                valid=False,
                problems=[
                    "Could not tell which training CSV format this is from its header. This service accepts "
                    f"either the rule-based KAU knowledge-base format (columns: {REQUIRED_COLUMNS}) or the "
                    f"pre-expanded/factual format (columns: {REQUIRED_PREEXPANDED_COLUMNS}). "
                    f"Header found: {list(raw.columns)}."
                ],
                warnings=[],
                n_rows=len(raw),
                detected_format="unknown",
            )
        findings = validate_source_csv(raw) if fmt == "rule_based" else validate_preexpanded_csv(raw)
    finally:
        tmp_path.unlink(missing_ok=True)
    problems = [f for f in findings if is_blocking(f)]
    warnings_ = [f for f in findings if f not in problems]
    logger.info(
        "validate-dataset: format=%s n_rows=%d valid=%s problems=%d warnings=%d",
        fmt, len(raw), not problems, len(problems), len(warnings_),
    )
    return DatasetValidationResponse(
        valid=not problems, problems=problems, warnings=warnings_, n_rows=len(raw), detected_format=fmt
    )


class RetrainResponse(BaseModel):
    version_code: str
    model_file_path: str  # relative to ML_MODELS_DIR, same convention Django's _save_model_file() uses
    suggested_description: str
    metrics: dict
    validation_warnings: list[str]


@app.post("/train/", response_model=RetrainResponse)
async def train_from_csv(
    dataset_file: UploadFile = File(..., description="CSV in the same shape as crop_prediction_dataset_with_commodity_codes.csv"),
    version_code: Optional[str] = Form(None),
):
    """
    Accepts a CSV upload, runs the full retrain pipeline (see
    retrain_pipeline.py), and writes the resulting model + metrics into
    ML_MODELS_DIR/{version_code}/ -- the SAME shared folder and path
    convention (`{version_code}/{filename}`) Django's own
    _save_model_file() uses for manually-uploaded model files, so the
    returned model_file_path can be registered via the existing
    MLModelVersionAdminView.post() -> MLModelVersion.objects.create() path
    without any change to that model or its API contract.

    Does NOT activate the new model -- it's written to disk and its
    metrics are returned so an admin can review them (e.g. check
    leave_one_zone_out_cv and crops_with_no_positive_label before trusting
    it) and only then activate it through the existing separate endpoint,
    matching the "register, then activate" two-step flow your admin UI
    already has.
    """
    if not version_code:
        version_code = f"v-retrain-{uuid.uuid4().hex[:8]}"

    logger.info("train: starting run for version_code=%s", version_code)
    start_time = time.monotonic()
    tmp_path = Path(tempfile.gettempdir()) / f"retrain_upload_{uuid.uuid4().hex}.csv"
    try:
        contents = await dataset_file.read()
        tmp_path.write_bytes(contents)

        try:
            # run_retrain is CPU-bound and synchronous. Awaiting it in the
            # threadpool keeps the event loop free, so /predict/crops/ and
            # /health keep answering while a training run is in progress.
            # Calling it directly from this async endpoint would stall EVERY
            # other request for the whole duration of training.
            pipe, metrics, training_df = await run_in_threadpool(run_retrain, str(tmp_path))
        except DatasetValidationError as exc:
            logger.error("train failed for version_code=%s: %s", version_code, exc)
            raise HTTPException(status_code=422, detail=str(exc))

        version_dir = ML_MODELS_DIR / version_code
        version_dir.mkdir(parents=True, exist_ok=True)
        model_filename = "model.joblib"
        joblib.dump(pipe, version_dir / model_filename)
        with open(version_dir / "training_metrics.json", "w") as f:
            json.dump(metrics, f, indent=2, default=str)

        duration_s = time.monotonic() - start_time
        logger.info(
            "train: completed version_code=%s in %.1fs (n_rows=%s, n_crops=%s, accuracy=%.1f%%, format=%s)",
            version_code, duration_s, metrics.get("n_rows_total"), metrics.get("n_crops"),
            metrics.get("random_80_20_split", {}).get("accuracy", 0) * 100, metrics.get("source_format"),
        )

        return RetrainResponse(
            version_code=version_code,
            model_file_path=f"{version_code}/{model_filename}",
            suggested_description=(
                f"Retrained on uploaded dataset: {metrics['n_rows_total']} rows, "
                f"{metrics['n_crops']} crops, "
                f"{metrics['random_80_20_split']['accuracy']:.1%} accuracy (80/20 split)."
            ),
            metrics=metrics,
            validation_warnings=metrics.get("validation_warnings", []),
        )
    finally:
        tmp_path.unlink(missing_ok=True)