"""
Seed CropZoneProfile from ml_service's existing crop_profiles_service_zones.csv.

REQUIRED ONE-TIME STEP before using the new admin CRUD (apps.recommendations.
api.crop_zone_profile_admin) for the first time: the CRUD's export always
writes ALL active DB rows as the complete knowledge base ml_service reads --
if the DB starts empty, an admin's very first create/activate would export
just their one new row and wipe out every other crop's eligibility. Seeding
the DB with the current CSV content first (all rows is_active=True, matching
today's live behavior) makes the CRUD safe to use incrementally afterward.

The CSV has one row per (crop, SERVICE zone) -- already expanded via the
KAU-zone -> service-zone crosswalk. CropZoneProfile stores one row per
(crop, KAU zone) instead (the book's own granularity -- see the model's
docstring), so this collapses the expansion back: verified safe to do
(every expanded group's non-key columns are identical -- see the checked-in
sanity check this script re-runs and asserts on) since the crosswalk is a
pure fan-out, not a per-zone override.

Usage:
    python manage.py shell -c "
    exec(open('scripts/seed_crop_zone_profiles.py').read())
    seed_crop_zone_profiles()"
"""
import csv
import os
from collections import OrderedDict
from pathlib import Path

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.conf import settings

from apps.database.models import CropZoneProfile

# NOT Path(__file__) -- this module is meant to be run via exec(open(...).read())
# from `manage.py shell`, which leaves __file__ pointing at whatever module called
# exec(), not this file. settings.ML_SERVICE_DATA_DIR is the same path the admin
# CRUD's export_and_notify() writes to (see crop_zone_profile_admin.py), so this
# also doubles as a check that the two agree.
SOURCE_CSV = Path(settings.ML_SERVICE_DATA_DIR) / 'crop_profiles_service_zones.csv'

CONSISTENCY_COLUMNS = [
    'crop_group', 'temp_lo', 'temp_hi', 'ph_lo', 'ph_hi',
    'seasons_text', 'ph_is_real', 'temp_is_real',
]


def _to01(v: str) -> bool:
    return v.strip().lower() in ('true', '1')


def seed_crop_zone_profiles():
    if not SOURCE_CSV.is_file():
        print(f"❌ Source file not found: {SOURCE_CSV}")
        return

    # Collapse (crop, service_zone)-expanded rows back to one per (crop, kau_zone) --
    # keep the first row per group, but verify every group actually agrees first
    # (a real content difference would mean the collapse loses information silently).
    groups = OrderedDict()
    with open(SOURCE_CSV, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            key = (row['crop_name'], row['agro_zone'])
            groups.setdefault(key, []).append(row)

    inconsistent = []
    for key, rows in groups.items():
        first = rows[0]
        for row in rows[1:]:
            if any(row[c] != first[c] for c in CONSISTENCY_COLUMNS):
                inconsistent.append(key)
                break

    if inconsistent:
        print(f"❌ {len(inconsistent)} (crop, kau_zone) group(s) disagree across their expanded service-zone rows "
              f"-- refusing to collapse blindly. First few: {inconsistent[:5]}")
        return

    created, updated = 0, 0
    for (crop_name, kau_zone), rows in groups.items():
        row = rows[0]
        obj, was_created = CropZoneProfile.objects.update_or_create(
            crop_name=crop_name, kau_zone=kau_zone,
            defaults={
                'crop_group': row['crop_group'],
                'temp_lo': float(row['temp_lo']), 'temp_hi': float(row['temp_hi']),
                'ph_lo': float(row['ph_lo']), 'ph_hi': float(row['ph_hi']),
                'seasons_text': row['seasons_text'],
                'temp_is_real': _to01(row['temp_is_real']),
                'ph_is_real': _to01(row['ph_is_real']),
                'is_active': True,  # matches today's live behavior -- the CSV is already what's serving
            },
        )
        created += was_created
        updated += not was_created

    print(f"\n✅ Crop zone profiles seeded: {created} created, {updated} updated. "
          f"Total rows: {CropZoneProfile.objects.filter(is_deleted=False).count()} "
          f"({CropZoneProfile.objects.filter(is_deleted=False).values('crop_name').distinct().count()} unique crops)")
    print("   The CRUD's export is now safe to use -- it will reproduce the current live knowledge base "
          "exactly, then diverge only as admins make real edits.")


if __name__ == '__main__':
    seed_crop_zone_profiles()
