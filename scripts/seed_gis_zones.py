"""
Seed script — placeholder Agro-Climatic Zones for Kerala.

TEMPORARY: These are dummy grid polygons roughly covering Kerala's
bounding box, NOT accurate zone boundaries. Replace with the real
KAU-provided GeoJSON once available (see doc: "What NOT to Build Yet").

Usage:
    python manage.py shell < scripts/seed_gis_zones.py
    (or wrap this in a management command if the project prefers that)
"""
from django.contrib.gis.geos import Polygon, MultiPolygon

from apps.database.models import AgroClimaticZone

# Kerala's rough bounding box: lat 8.2–12.8, lng 74.8–77.4
# Split into 5 non-overlapping horizontal bands (south to north) —
# not geographically meaningful, just distinct valid polygons for testing.

ZONES = [
    {
        'code': 'coastal_zone',
        'name_en': 'Coastal Zone',
        'name_ml': 'തീരദേശ മേഖല',
        'suitable_crops': ['coconut', 'rice', 'banana'],
        'soil_type': 'Sandy, alluvial coastal soil',
        'bbox': (74.8, 8.2, 77.4, 9.0),  # (min_lng, min_lat, max_lng, max_lat)
    },
    {
        'code': 'southern_zone',
        'name_en': 'Southern Zone',
        'name_ml': 'തെക്കൻ മേഖല',
        'suitable_crops': ['rubber', 'coconut', 'tapioca'],
        'soil_type': 'Laterite',
        'bbox': (74.8, 9.0, 77.4, 9.8),
    },
    {
        'code': 'central_zone',
        'name_en': 'Central Zone',
        'name_ml': 'മധ്യമേഖല',
        'suitable_crops': ['rice', 'coconut', 'arecanut'],
        'soil_type': 'Alluvial, riverine',
        'bbox': (74.8, 9.8, 77.4, 10.6),
    },
    {
        'code': 'high_ranges',
        'name_en': 'High Ranges Zone',
        'name_ml': 'ഹൈ റേഞ്ച് മേഖല',
        'suitable_crops': ['cardamom', 'coffee', 'tea', 'pepper'],
        'soil_type': 'Forest loam, high organic content',
        'bbox': (74.8, 10.6, 77.4, 11.6),
    },
    {
        'code': 'northern_zone',
        'name_en': 'Northern Zone',
        'name_ml': 'വടക്കൻ മേഖല',
        'suitable_crops': ['rice', 'coconut', 'cashew'],
        'soil_type': 'Laterite, sandy loam',
        'bbox': (74.8, 11.6, 77.4, 12.8),
    },
]


def make_multipolygon(bbox):
    min_lng, min_lat, max_lng, max_lat = bbox
    ring = (
        (min_lng, min_lat),
        (max_lng, min_lat),
        (max_lng, max_lat),
        (min_lng, max_lat),
        (min_lng, min_lat),  # ring must close
    )
    polygon = Polygon(ring, srid=4326)
    return MultiPolygon(polygon, srid=4326)


def run():
    created_count = 0
    updated_count = 0

    for zone_data in ZONES:
        boundary = make_multipolygon(zone_data['bbox'])

        obj, created = AgroClimaticZone.objects.update_or_create(
            code=zone_data['code'],
            defaults={
                'name_en': zone_data['name_en'],
                'name_ml': zone_data['name_ml'],
                'suitable_crops': zone_data['suitable_crops'],
                'soil_type': zone_data['soil_type'],
                'boundary': boundary,
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