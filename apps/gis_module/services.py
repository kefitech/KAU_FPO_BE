"""
GIS Weather Service — apps/gis_module/services.py

Tries OpenWeatherMap's real Current Weather API first — reading the
API key from ExternalAPISettings (service='weather_api'), the same
encrypted-credential system used for PAN/GSTIN/CIN verification and
the AI chat feature (apps/database/models/external_api.py). Manage
the key via the existing admin dashboard (/admin/external-apis in the
frontend) — no new UI needed, this system was already built to be
generic across services.

Falls back to a SIMULATED estimate (season + zone based) if the
service isn't registered, isn't active, or the API call fails for any
reason — same graceful-degradation pattern used throughout this
project (e.g. the FastAPI recommendation proxy's cached-fallback
logic).

Chose OpenWeatherMap over Open-Meteo: Open-Meteo's free tier is
explicitly non-commercial-use-only per their Terms of Service — not
appropriate for this commercially-contracted platform. OpenWeatherMap's
free tier explicitly permits commercial use with attribution.

India Meteorological Department's Agromet Advisories API
(api.imd.gov.in) remains the eventual ideal (agriculture-focused,
official government data) but requires organizational registration +
IP whitelisting — out of scope for this module alone. OpenWeatherMap
is the pragmatic interim real data source.
"""
from datetime import date

import httpx
from django.contrib.gis.geos import Point

OPENWEATHERMAP_URL = "https://api.openweathermap.org/data/2.5/weather"


def _get_weather_api_key() -> str | None:
    """
    Looks up the active weather_api credential from ExternalAPISettings.
    Returns None if no entry exists, it's inactive, or has no api_key —
    any of which triggers the simulated fallback in get_weather_for_point().
    """
    from apps.database.models import ExternalAPISettings
    from apps.notifications.utils import decrypt_config

    settings_obj = ExternalAPISettings.objects.filter(
        service=ExternalAPISettings.SERVICE_WEATHER, is_active=True
    ).first()
    if not settings_obj or not settings_obj.config:
        return None

    config = decrypt_config(settings_obj.config)
    return config.get('api_key') or None


def find_zone_for_point(lat: float, lng: float):
    """
    Live spatial lookup — which AgroClimaticZone contains this point.
    Public, shared helper: used by weather simulation below, by
    cultivation_area.py's serializer, and by recommendations' payload
    building — one implementation, not three copies that can drift out
    of sync (this exact class of bug happened once already with
    cultivation area zone lookups defaulting to the FPO's registered
    address instead of the plot's actual location).
    """
    from apps.database.models import AgroClimaticZone

    point = Point(lng, lat, srid=4326)
    return AgroClimaticZone.objects.filter(boundary__contains=point).first()


def resolve_fpo_location(fpo):
    """
    Returns (lat, lng) or (None, None) if the FPO has no usable location.
    Prefers the cultivation area's centroid (more precise — the actual
    farmed plot), falls back to the FPO's own latitude/longitude.

    Public, shared helper — used anywhere "where is this FPO's farm"
    needs answering generically (weather, recommendation payloads).
    Cultivation area's OWN serializer doesn't need this: it already has
    its own area_polygon directly, no fallback required.
    """
    cultivation_area = getattr(fpo, 'cultivation_area', None)
    if cultivation_area and cultivation_area.area_polygon:
        centroid = cultivation_area.area_polygon.centroid
        return centroid.y, centroid.x  # .y = lat, .x = lng

    if fpo.latitude is not None and fpo.longitude is not None:
        return float(fpo.latitude), float(fpo.longitude)

    return None, None


def resolve_fpo_zone(fpo):
    """
    Convenience wrapper: resolve_fpo_location() + find_zone_for_point()
    in one call. Returns an AgroClimaticZone or None.
    """
    lat, lng = resolve_fpo_location(fpo)
    if lat is None or lng is None:
        return None
    return find_zone_for_point(lat, lng)


# ── Season detection — Kerala's monsoon calendar ──

def get_current_season(reference_date: date | None = None) -> str:
    """
    Kerala has three broad seasons:
    - southwest_monsoon: June-September (main monsoon, heaviest rainfall)
    - northeast_monsoon: October-November (secondary monsoon)
    - dry_season: December-May (hot, dry, pre-monsoon)
    """
    d = reference_date or date.today()
    month = d.month

    if 6 <= month <= 9:
        return 'southwest_monsoon'
    if month in (10, 11):
        return 'northeast_monsoon'
    return 'dry_season'


# ── Real weather — OpenWeatherMap ──

def _fetch_real_weather(lat: float, lng: float) -> dict | None:
    """
    Calls OpenWeatherMap's Current Weather API. Returns None (which
    triggers fallback to simulation below) if no API key is configured,
    or if the call fails for any reason — network error, rate limit,
    invalid response, etc.

    HONEST NOTE on rainfall: OpenWeatherMap's 'rain' field is real,
    measured rainfall in the LAST 1 HOUR (mm) — not a seasonal or daily
    total. This is genuinely a different quantity than the simulated
    fallback's 'rainfall_mm' (an illustrative SEASONAL estimate). Both
    are returned under the same field name for API-contract stability,
    but the MEANING differs by is_simulated: "recent measured rainfall"
    when False, vs. "illustrative seasonal estimate" when True. Don't
    conflate the two when interpreting stored FPOWeatherSnapshot rows.
    """
    api_key = _get_weather_api_key()
    if not api_key:
        return None

    try:
        response = httpx.get(
            OPENWEATHERMAP_URL,
            params={'lat': lat, 'lon': lng, 'appid': api_key, 'units': 'metric'},
            timeout=5.0,
        )
        response.raise_for_status()
        data = response.json()

        return {
            'temperature_c': round(data['main']['temp'], 1),
            'humidity_percent': round(data['main']['humidity'], 1),
            'rainfall_mm': round(data.get('rain', {}).get('1h', 0.0), 1),
            'description': data['weather'][0]['description'].capitalize(),
        }
    except Exception:
        return None


# ── Simulated fallback — used only if the real API is unavailable ──

# Rough seasonal baselines for Kerala — deliberately simple, illustrative
# ranges, not derived from any real dataset.
_SEASON_PROFILES = {
    'southwest_monsoon': {
        'temperature_c': 26.5,
        'humidity_percent': 88.0,
        'rainfall_mm': 620.0,
        'description': 'Heavy monsoon rainfall expected',
    },
    'northeast_monsoon': {
        'temperature_c': 27.5,
        'humidity_percent': 80.0,
        'rainfall_mm': 280.0,
        'description': 'Moderate rainfall, retreating monsoon',
    },
    'dry_season': {
        'temperature_c': 31.0,
        'humidity_percent': 65.0,
        'rainfall_mm': 40.0,
        'description': 'Dry conditions, occasional pre-monsoon showers',
    },
}

# Rough per-zone adjustments applied on top of the season baseline —
# illustrative only (e.g. highland zones run cooler and wetter than
# coastal zones at the same time of year). Keyed by AgroClimaticZone.code.
_ZONE_ADJUSTMENTS = {
    'coastal_zone': {
        'temperature_c': +2.0, 'humidity_percent': +5.0, 'rainfall_mm': +0.0,
        'note': 'coastal — warmer, more humid',
    },
    'high_ranges': {
        'temperature_c': -6.0, 'humidity_percent': +3.0, 'rainfall_mm': +150.0,
        'note': 'high elevation — cooler, wetter',
    },
    'southern_zone': {
        'temperature_c': 0.0, 'humidity_percent': 0.0, 'rainfall_mm': 0.0,
        'note': None,
    },
    'central_zone': {
        'temperature_c': 0.0, 'humidity_percent': 0.0, 'rainfall_mm': 0.0,
        'note': None,
    },
    'northern_zone': {
        'temperature_c': +0.5, 'humidity_percent': 0.0, 'rainfall_mm': -30.0,
        'note': None,
    },
}


def _simulate_weather(lat: float, lng: float, season: str) -> dict:
    """Illustrative fallback — only used when the real API is unavailable."""
    profile = _SEASON_PROFILES[season]
    zone = find_zone_for_point(lat, lng)
    adjustment = _ZONE_ADJUSTMENTS.get(zone.code, {}) if zone else {}

    temperature_c = profile['temperature_c'] + adjustment.get('temperature_c', 0.0)
    humidity_percent = profile['humidity_percent'] + adjustment.get('humidity_percent', 0.0)
    rainfall_mm = max(0.0, profile['rainfall_mm'] + adjustment.get('rainfall_mm', 0.0))

    description = profile['description']
    zone_note = adjustment.get('note')
    if zone_note:
        description = f"{description} ({zone_note})"

    return {
        'temperature_c': round(temperature_c, 1),
        'humidity_percent': round(humidity_percent, 1),
        'rainfall_mm': round(rainfall_mm, 1),
        'description': description,
    }


def get_weather_for_point(lat: float, lng: float, reference_date: date | None = None) -> dict:
    """
    Returns a weather estimate for the given coordinates. Tries the
    real OpenWeatherMap API first; falls back to a simulated
    season+zone-based estimate if the API call fails or no key is
    configured.

    Return shape (kept stable regardless of source):
        {
            'temperature_c': float,
            'humidity_percent': float,
            'rainfall_mm': float,
            'season': str,
            'description': str,
            'is_simulated': bool,
        }
    """
    season = get_current_season(reference_date)

    real = _fetch_real_weather(lat, lng)
    if real is not None:
        return {
            **real,
            'season': season,
            'is_simulated': False,
        }

    simulated = _simulate_weather(lat, lng, season)
    return {
        **simulated,
        'season': season,
        'is_simulated': True,
    }