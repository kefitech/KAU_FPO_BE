"""
Seed script — placeholder District Boundaries for Kerala's 14 districts.

TEMPORARY: boundaries are small dummy squares centered on each district's
approximate real-world centroid — NOT accurate administrative boundaries.
Real shapes should come from an official source (e.g. Survey of India,
Kerala GIS cell) when available. Centroids are approximate town-center
coordinates, close enough for testing but not survey-accurate.

DistrictBoundary has no name field — display names come from
apps.core.utils.constants.District / DISTRICTS_BILINGUAL.

Usage:
    python manage.py shell < scripts/seed_gis_districts.py
"""
from django.contrib.gis.geos import Polygon, MultiPolygon

from apps.database.models import DistrictBoundary

# code -> (centroid_lat, centroid_lng)  — approximate district town centers
DISTRICT_CENTROIDS = {
    'TVM': (8.5241, 76.9366),
    'KLM': (8.8932, 76.6141),
    'PTA': (9.2648, 76.7870),
    'ALP': (9.4981, 76.3388),
    'KTM': (9.5916, 76.5222),
    'IDK': (9.8560, 76.9700),
    'EKM': (9.9816, 76.2999),
    'TSR': (10.5276, 76.2144),
    'PKD': (10.7867, 76.6548),
    'MLP': (11.0510, 76.0711),
    'KZD': (11.2588, 75.7804),
    'WYD': (11.6854, 76.1320),
    'KNR': (11.8745, 75.3704),
    'KSD': (12.4996, 74.9869),
}

HALF_WIDTH = 0.15  # degrees — dummy square size around each centroid


def make_square(lat, lng, half_width=HALF_WIDTH):
    ring = (
        (lng - half_width, lat - half_width),
        (lng + half_width, lat - half_width),
        (lng + half_width, lat + half_width),
        (lng - half_width, lat + half_width),
        (lng - half_width, lat - half_width),  # ring must close
    )
    polygon = Polygon(ring, srid=4326)
    return MultiPolygon(polygon, srid=4326)


def run():
    created_count = 0
    updated_count = 0

    for code, (lat, lng) in DISTRICT_CENTROIDS.items():
        boundary = make_square(lat, lng)
        centroid = boundary.centroid  # derives a Point from the polygon itself

        obj, created = DistrictBoundary.objects.update_or_create(
            code=code,
            defaults={
                'boundary': boundary,
                'centroid': centroid,
            },
        )

        if created:
            created_count += 1
            print(f"Created: {obj.code}")
        else:
            updated_count += 1
            print(f"Updated: {obj.code}")

    print(f"\nDone. {created_count} created, {updated_count} updated.")


run()