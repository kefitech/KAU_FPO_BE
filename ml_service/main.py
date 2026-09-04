"""
KAU-FPO Crop Recommendation Service -- trained-model version.

This is a DROP-IN REPLACEMENT for the mock `main.py` you shared: same
Pydantic request/response contract, same `/predict/crops/` endpoint path,
same `/health`, `/reload-model/`, `/model-status/` and `ML_MODELS_DIR`
mechanism -- but `predict_crops()` now actually calls a trained
RandomForestClassifier (see train_model.py) instead of the illustrative
hand-authored scoring table.

WHAT CHANGED FROM THE MOCK, CONCRETELY
---------------------------------------
- The static `CROPS` list (10 crops, hand-authored zones/soil_keywords/
  base_confidence) is replaced by:
    (a) a real 149-crop knowledge base extracted from KAU's Package of
        Practices 2024 book (data/crop_prediction_dataset_with_commodity_codes.csv),
        used to resolve `commodities` -> crop names and to source
        `estimated_yield` / variety-based reasoning text, and
    (b) a RandomForestClassifier trained on real Kerala climate (6 towns,
        IMD-sourced normals) matched against each crop's PoP-stated
        temperature/pH/season requirements (see train_model.py,
        model/training_metrics_v2.json). `confidence` is the model's
        predict_proba(is_suitable) for that crop/zone/season combination.
- Zone eligibility ("candidates") now comes from which crops the PoP book
  actually documents as suited to that zone (via the KAU-AEZ -> this
  service's zone crosswalk in build_v2.py), not a 10-crop hand list -- so
  many more crops can appear, not just the mock's original 10. If a
  request's zone/commodities don't resolve to anything the book documents,
  behavior falls back the same way the mock did (DEFAULT_CROP).

HONESTY NOTE (carried over from the whole project): `is_suitable` in
training was RULE-DERIVED (real climate checked against PoP-stated crop
requirements, cross-walked from KAU's 5 physiographic zones onto this
service's 5 geographic zones), not an observed real planting outcome.
Treat `confidence` as "how well this crop's documented requirements match
this zone/season's typical climate," not a market-validated success
probability. See model/training_metrics_v2.json for accuracy figures,
including the leave-one-zone-out cross-validation (the honest
generalization estimate).

Run:
    pip install -r requirements.txt
    uvicorn main:app --reload --port 8001
"""
import json
import os
import tempfile
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
from retrain_pipeline import run_retrain, validate_source_csv, DatasetValidationError

# Load the SAME .env file Django reads (config('ML_MODELS_DIR', ...) in
# config/settings/base.py), so both services agree on ML_MODELS_DIR from one
# place instead of each computing its own default and hoping they match.
# This assumes ml_service/ sits directly inside the Django project root
# (KAU_FPO_BE/) -- adjust the parent count below if your layout differs.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

app = FastAPI(title="KAU-FPO Crop Recommendation Service")

SERVED_MODEL_VERSION = "v3.3.0-rf-poc"  # updated at runtime by /reload-model/ on a successful swap

MODEL_PATH = "model/crop_suitability_rf_v3.joblib"
# NOTE: elevation_m dropped vs v2 -- it was fully determined by zone (near-zero
# importance, pure duplicate signal). soil_type is now a real categorical
# resolved from the request, not a zone-average pH number. See README_v3.md.
CATEGORICAL = ["zone", "soil_type", "season", "crop_name", "crop_group"]
NUMERIC = ["temperature_avg_C", "rainfall_mm", "humidity_pct", "soil_ph_mid"]

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

EXPECTED_MODEL_COLUMNS = CATEGORICAL + NUMERIC


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

    classes = getattr(pipe, "classes_", None)
    if classes is not None and list(classes) != [0, 1]:
        problems.append(
            f"Model classes_ are {list(classes)}; this service reads predict_proba()[:, 1] as "
            "P(suitable) and requires classes exactly [0, 1]."
        )

    # Smoke prediction with one plausible row -- catches anything the structural
    # checks above can't see (broken pickle internals, wrong step order, etc).
    if not problems:
        smoke = pd.DataFrame([{
            "zone": "coastal_zone", "soil_type": "Laterite", "season": "dry_season",
            "crop_name": DEFAULT_CROP_NAME, "crop_group": "Cereals",
            "temperature_avg_C": 28.0, "rainfall_mm": 100.0, "humidity_pct": 75.0, "soil_ph_mid": 6.0,
        }])
        try:
            proba = pipe.predict_proba(smoke[EXPECTED_MODEL_COLUMNS])
            if getattr(proba, "shape", None) != (1, 2):
                problems.append(f"Smoke prediction returned shape {getattr(proba, 'shape', None)}, expected (1, 2).")
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
        print(f"[startup] model warning: {w}")
    if problems:
        # Refuse to start rather than come up "healthy" and 500 on the first
        # real prediction. The message names the exact mismatch.
        raise RuntimeError(
            f"Default model at {MODEL_PATH} is not compatible with this service: " + " | ".join(problems)
        )
    _model = pipe
    _kb = CropKnowledgeBase()


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

    crop_groups = {}
    for name in candidates:
        rows = _kb.crop_rows(name)
        crop_groups[name] = rows.iloc[0]["crop_group"] if len(rows) else "Unknown"

    feature_rows = []
    for name in candidates:
        for soil_cat in soil_categories:
            ph_lo, ph_hi = _kb.soil_ph_range(soil_cat)
            feature_rows.append({
                "crop_name": name, "soil_category": soil_cat,
                "zone": effective_zone, "soil_type": soil_cat, "season": effective_season,
                "crop_group": crop_groups[name],
                "temperature_avg_C": climate["temperature_avg_C"], "rainfall_mm": climate["rainfall_mm"],
                "humidity_pct": climate["humidity_pct"], "soil_ph_mid": (ph_lo + ph_hi) / 2,
            })
    feat_df = pd.DataFrame(feature_rows)
    feat_df["confidence"] = _model.predict_proba(feat_df[CATEGORICAL + NUMERIC])[:, 1]
    # average across soil categories per crop (a no-op when only 1 category, i.e. soil was resolved)
    per_crop_confidence = feat_df.groupby("crop_name")["confidence"].mean().to_dict()

    COMMODITY_MATCH_BONUS = 0.07  # same magnitude as the mock's score_crop() bonus

    scored = []
    for name in candidates:
        raw_confidence = per_crop_confidence[name]
        already_grown = name in resolved_requested
        confidence = raw_confidence + COMMODITY_MATCH_BONUS if already_grown else raw_confidence
        confidence = max(0.0, min(confidence, 1.0))
        reasoning = build_reasoning(name, effective_zone, effective_season, climate, confidence, _kb, soil_note)
        if already_grown:
            reasoning += f" You already handle {name}-related commodities -- a natural fit to expand on."
        scored.append((
            _kb.is_zone_specific(name, effective_zone),
            confidence,
            CropRecommendationItem(
                crop=name,
                confidence=round(float(confidence), 4),
                reasoning=reasoning,
                estimated_yield=estimated_yield_for(name, _kb),
                business_guidance=build_business_guidance(name, payload.tier, _kb),
            ),
        ))

    # Rank crops the PoP book actually documents for THIS zone (via a real KAU-zone
    # crosswalk, e.g. Coffee/Cardamom/Tea -> High Hills -> high_ranges) above crops
    # that only appear here via the 'General (all zones)' catch-all (~78% of the
    # 149-crop dataset, covering crops the book never localizes -- mostly common
    # vegetables/spices). Without this, a middling-confidence generic crop like
    # Cocoa can outrank a genuinely zone-documented specialty like Coffee or
    # Cardamom just because 'General' crops tend to have wide temperature/season
    # tolerances that clear the suitability bar easily. See data_access_v3.py's
    # is_zone_specific() and README_v3.md. This now ALWAYS applies (previously it
    # was skipped whenever commodities were named -- no longer needed, since
    # commodities no longer redefine the candidate pool, they only nudge scores
    # within it).
    scored.sort(key=lambda t: (not t[0], -t[1]))
    top_results = [item for _, _, item in scored[:3]]

    return RecommendationResponse(
        recommendations=top_results,
        model_version=payload.model_version or SERVED_MODEL_VERSION,
    )


@app.get("/health")
def health():
    """Simple liveness check -- useful for confirming the service is up during dev."""
    return {"status": "ok", "service": "crop-recommendation-rf-v3", "model_version": SERVED_MODEL_VERSION}


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
        raise HTTPException(status_code=422, detail={
            "note": ("File not found at the resolved shared-folder path. "
                     "Check ML_MODELS_DIR matches Django's settings.ML_MODELS_DIR."),
            "resolved_path": str(full_path),
            "problems": [],
        })

    pipe, problems, warns = load_model_checked(full_path)
    if problems:
        _active_model_state["loaded"] = False
        raise HTTPException(status_code=422, detail={
            "note": "Model file rejected; previous model remains active.",
            "resolved_path": str(full_path),
            "problems": problems,
            "warnings": warns,
        })

    _model = pipe
    SERVED_MODEL_VERSION = payload.version_code  # /health and predict responses now report the truth
    _active_model_state["loaded"] = True

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


@app.post("/validate-dataset/", response_model=DatasetValidationResponse)
async def validate_dataset(dataset_file: UploadFile = File(...)):
    """
    Fast structural check of a training CSV -- the same checks /train/ runs
    before training, exposed on their own so Django can refuse a broken file
    immediately (missing columns -> 422) instead of queueing a Celery job that
    is guaranteed to fail. Takes milliseconds; no training happens here.

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
            return DatasetValidationResponse(valid=False, problems=[f"Could not parse CSV: {exc}"], warnings=[], n_rows=0)
        findings = validate_source_csv(raw)
    finally:
        tmp_path.unlink(missing_ok=True)
    problems = [f for f in findings if f.startswith("Missing required columns")]
    warnings_ = [f for f in findings if f not in problems]
    return DatasetValidationResponse(valid=not problems, problems=problems, warnings=warnings_, n_rows=len(raw))


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
            raise HTTPException(status_code=422, detail=str(exc))

        version_dir = ML_MODELS_DIR / version_code
        version_dir.mkdir(parents=True, exist_ok=True)
        model_filename = "model.joblib"
        joblib.dump(pipe, version_dir / model_filename)
        with open(version_dir / "training_metrics.json", "w") as f:
            json.dump(metrics, f, indent=2, default=str)

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