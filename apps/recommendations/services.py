"""
FastAPI ML Service Proxy — P2-06
Calls the FastAPI crop-recommendation service and handles graceful
degradation when it's unavailable.
"""
import httpx
from datetime import date
from django.conf import settings

from apps.database.models import CropRecommendation
from apps.gis_module.services import resolve_fpo_zone, get_current_season


def get_current_financial_year() -> str:
    """
    Returns India's financial year as 'YYYY-YY', e.g. '2026-27'.
    FY runs April 1 – March 31.

    NOTE: assumes the standard April–March Indian FY convention used
    elsewhere in the doc's example payload ("2025-26"). Confirm with the
    team if KAU uses a different fiscal calendar for this platform.
    """
    today = date.today()
    if today.month >= 4:
        start_year = today.year
    else:
        start_year = today.year - 1
    end_year_short = str(start_year + 1)[-2:]
    return f"{start_year}-{end_year_short}"


def build_recommendation_payload(fpo, model_version, financial_year) -> dict:
    """
    Builds the FastAPI request payload matching the richer P2-06 module
    spec: fpo_id, district, agro_zone, soil_type, season, commodities,
    tier, model_version, financial_year.

    agro_zone/soil_type come from resolve_fpo_zone() — a live spatial
    lookup against WHERE THE FARM ACTUALLY IS (cultivation area centroid,
    falling back to the FPO's own lat/lng), not the FPO's separate
    FPOZoneAssignment cache. Same reasoning as cultivation_area.py's
    serializer: an FPO's registered address and their farmland can
    legitimately be in different zones.
    """
    zone = resolve_fpo_zone(fpo)
    agro_zone_code = zone.code if zone else None
    soil_type = zone.soil_type if zone else None

    commodities = list(fpo.primary_commodities or []) + list(fpo.secondary_commodities or [])

    return {
        "fpo_id": str(fpo.pk),
        "district": fpo.district,
        "agro_zone": agro_zone_code,
        "soil_type": soil_type,
        "season": get_current_season(),
        "commodities": commodities,
        "tier": fpo.current_tier,
        "model_version": model_version.version_code if model_version else None,
        "financial_year": financial_year,
    }


def get_crop_recommendation(fpo, model_version, financial_year):
    """
    Calls the FastAPI ML service for a crop recommendation.

    On any failure (FastAPI down, timeout, bad response), falls back to
    the FPO's last cached recommendation, or an empty result with a
    warning if none exists.
    """
    payload = build_recommendation_payload(fpo, model_version, financial_year)

    try:
        response = httpx.post(
            f"{settings.ML_SERVICE_URL}/predict/crops/",
            json=payload,
            timeout=10.0,
        )
        response.raise_for_status()
        result = response.json()
        result['cached'] = False
        return result

    except Exception:
        last = (
            CropRecommendation.objects
            .filter(fpo=fpo)
            .order_by('-created_at')
            .first()
        )
        if last:
            return {
                "cached": True,
                "recommendations": last.recommendations,
            }
        return {
            "cached": True,
            "recommendations": [],
            "warning": "AI service unavailable",
        }