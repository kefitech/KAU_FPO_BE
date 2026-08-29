"""
GIS Weather Service — apps/gis_module/services.py

TEMPORARY: get_weather_for_point() currently returns a SIMULATED
estimate combining season (from today's date) and zone (from a live
spatial lookup against AgroClimaticZone) — not real weather data.
India Meteorological Department's Agromet Advisories API
(api.imd.gov.in) is the intended real source — agriculture-focused,
official government data, a strong fit for this platform. It requires
account registration and IP whitelisting through IMD's portal
(api.imd.gov.in/public/login.php), which is an organizational step for
whoever manages vendor/API registrations, not something wireable
directly in this module.

When that's set up: replace the body of get_weather_for_point() with a
real API call, keep the same return shape, and set is_simulated=False.
No other code (views, models) needs to change — everything downstream
consumes this function's return value, not its implementation.
"""
from datetime import date

from django.contrib.gis.geos import Point


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


def get_weather_for_point(lat: float, lng: float, reference_date: date | None = None) -> dict:
    """
    Returns a weather estimate for the given coordinates.

    TEMPORARY / SIMULATED: does not call any real weather service.
    Combines Kerala's seasonal calendar (varies by date) with a live
    lookup of which AgroClimaticZone the point falls in (varies by
    location, via find_zone_for_point above) to produce a more
    location-aware estimate than season alone. Still illustrative, not
    measured data.

    Return shape (kept stable so callers don't need to change when
    this is swapped for a real API):
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
        'season': season,
        'description': description,
        'is_simulated': True,
    }