"""Loads the PoP crosswalk + service-zone climate + soil-type reference for v3.

Adds real soil-type resolution on top of data_access.py (v2): a request's
free-text `soil_type` (e.g. "laterite", "sandy", "alluvial soil") is matched
to one of the 6 canonical soil categories used in training, instead of being
ignored (v2 accepted `soil_type` in the request but never used it -- see
README_v2.md's placeholder note).
"""
import pandas as pd

COMMODITY_CROSSWALK_PATH = "data/crop_prediction_dataset_with_commodity_codes.csv"
CROP_PROFILES_PATH = "data/crop_profiles_service_zones.csv"   # for reasoning text (temp/ph ranges)
CLIMATE_PATH = "data/zone_climate_real.csv"
SOIL_REF_PATH = "data/soil_type_reference.csv"

# same zone -> plausible soil types + keyword matcher as tailor_dataset_v3.py
ZONE_SOIL_TYPES = {
    "coastal_zone": ["Coastal sandy / laterite patches", "Coastal alluvium / sandy, backwater-adjacent"],
    "southern_zone": ["Laterite", "Lateritic loam (transitional)"],
    "central_zone": ["Laterite", "Black soil (Chittoor black soil) / red loam"],
    "northern_zone": ["Laterite", "Forest loam / hill soil (acidic, high organic matter)"],
    "high_ranges": ["Forest loam / hill soil (acidic, high organic matter)", "Lateritic loam (transitional)"],
}
SOIL_KEYWORDS = {
    "Coastal sandy / laterite patches": ["coastal sand", "onattukara", "light coastal sand", "coastal saline", "sandy"],
    "Coastal alluvium / sandy, backwater-adjacent": ["alluvial", "alluvium", "backwater", "kuttanad", "reclaimed",
                                                      "marshy", "kaipad", "pokkali", "riverine"],
    "Laterite": ["laterite", "lateritic"],
    "Lateritic loam (transitional)": ["lateritic loam", "lateritic gravelly", "gravelly", "midland"],
    "Black soil (Chittoor black soil) / red loam": ["black soil", "black cotton", "chittoor", "red loam", "black loam"],
    "Forest loam / hill soil (acidic, high organic matter)": ["forest loam", "hill soil", "humus", "high ranges", "high-range"],
}


def resolve_soil_category(requested_soil_type: str):
    """Map a free-text soil_type request field to one of the 6 training categories.
    Returns None if it can't be confidently resolved (caller should fall back to
    averaging across the zone's known soil mix)."""
    if not requested_soil_type or not requested_soil_type.strip():
        return None
    text = requested_soil_type.strip().lower()
    # exact/near-exact match against a canonical category name first
    for cat in SOIL_KEYWORDS:
        if text == cat.lower():
            return cat
    # keyword match, preferring the MOST SPECIFIC (longest) matching keyword -- e.g. a request of
    # "lateritic loam" must resolve to "Lateritic loam (transitional)", not "Laterite", even though
    # the generic "lateritic" keyword under Laterite also matches. Ranking by hit *count* instead of
    # specificity would have both categories tie at 1 hit and pick whichever appears first in the
    # dict (a real bug caught by testing "lateritic loam" against both categories).
    best, best_len = None, 0
    for cat, kws in SOIL_KEYWORDS.items():
        match_len = max((len(kw) for kw in kws if kw in text), default=0)
        if match_len > best_len:
            best, best_len = cat, match_len
    return best


class CropKnowledgeBase:
    def __init__(self):
        self.pop = pd.read_csv(COMMODITY_CROSSWALK_PATH, dtype=str, keep_default_na=False)
        self.profiles = pd.read_csv(CROP_PROFILES_PATH)
        self.climate = pd.read_csv(CLIMATE_PATH)
        self.soil_ref = pd.read_csv(SOIL_REF_PATH).set_index("soil_type")

        self.code_to_crop = {}
        self.name_to_crop = {}
        for _, row in self.pop.iterrows():
            crop = row["crop_name"]
            self.name_to_crop[crop.lower()] = crop
            for code in [c.strip() for c in row["commodity_code"].split(";") if c.strip()]:
                self.code_to_crop.setdefault(code, crop)
            for en in [e.strip() for e in row["commodity_en"].split(";") if e.strip()]:
                self.name_to_crop.setdefault(en.lower(), crop)
        extra_aliases = {"paddy": "Rice", "cassava": "Tapioca", "pepper": "Black pepper"}
        for k, v in extra_aliases.items():
            self.name_to_crop.setdefault(k, v)

    def resolve_crop(self, requested: str):
        key = requested.strip().lower()
        if key in self.code_to_crop:
            return self.code_to_crop[key]
        if key in self.name_to_crop:
            return self.name_to_crop[key]
        base = key.split("_")[0]
        return self.name_to_crop.get(base)

    def crop_rows(self, crop_name: str) -> pd.DataFrame:
        return self.pop[self.pop["crop_name"] == crop_name]

    def crop_zone_profile(self, crop_name: str, zone: str):
        sub = self.profiles[(self.profiles["crop_name"] == crop_name) & (self.profiles["service_zone"] == zone)]
        return sub.iloc[0] if len(sub) else None

    def known_crop_names(self) -> set:
        return set(self.pop["crop_name"].unique())

    def crops_in_zone(self, zone: str) -> set:
        return set(self.profiles[self.profiles["service_zone"] == zone]["crop_name"].unique())

    def is_zone_specific(self, crop_name: str, zone: str) -> bool:
        """True if the PoP book documents this crop for a real KAU zone that crosswalks to
        `zone` (e.g. Coffee/Cardamom/Tea -> High Hills -> high_ranges), as opposed to only
        appearing here via the 'General (all zones)' catch-all (used for crops the book
        never localizes to one zone -- ~78% of the 149-crop dataset). Used to rank
        genuinely zone-documented specialty crops above generic ones that merely
        didn't get filtered out (see README_v3.md's zone-specificity note)."""
        row = self.profiles[(self.profiles["crop_name"] == crop_name) & (self.profiles["service_zone"] == zone)]
        if row.empty:
            return False
        return bool((row["kau_zone_source"] != "General (all zones)").any())

    def soil_ph_range(self, soil_category: str):
        row = self.soil_ref.loc[soil_category]
        return float(row["ph_lo"]), float(row["ph_hi"])

    def soil_categories_for_zone(self, zone: str):
        return ZONE_SOIL_TYPES.get(zone, list(self.soil_ref.index))

    def representative_climate(self, zone: str, season: str) -> dict:
        subset = self.climate[(self.climate["zone"] == zone) & (self.climate["season"] == season)]
        if subset.empty:
            subset = self.climate[self.climate["zone"] == zone]
        if subset.empty:
            subset = self.climate
        return {
            "temperature_avg_C": float(subset["temperature_avg_C"].mean()),
            "rainfall_mm": float(subset["rainfall_mm"].mean()),
            "humidity_pct": float(subset["humidity_pct"].mean()),
            "n_samples": len(subset),
        }
