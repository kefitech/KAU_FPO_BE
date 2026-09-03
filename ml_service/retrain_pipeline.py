"""
End-to-end retrain pipeline: raw PoP-crosswalk CSV -> trained model.

This consolidates three stages that, up to now, lived in separate one-off
scripts run by hand across this project (augment.py's regex parsing ->
build_grounded.py's per-crop-zone aggregation -> tailor_dataset_v3.py's
service-zone expansion -> train_model_v3.py's training). A CSV upload
endpoint needs all of that to run automatically end to end, so this module
wraps each stage as an importable function and exposes ONE entry point,
`run_retrain()`, that main.py's upload endpoint calls.

Nothing about the MODEL or the LABEL RULE changed here -- this is a
refactor of existing logic into reusable functions, not a new approach.
See tailor_dataset_v3.py's and train_model_v3.py's docstrings for what the
label rule and features actually are; the same rules are applied here.

REQUIRED INPUT CSV COLUMNS (same as data/crop_prediction_dataset_with_commodity_codes.csv):
    crop_name, crop_group, commodity_code, commodity_en, commodity_section,
    soil_type, soil_ph_range, season, agro_zone, temperature_range,
    variety_recommendations, estimated_yield

REQUIRED agro_zone VALUES (exact strings -- anything else is silently
dropped by the KAU-zone -> service-zone crosswalk, so this is validated
up front rather than failing silently deep in the pipeline):
    'Coastal Plain', 'Midland Laterites', 'Foothills', 'High Hills',
    'Palakkad Plain', 'General (all zones)'
"""
import re
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split, GroupKFold
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (accuracy_score, precision_score, recall_score, f1_score,
                              roc_auc_score, confusion_matrix)

REQUIRED_COLUMNS = [
    "crop_name", "crop_group", "commodity_code", "commodity_en", "commodity_section",
    "soil_type", "soil_ph_range", "season", "agro_zone", "temperature_range",
    "variety_recommendations", "estimated_yield",
]
VALID_KAU_ZONES = {"Coastal Plain", "Midland Laterites", "Foothills", "High Hills",
                   "Palakkad Plain", "General (all zones)"}

CLIMATE_PATH = "data/zone_climate_real.csv"  # real climate per service zone/month -- not crop data, reused as-is

KAU_TO_SERVICE_ZONE = {
    'Coastal Plain': ['coastal_zone'],
    'High Hills': ['high_ranges'],
    'Midland Laterites': ['northern_zone', 'central_zone', 'southern_zone'],
    'Foothills': ['northern_zone', 'central_zone', 'southern_zone'],
    'Palakkad Plain': ['central_zone'],
    'General (all zones)': ['coastal_zone', 'southern_zone', 'central_zone', 'northern_zone', 'high_ranges'],
}
SOIL_PH = {
    "Coastal sandy / laterite patches": (5.5, 7.0),
    "Coastal alluvium / sandy, backwater-adjacent": (5.5, 7.5),
    "Laterite": (4.5, 6.0),
    "Lateritic loam (transitional)": (4.8, 6.3),
    "Black soil (Chittoor black soil) / red loam": (6.5, 8.5),
    "Forest loam / hill soil (acidic, high organic matter)": (4.5, 6.0),
}
ZONE_SOIL_TYPES = {
    "coastal_zone": ["Coastal sandy / laterite patches", "Coastal alluvium / sandy, backwater-adjacent"],
    "southern_zone": ["Laterite", "Lateritic loam (transitional)"],
    "central_zone": ["Laterite", "Black soil (Chittoor black soil) / red loam"],
    "northern_zone": ["Laterite", "Forest loam / hill soil (acidic, high organic matter)"],
    "high_ranges": ["Forest loam / hill soil (acidic, high organic matter)", "Lateritic loam (transitional)"],
}
SOIL_KEYWORDS = {
    "Coastal sandy / laterite patches": ["coastal sand", "onattukara", "light coastal sand", "coastal saline"],
    "Coastal alluvium / sandy, backwater-adjacent": ["alluvial", "alluvium", "backwater", "kuttanad", "reclaimed",
                                                      "marshy", "kaipad", "pokkali", "riverine"],
    "Laterite": ["laterite", "lateritic"],
    "Lateritic loam (transitional)": ["lateritic loam", "lateritic gravelly", "gravelly", "midland soils"],
    "Black soil (Chittoor black soil) / red loam": ["black soil", "black cotton", "chittoor", "red loam", "black loam"],
    "Forest loam / hill soil (acidic, high organic matter)": ["forest loam", "hill soil", "humus", "high ranges", "high-range"],
}
UNIVERSAL_SOIL_PHRASES = ["wide range of soils", "wide variety of soils", "almost all soil types",
                          "various soils", "all types of soils", "adapted to almost all"]
SEASON_SYNONYMS = {
    "southwest_monsoon": ["virippu", "kharif", "autumn", "monsoon", "first crop", "i crop",
                           "rainfed", "south-west monsoon", "sw monsoon", "june", "july", "august"],
    "northeast_monsoon": ["mundakan", "rabi", "second crop", "ii crop", "north-east monsoon",
                           "ne monsoon", "october", "november", "winter"],
    "dry_season": ["puncha", "zaid", "summer", "third crop", "iii crop", "dry season",
                   "irrigated", "january", "february", "march", "april", "may"],
}
ZONE_TEMP_DEFAULTS = {  # only used when a row states no numeric temperature at all (see parse_temp)
    'Coastal Plain': (24, 33), 'Midland Laterites': (23, 32), 'Foothills': (20, 30),
    'High Hills': (12, 25), 'Palakkad Plain': (24, 36), 'General (all zones)': (22, 32),
}
GLOBAL_PH_DEFAULT = (5.0, 6.5)

CATEGORICAL = ["zone", "soil_type", "season", "crop_name", "crop_group"]
NUMERIC = ["temperature_avg_C", "rainfall_mm", "humidity_pct", "soil_ph_mid"]


class DatasetValidationError(ValueError):
    """Raised when the uploaded CSV can't be safely turned into training data.
    Caught by main.py's upload endpoint and returned as a 422 with details,
    instead of failing opaquely partway through the pipeline."""


def validate_source_csv(df: pd.DataFrame) -> list[str]:
    """Returns a list of human-readable problems (empty list = OK to proceed).
    Checks structure, not content quality -- e.g. it won't catch a crop with
    an implausible pH, only a missing column or an unrecognized zone value."""
    problems = []
    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        problems.append(f"Missing required columns: {missing_cols}")
        return problems  # can't check anything else meaningfully without these
    if df["crop_name"].isna().any() or (df["crop_name"].astype(str).str.strip() == "").any():
        problems.append("Some rows have a blank crop_name.")
    unknown_zones = sorted(set(df["agro_zone"].dropna().unique()) - VALID_KAU_ZONES)
    if unknown_zones:
        problems.append(
            f"Unrecognized agro_zone value(s): {unknown_zones}. Must be one of {sorted(VALID_KAU_ZONES)}. "
            f"Rows with an unrecognized zone will not crosswalk into ANY service zone and will be silently "
            f"dropped from training -- fix these before uploading, don't rely on this pipeline to catch them."
        )
    if len(df) < 20:
        problems.append(f"Only {len(df)} rows -- suspiciously small for a full crop dataset, double check the file.")
    return problems


# ---------------- stage 1: parse free-text ranges into numeric bounds (was augment.py) ----------------

def _parse_ph(text):
    if not text:
        return None
    pairs = re.findall(r'(\d\.\d)\s*[-–to]+\s*(\d\.\d)', text)
    if pairs:
        vals = [float(x) for p in pairs for x in p]
        return (min(vals), max(vals))
    singles = re.findall(r'(\d\.\d)', text)
    if singles:
        v = [float(x) for x in singles]
        return (min(v) - 0.3, max(v) + 0.3)
    return None


def _parse_temp(text):
    if not text:
        return None
    pairs = re.findall(r'(\d{1,2})\s*[-–]\s*(\d{1,2})\s*(?:°|deg)?\s*C', text)
    pairs = [(float(a), float(b)) for a, b in pairs if 0 < float(a) < 50 and 0 < float(b) < 50]
    singles_raw = re.findall(r'(\d{1,2})\s*(?:°|deg(?:rees)?)?\s*C\b', text)
    singles = [float(x) for x in singles_raw if 0 < float(x) < 50]
    all_vals = [v for p in pairs for v in p] + singles
    if not all_vals:
        return None
    lo, hi = min(all_vals), max(all_vals)
    if lo == hi:
        return (lo - 4, hi + 4)
    return (lo, hi)


def _stage1_parse_bounds(raw: pd.DataFrame) -> pd.DataFrame:
    ph_by_row = raw["soil_ph_range"].apply(_parse_ph)
    tmp = raw.copy()
    tmp["_ph_lo"] = ph_by_row.apply(lambda x: x[0] if x else np.nan)
    tmp["_ph_hi"] = ph_by_row.apply(lambda x: x[1] if x else np.nan)
    group_ph = tmp.groupby("crop_group")[["_ph_lo", "_ph_hi"]].median()

    def ph_fallback(group):
        if group in group_ph.index and not group_ph.loc[group].isna().any():
            return tuple(group_ph.loc[group])
        return GLOBAL_PH_DEFAULT

    rows = []
    for _, r in raw.iterrows():
        zone = r["agro_zone"] if r["agro_zone"] in ZONE_TEMP_DEFAULTS else "General (all zones)"
        ph = _parse_ph(r["soil_ph_range"])
        ph_src = "pop_text"
        if ph is None:
            ph = ph_fallback(r["crop_group"])
            ph_src = "crop_group_median" if ph != GLOBAL_PH_DEFAULT else "global_default"
        temp = _parse_temp(r["temperature_range"])
        temp_src = "pop_text"
        if temp is None:
            temp = ZONE_TEMP_DEFAULTS[zone]
            temp_src = "zone_default"
        rows.append({
            "crop_name": r["crop_name"], "crop_group": r["crop_group"], "agro_zone": r["agro_zone"],
            "season": r["season"], "soil_type_text": r["soil_type"],
            "ph_lo": ph[0], "ph_hi": ph[1], "ph_src": ph_src,
            "temp_lo": temp[0], "temp_hi": temp[1], "temp_src": temp_src,
        })
    return pd.DataFrame(rows)


# ---------------- stage 2: aggregate to one profile per (crop, KAU zone) (was build_grounded.py) ----------------

def _stage2_aggregate_profiles(bounds: pd.DataFrame) -> pd.DataFrame:
    def agg(grp):
        return pd.Series({
            "crop_group": grp["crop_group"].iloc[0],
            "temp_lo": grp["temp_lo"].min(), "temp_hi": grp["temp_hi"].max(),
            "ph_lo": grp["ph_lo"].min(), "ph_hi": grp["ph_hi"].max(),
            "seasons_text": " | ".join(grp["season"].fillna("").astype(str)),
            "soil_text": " | ".join(t for t in grp["soil_type_text"].fillna("").astype(str) if t.strip()),
            "ph_is_real": (grp["ph_src"] == "pop_text").any(),
            "temp_is_real": (grp["temp_src"] == "pop_text").any(),
        })
    return bounds.groupby(["crop_name", "agro_zone"]).apply(agg).reset_index()


# ---------------- stage 3: expand to service zones + build training rows (was tailor_dataset_v3.py) ----------------

def _safe_str(x) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return ""
    return str(x)


def _soil_match(crop_soil_text, category: str) -> bool:
    text = _safe_str(crop_soil_text).lower()
    if not text.strip():
        return True
    if any(p in text for p in UNIVERSAL_SOIL_PHRASES):
        return True
    return any(kw in text for kw in SOIL_KEYWORDS[category])


def _season_match(service_season: str, seasons_text) -> bool:
    text = _safe_str(seasons_text).lower()
    if not text.strip():
        return True
    return any(syn in text for syn in SEASON_SYNONYMS[service_season])


def _stage3_build_training_rows(profiles: pd.DataFrame, climate: pd.DataFrame) -> pd.DataFrame:
    expanded = []
    for _, row in profiles.iterrows():
        kau_zone = row["agro_zone"]
        for sz in KAU_TO_SERVICE_ZONE.get(kau_zone, []):
            expanded.append({**row.to_dict(), "service_zone": sz, "kau_zone_source": kau_zone})
    profiles_expanded = pd.DataFrame(expanded)

    rows = []
    for _, zc in climate.iterrows():
        zone, month, season = zc["zone"], zc["month"], zc["season"]
        cand = profiles_expanded[profiles_expanded["service_zone"] == zone]
        for soil_category in ZONE_SOIL_TYPES[zone]:
            ph_lo_zone, ph_hi_zone = SOIL_PH[soil_category]
            soil_ph_mid = (ph_lo_zone + ph_hi_zone) / 2
            for _, cr in cand.iterrows():
                temp_ok = not (zc["temperature_avg_C"] < cr["temp_lo"] - 2 or zc["temperature_avg_C"] > cr["temp_hi"] + 2)
                season_ok = _season_match(season, cr["seasons_text"])
                soilkw_ok = _soil_match(cr["soil_text"], soil_category)
                is_suitable = int(temp_ok and (season_ok or soilkw_ok))
                rows.append({
                    "zone": zone, "month": month, "season": season, "soil_type": soil_category,
                    "soil_ph_mid": soil_ph_mid,
                    "temperature_avg_C": zc["temperature_avg_C"], "rainfall_mm": zc["rainfall_mm"],
                    "humidity_pct": zc["humidity_pct"],
                    "crop_name": cr["crop_name"], "crop_group": cr["crop_group"],
                    "kau_zone_source": cr["kau_zone_source"],
                    "is_suitable": is_suitable,
                })
    return pd.DataFrame(rows)


# ---------------- stage 4: train (was train_model_v3.py) ----------------

def _build_pipeline():
    pre = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
        ("num", "passthrough", NUMERIC),
    ])
    clf = RandomForestClassifier(n_estimators=300, max_depth=12, min_samples_leaf=3,
                                  class_weight="balanced", random_state=42, n_jobs=-1)
    return Pipeline([("pre", pre), ("clf", clf)])


def _train(df: pd.DataFrame):
    X = df[CATEGORICAL + NUMERIC]
    y = df["is_suitable"]

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    pipe = _build_pipeline()
    pipe.fit(X_train, y_train)
    y_pred = pipe.predict(X_test)
    y_proba = pipe.predict_proba(X_test)[:, 1]
    random_split_metrics = {
        "accuracy": accuracy_score(y_test, y_pred), "precision": precision_score(y_test, y_pred),
        "recall": recall_score(y_test, y_pred), "f1": f1_score(y_test, y_pred),
        "roc_auc": roc_auc_score(y_test, y_proba),
        "confusion_matrix": confusion_matrix(y_test, y_pred).tolist(),
        "n_train": len(X_train), "n_test": len(X_test),
    }

    logo_scores = []
    if df["zone"].nunique() > 1:
        gkf = GroupKFold(n_splits=df["zone"].nunique())
        for train_idx, test_idx in gkf.split(X, y, groups=df["zone"]):
            p = _build_pipeline()
            p.fit(X.iloc[train_idx], y.iloc[train_idx])
            held_out = df["zone"].iloc[test_idx].iloc[0]
            pred = p.predict(X.iloc[test_idx])
            logo_scores.append({
                "held_out_zone": str(held_out),
                "accuracy": accuracy_score(y.iloc[test_idx], pred),
                "f1": f1_score(y.iloc[test_idx], pred, zero_division=0),
                "n_test": len(test_idx),
            })

    final_pipe = _build_pipeline()
    final_pipe.fit(X, y)
    ohe = final_pipe.named_steps["pre"].named_transformers_["cat"]
    cat_names = list(ohe.get_feature_names_out(CATEGORICAL))
    importances = final_pipe.named_steps["clf"].feature_importances_
    importance_by_field = {}
    for name, imp in zip(cat_names + NUMERIC, importances):
        field = name if name in NUMERIC else next((c for c in CATEGORICAL if name.startswith(c + "_")), name)
        importance_by_field[field] = importance_by_field.get(field, 0) + float(imp)

    metrics = {
        "random_80_20_split": random_split_metrics,
        "leave_one_zone_out_cv": logo_scores,
        "feature_importance_by_field": dict(sorted(importance_by_field.items(), key=lambda x: -x[1])),
        "n_rows_total": len(df), "n_crops": df["crop_name"].nunique(),
        "crops_with_no_positive_label": int(df.groupby("crop_name")["is_suitable"].max().eq(0).sum()),
        "class_balance": {str(k): v for k, v in y.value_counts(normalize=True).to_dict().items()},
        "caveat": ("Label is rule-derived (PoP crop requirements matched against real zone climate and a "
                   "documented-approximation soil-type-per-zone mix); a crop is 'suitable' if temperature "
                   "matches AND (season matches OR soil matches). Not an observed real-world outcome."),
    }
    return final_pipe, metrics


# ---------------- entry point ----------------

def run_retrain(source_csv_path: str, climate_path: str = CLIMATE_PATH):
    """Runs all 4 stages. Returns (fitted_pipeline, metrics_dict, training_df).
    Raises DatasetValidationError if the input CSV fails structural checks --
    callers should catch this and surface it as a 4xx, not a 500."""
    raw = pd.read_csv(source_csv_path, dtype=str, keep_default_na=False)
    problems = validate_source_csv(raw)
    blocking = [p for p in problems if p.startswith("Missing required columns")]
    if blocking:
        raise DatasetValidationError("; ".join(problems))

    # numeric columns that came in as strings (dtype=str above, to preserve exact zone-name text)
    bounds = _stage1_parse_bounds(raw)
    profiles = _stage2_aggregate_profiles(bounds)
    climate = pd.read_csv(climate_path)
    training_df = _stage3_build_training_rows(profiles, climate)

    if training_df.empty or training_df["crop_name"].nunique() == 0:
        raise DatasetValidationError(
            "No trainable rows were produced -- every row's agro_zone likely failed to crosswalk into a "
            "service zone. Check agro_zone values against the required list."
        )

    pipe, metrics = _train(training_df)
    metrics["validation_warnings"] = problems  # non-blocking issues, still worth surfacing
    return pipe, metrics, training_df
