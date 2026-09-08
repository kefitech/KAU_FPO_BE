# Tailoring the dataset based on the trained model (v2 → v3)

You asked to tailor the dataset based on what the model showed. The v2 model's `training_metrics_v2.json` exposed two concrete issues, and this round fixes both:

1. **`zone` (0.9%) and `soil_ph_mid` (0.4%) were nearly useless features.** v2 gave each of the 5 service zones exactly one representative pH range, so soil never varied independently of zone — nothing zone/soil-specific for the model to learn.
2. **`elevation_m` (0.5% importance) was pure noise.** It's fully determined by zone (one fixed value per zone in the climate table), so it was really just a duplicate encoding of zone that added nothing.

## What changed

**Real soil-type variation, within each zone.** Each of the 5 zones now has 2 plausible soil types (`data/soil_type_reference.csv`), drawn from general Kerala pedology and deliberately overlapping across zones — Laterite appears in 3 zones, Forest loam and Lateritic loam each in 2 — so soil carries information independent of which zone it's in:

| Zone | Soil types |
|---|---|
| coastal_zone | Coastal sandy / laterite patches, Coastal alluvium / sandy |
| southern_zone | Laterite, Lateritic loam (transitional) |
| central_zone | Laterite, Black soil (Chittoor) / red loam |
| northern_zone | Laterite, Forest loam / hill soil |
| high_ranges | Forest loam / hill soil, Lateritic loam (transitional) |

Each crop's actual PoP-book soil description (free text, e.g. "forest loam soils rich in phosphorus... raised on soils rich in humus" for Cardamom) is keyword-matched against each zone's soil types, so a crop can be suitable in one zone's soil and not another zone's — a real soil-specific signal, not a zone-wide constant. See `tailor_dataset_v3.py` for the full keyword dictionary and the label rule (a crop counts as suitable when temperature matches AND (season matches OR soil matches) — pH was dropped as a gating condition once we confirmed it was true for ~100% of rows at these zone-level pH widths and would have just diluted the new soil signal).

**`elevation_m` removed from the trained feature set.** `CATEGORICAL`/`NUMERIC` in `train_model_v3.py` no longer include it.

**`main.py` now actually uses the request's `soil_type` field.** v2 accepted it but never used it in scoring (a known placeholder gap flagged in `README_v2.md`). v3 resolves the free text (e.g. `"sandy"`, `"lateritic loam"`) to one of the 6 trained soil categories and feeds it into the model; if it can't resolve one, it falls back to averaging the prediction across the zone's own two soil types (what v2 always implicitly did).

## Result: did it work?

Yes, measurably — feature importance:

| Feature | v2 | v3 |
|---|---|---|
| zone | 0.9% | **12.6%** |
| soil_type + soil_ph_mid | 0.4% | **5.7%** |
| crop_name + crop_group | 77.5% | 53.6% |
| season | 16.2% | 6.6% |
| climate (temp/rain/humidity) | 5.5% | 21.5% |

Zone went from noise to the model's 3rd-most-used feature; soil went from negligible to a real, if modest, contributor. Spot-checked live: asking for Cardamom in `high_ranges` with soil_type `"forest loam"` (its actual documented soil) now scores higher (0.368) than the same request with `"lateritic loam"` (0.298) — the direction the book supports. That check also caught and fixed a real bug in the soil-name resolver (a generic keyword tie made `"lateritic loam"` resolve to the wrong category); worth knowing in case you add more soil-type synonyms later — prefer the most specific matching keyword, not just the one with the most hits.

## The honest trade-offs

Nothing here was free:

- **Coverage vs. strictness.** Requiring temperature AND (season OR soil) — instead of v2's stricter "all three of temp/ph/season" — pushed the positive rate from 42% to 59% and crop coverage from 116/149 to 129/149 crops. That's a real design choice, not a neutral one: it's more lenient in what counts as "suitable," which is part of why coverage went up.
- **`high_ranges` got harder to generalize to.** Leave-one-zone-out accuracy for the held-out `high_ranges` zone dropped from 0.75 (v2) to 0.55 (v3) — the model now leans more on zone-specific patterns, and `high_ranges` is climatically/pedologically the most distinct zone, so it's the hardest one to predict correctly when the model has never seen it. The other 4 zones held up (0.84-0.85, similar to v2). If `high_ranges` predictions matter a lot to you, this is the number to watch.
- **The soil-type-per-zone mix is still a documented approximation**, not a soil survey (same caveat as v2's zone crosswalk — see README_v2.md). Replace `ZONE_SOIL_TYPES` in `tailor_dataset_v3.py`/`data_access_v3.py` with real per-field soil data once your GIS lookup is live; the model and API already expect a `soil_type` category, so that swap doesn't require touching the contract.
- **pH itself is still a weak signal** (0.9% importance) because the 6 soil categories' pH ranges are wide enough to overlap almost every crop's stated tolerance — it's along for the ride numerically but rarely decisive.

## Files added/changed this round

- `tailor_dataset_v3.py` — builds the soil-varying training data (`data/grounded_training_dataset_v3.csv`) and the soil reference table (`data/soil_type_reference.csv`).
- `train_model_v3.py` — retrains with `soil_type` in, `elevation_m` out; adds a leave-one-soil-type-out CV alongside leave-one-zone-out.
- `data_access_v3.py` — adds `resolve_soil_category()` (request text → trained category) and soil-aware knowledge-base methods.
- `main.py` — updated to call the v3 model/knowledge base, resolve the request's `soil_type`, and average across a zone's soil mix when it can't. Contract (endpoints, Pydantic models, `/reload-model/` mechanism) is unchanged from the previous drop-in.
- `model/crop_suitability_rf_v3.joblib`, `model/training_metrics_v3.json` — the retrained model and full metrics.

Live-tested end to end again after this change: health check, soil-resolved vs. soil-unresolved requests, the cardamom soil-direction check above, zone fallback, unresolved-commodity handling, and `/reload-model/` with the new model file — all matched the expected contract shape.
