# ML Service — current state

FastAPI service (`main.py`) that predicts which crops suit a given environment for KAU-FPO's recommendation feature, and trains/retrains that model from CSV uploads (`retrain_pipeline.py`).

## Model: multiclass, environment → crop

The model is a `RandomForestClassifier` where `crop_name` is the predicted TARGET, never an input feature. Inputs are purely environmental:

- **Categorical**: `zone` (5 service zones), `soil_type` (6 categories, `data/soil_type_reference.csv`), `season` (3 values)
- **Numeric**: `temperature_avg_C`, `rainfall_mm`, `humidity_pct`, `soil_ph_mid`

`predict_crops()` in `main.py` builds one feature row from the request's resolved environment and calls `predict_proba()` once, returning a ranked probability across every known crop. `crop_name` is deliberately excluded from the inputs so the model can't shortcut through crop identity — an earlier binary-classifier design that did include it let `crop_name` dominate with 30.8% feature importance (more than double any other feature), which meant a handful of broadly-documented crops (Rice, Cashew, Anthurium) topped every zone's recommendations almost regardless of actual conditions.

## Training data: two accepted CSV formats

`retrain_pipeline.py`'s `run_retrain()` auto-detects which format an uploaded CSV is (`_detect_dataset_format()`):

- **Pre-expanded** (`REQUIRED_PREEXPANDED_COLUMNS`: `zone, soil_type, season, crop_name, temperature_avg_C, rainfall_mm, humidity_pct, soil_ph_mid, is_suitable`) — each row is already a real training example. `data/grounded_training_dataset_v5.csv` is the current best version of this (see below); `data/sample_retrain_dataset.csv` is a small illustrative template of the shape.
- **Rule-based** (`REQUIRED_COLUMNS`: `crop_name, crop_group, commodity_code, commodity_en, commodity_section, soil_type, soil_ph_range, season, agro_zone, temperature_range, variety_recommendations, estimated_yield`) — free text parsed from the KAU PoP crosswalk (`data/crop_prediction_dataset_with_commodity_codes.csv`) and expanded into training rows through 3 stages (parse bounds → aggregate per crop/zone → expand to service zones + build rows). This is how `grounded_training_dataset_v5.csv` was generated.

Both formats feed the same `_train()` function once expanded to the pre-expanded shape.

## Evaluation: `accuracy` will look low — that's expected, use `top_5_hit_rate`

Many `(zone, soil_type, season)` environments have dozens of crops genuinely valid at once (~87 on average, across only 30 unique environment combinations) — but a random train/test split holds out only one crop_name per row. `accuracy` (strict single-label match) penalizes the model for ranking a *different*, equally-valid crop above the one specific row that happened to land in the test split, so it's structurally incapable of reaching a high number even for a model that's working correctly.

`top_5_hit_rate` is the metric that reflects real quality: it checks whether the model's top-5 predictions fall within the FULL set of crops the source data marks valid for that environment (`_top_k_hit_rate()` in `retrain_pipeline.py`), not just the one held-out label. Currently 100% on `grounded_training_dataset_v5.csv`, including all 5 leave-one-zone-out folds.

## Current best dataset: `grounded_training_dataset_v5.csv`

Each crop's own documented pH range and temperature range (parsed from the PoP-crosswalk CSV's free text) now feed `soil_ph_mid` and `temperature_avg_C` directly, instead of a soil-category/zone-climate constant shared by every crop in a bucket — these were being parsed correctly in stage 1 and then silently discarded in stage 3 until fixed. `is_suitable` labels are unchanged; this only fixes what numeric signal the model gets to learn from.

| | dominant feature | accuracy (exact match) | top-5 hit rate |
|---|---|---|---|
| `grounded_training_dataset_v3.csv` (original) | temperature (24.7%) | 0.0% | 100%* |
| `grounded_training_dataset_v4.csv` (pH fix only) | `soil_ph_mid` (59.4%) | 1.8% | 100% |
| `grounded_training_dataset_v5.csv` (pH + temperature fix) | balanced: temp 37.0%, pH 35.1%, rest ~5% each | 16.6% | 100% |

*v3's 100% was hollow — with zero per-crop signal in the features, there was nothing for the model to get wrong.

Real-prediction spot check (using the same feature construction `predict_crops()` uses at inference — zone's real climate + soil category's book pH, not any crop's own value): `high_ranges` + acidic forest-loam soil + `southwest_monsoon` correctly surfaces **Tea and Cardamom** at the top — Idukki's high ranges is Kerala's actual tea-and-cardamom belt.

**Why accuracy won't easily clear ~20%, and what it would take**: only 24 of 179 crop-zone profiles (13%) have a real parsed pH value, 36 (20%) a real temperature, and 131 (73%) have neither — for those, the source CSV's `soil_ph_range`/`temperature_range` text is blank or non-numeric (often elevation/rainfall figures instead), confirmed by inspecting the raw text directly, not a parsing bug. Crops sharing a `crop_group` fallback are genuinely indistinguishable to any model, because the source data doesn't distinguish them either. Pushing higher requires filling in real pH/temperature/rainfall figures from the KAU PoP book for those 131 profiles — data entry, not further modeling.

`grounded_training_dataset_v5.csv` is not yet registered/activated as of this writing.

## Model storage: local disk today, no durable volume in the test deploy

Trained/registered model files are written to `ML_MODELS_DIR/{version_code}/model.joblib` (plus `training_metrics.json`, and `dataset.csv` for CSV retrains) — plain local disk, both this service and Django reading/writing the same path directly (`os.environ["ML_MODELS_DIR"]` here, `settings.ML_MODELS_DIR` in Django). See `main.py`'s `/train/`, `/reload-model/`, `/validate-model/` and Django's `MLModelVersionAdminView`/`MLModelRetrainView`/`retrain_model_task`.

On the deployed test server, `docker-compose.yml` declares no volume for `ML_MODELS_DIR` on the `web`/`celery` containers (only `media_files`, `static_files`, `logs` are mounted) — so unless `.env` there points `ML_MODELS_DIR` at a bind-mounted host path outside the containers, every registered model version is lost on the next rebuild/redeploy.

### TODO: move model storage to S3 (not yet done)

Would touch: `main.py`'s `/train/` (upload instead of/after local `joblib.dump`), `/reload-model/` and `/validate-model/` (load from S3 instead of a local path); Django's `_save_model_file()` and `MLModelRetrainView`'s CSV save; `retrain_model_task`'s shared-filesystem assumption (same "two processes must see the same file" issue this whole section is about); `MLModelVersion.model_file_path`'s shape (full S3 key/URI, or a relative key + shared bucket/prefix setting); a new `boto3`(-like) dependency + AWS credentials/bucket config; and a deliberate decision on whether ml_service caches the active model locally or always loads from S3, since `/predict/crops/` calls `predict_proba()` per request and shouldn't take on network latency per call.
