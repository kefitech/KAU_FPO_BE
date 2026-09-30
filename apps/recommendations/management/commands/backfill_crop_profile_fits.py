"""
One-time backfill of CropZoneProfile.seasons / .suitable_soils (the structured
fields ml_service's rule-fit scorer reads) from the data we already have:

- seasons: parsed from each profile's own seasons_text with the same season
  synonym table ml_service/retrain_pipeline.py has always used to interpret
  that text for training labels -- so the structured field starts out saying
  exactly what training already assumed the text meant.
- suitable_soils: keyword-matched from the PoP book CSV's soil_type free text
  for the same (crop, kau_zone), with the same keyword table
  ml_service/data_access_v3.py uses to resolve request soil types. Rows whose
  book text is blank or "wide range of soils"-style stay [] (= unspecified).

Both tables are DUPLICATED here rather than imported: ml_service is a separate
process/deployment with its own venv (Django's has no pandas, ml_service's has
no Django) -- same stance as crop_zone_profile_admin.py's KAU_TO_SERVICE_ZONE.

Idempotent and conservative: only fills fields that are currently empty, so an
admin's manual selections are never overwritten. Run with --overwrite to
recompute everything, and --dry-run to preview.

    python manage.py backfill_crop_profile_fits [--dry-run] [--overwrite]

After a real run this calls export_and_notify() once, so ml_service picks the
new columns up immediately.
"""
import csv
from collections import defaultdict
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.database.models import CropZoneProfile

# ml_service/retrain_pipeline.py SEASON_SYNONYMS (keep in sync)
SEASON_SYNONYMS = {
    'southwest_monsoon': ['virippu', 'kharif', 'autumn', 'monsoon', 'first crop', 'i crop',
                          'rainfed', 'south-west monsoon', 'sw monsoon', 'june', 'july', 'august'],
    'northeast_monsoon': ['mundakan', 'rabi', 'second crop', 'ii crop', 'north-east monsoon',
                          'ne monsoon', 'october', 'november', 'winter'],
    'dry_season': ['puncha', 'zaid', 'summer', 'third crop', 'iii crop', 'dry season',
                   'irrigated', 'january', 'february', 'march', 'april', 'may'],
}
SEASON_ORDER = ['southwest_monsoon', 'northeast_monsoon', 'dry_season']

# ml_service/data_access_v3.py SOIL_KEYWORDS + retrain_pipeline.py
# UNIVERSAL_SOIL_PHRASES (keep in sync)
SOIL_KEYWORDS = {
    'Coastal sandy / laterite patches': ['coastal sand', 'onattukara', 'light coastal sand', 'coastal saline', 'sandy'],
    'Coastal alluvium / sandy, backwater-adjacent': ['alluvial', 'alluvium', 'backwater', 'kuttanad', 'reclaimed',
                                                     'marshy', 'kaipad', 'pokkali', 'riverine'],
    'Laterite': ['laterite', 'lateritic'],
    'Lateritic loam (transitional)': ['lateritic loam', 'lateritic gravelly', 'gravelly', 'midland'],
    'Black soil (Chittoor black soil) / red loam': ['black soil', 'black cotton', 'chittoor', 'red loam', 'black loam'],
    'Forest loam / hill soil (acidic, high organic matter)': ['forest loam', 'hill soil', 'humus', 'high ranges', 'high-range'],
}
UNIVERSAL_SOIL_PHRASES = ['wide range of soils', 'wide variety of soils', 'almost all soil types',
                          'various soils', 'all types of soils', 'adapted to almost all']

# A soil keyword found in a clause carrying one of these is a soil the book
# warns AGAINST, not recommends -- e.g. Fodder sorghum's "all soils except
# sandy soils" or Cinnamon's "marshy areas and hard laterites should be
# avoided". Clauses (split on ';' and '|') are checked independently so a
# negated warning clause doesn't poison the positive clause next to it.
NEGATION_MARKERS = ['except', 'avoid', 'unsuitable', 'not suited', 'not suitable',
                    'does not', 'cannot', 'poor growth', 'less suitable', 'not recommended']

BOOK_CSV = Path(settings.ML_SERVICE_DATA_DIR) / 'crop_prediction_dataset_with_commodity_codes.csv'


def parse_seasons(text: str) -> list:
    t = (text or '').strip().lower()
    if not t:
        return []
    return [s for s in SEASON_ORDER if any(k in t for k in SEASON_SYNONYMS[s])]


def parse_soils(text: str) -> list:
    t = (text or '').strip().lower()
    if not t or any(p in t for p in UNIVERSAL_SOIL_PHRASES):
        return []
    clauses = [c for part in t.split('|') for c in part.split(';')]
    positive = set()
    for clause in clauses:
        if any(m in clause for m in NEGATION_MARKERS):
            continue  # a warning clause -- soils named here are NOT endorsements
        positive.update(c for c, kws in SOIL_KEYWORDS.items() if any(k in clause for k in kws))
    return [c for c in SOIL_KEYWORDS if c in positive]  # stable canonical order


class Command(BaseCommand):
    help = "Backfill CropZoneProfile.seasons/.suitable_soils from seasons_text and the PoP book CSV."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Report what would change, write nothing.')
        parser.add_argument('--overwrite', action='store_true',
                            help='Recompute even where the field is already non-empty.')

    def handle(self, *args, **options):
        dry, overwrite = options['dry_run'], options['overwrite']

        # (crop_name.lower(), kau_zone) -> concatenated book soil text
        soil_text = defaultdict(list)
        if BOOK_CSV.is_file():
            with open(BOOK_CSV, newline='', encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    txt = (row.get('soil_type') or '').strip()
                    if txt:
                        soil_text[(row['crop_name'].strip().lower(), row['agro_zone'].strip())].append(txt)
        else:
            self.stdout.write(self.style.WARNING(
                f'{BOOK_CSV} not found -- suitable_soils left as-is, only seasons backfilled.'))

        changed_seasons = changed_soils = 0
        for p in CropZoneProfile.objects.filter(is_deleted=False):
            updates = []
            if overwrite or not p.seasons:
                seasons = parse_seasons(p.seasons_text)
                if seasons != p.seasons:
                    p.seasons = seasons
                    updates.append('seasons')
                    changed_seasons += 1
            if overwrite or not p.suitable_soils:
                text = ' | '.join(soil_text.get((p.crop_name.strip().lower(), p.kau_zone), []))
                soils = parse_soils(text)
                if soils != p.suitable_soils:
                    p.suitable_soils = soils
                    updates.append('suitable_soils')
                    changed_soils += 1
            if updates and not dry:
                p.save(update_fields=updates + ['updated_at'])

        self.stdout.write(self.style.SUCCESS(
            f"{'DRY RUN: would update' if dry else 'Updated'} seasons on {changed_seasons} "
            f"and suitable_soils on {changed_soils} profiles."))

        if not dry and (changed_seasons or changed_soils):
            from apps.recommendations.api.crop_zone_profile_admin import export_and_notify
            export_and_notify()
            self.stdout.write('Re-exported crop_profiles_service_zones.csv and notified ml_service.')
                                                                                                                                                                                                                                                                                                                                                                                                                    