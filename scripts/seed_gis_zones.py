"""
Seed script — REAL Kerala agro-climatic zone boundaries.

Replaces the earlier placeholder version (5 equal horizontal latitude
bands, which incorrectly split mountainous districts like Idukki
across multiple zones purely based on raw latitude).

This version builds each zone's actual shape by dissolving together
real taluk (sub-district) boundaries — sourced from LGD/Survey of
India via github.com/yashveeeeeeer/india-geodata — that have been
manually classified into a zone based on real Kerala geography (which
taluks are genuinely coastal, mountainous, etc.), not a raw
coordinate formula.

This is still NOT KAU's official agro-climatic zone system — it's a
geographically-grounded interim proxy, built from real administrative
boundaries and real geographic knowledge, pending KAU's actual data.
The taluk->zone classification is a best-effort judgment call — worth
a sanity check from someone with real local knowledge before treating
as final.

Requires zone_geometries.json to be present at the path below.

Usage:
    python manage.py shell < scripts/seed_gis_zones.py
"""
import json
from pathlib import Path

from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon, Polygon

from apps.database.models import AgroClimaticZone

GEOMETRY_PATH = Path(settings.BASE_DIR) / 'scripts' / 'data' / 'zone_geometries.json'

# Zone metadata — unchanged from the original placeholder version.
# code -> (name_en, name_ml, suitable_crops, soil_type)
ZONE_METADATA = {
    'coastal_zone': (
        'Coastal Zone', 'തീരദേശ മേഖല',
        ['coconut', 'rice', 'cashew', 'banana'],
        'Sandy, alluvial coastal soil',
    ),
    'southern_zone': (
        'Southern Zone', 'തെക്കൻ മേഖല',
        ['rubber', 'tapioca', 'coconut', 'pepper'],
        'Laterite soil',
    ),
    'central_zone': (
        'Central Zone', 'മധ്യ മേഖല',
        ['arecanut', 'rice', 'coconut', 'banana'],
        'Alluvial and riverine soil',
    ),
    'high_ranges': (
        'High Ranges', 'ഉയർന്ന പ്രദേശങ്ങൾ',
        ['cardamom', 'tea', 'coffee', 'pepper'],
        'Forest loam, high organic content',
    ),
    'northern_zone': (
        'Northern Zone', 'വടക്കൻ മേഖല',
        ['cashew', 'coconut', 'rice', 'pepper'],
        'Laterite and sandy soil',
    ),
}


def run():
    if not GEOMETRY_PATH.exists():
        print(f"ERROR: file not found at {GEOMETRY_PATH}")
        print("Place zone_geometries.json at scripts/data/zone_geometries.json")
        return

    with open(GEOMETRY_PATH) as f:
        zone_geometries = json.load(f)

    created_count = 0
    updated_count = 0

    for code, (name_en, name_ml, crops, soil_type) in ZONE_METADATA.items():
        geom_json = zone_geometries.get(code)
        if not geom_json:
            print(f"WARNING: no geometry found for {code} — skipping")
            continue

        geometry = GEOSGeometry(json.dumps(geom_json), srid=4326)
        if isinstance(geometry, Polygon):
            geometry = MultiPolygon(geometry, srid=4326)

        obj, created = AgroClimaticZone.objects.update_or_create(
            code=code,
            defaults={
                'name_en': name_en,
                'name_ml': name_ml,
                'boundary': geometry,
                'suitable_crops': crops,
                'soil_type': soil_type,
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