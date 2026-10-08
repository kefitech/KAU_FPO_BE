"""
Indicative Kerala crop yields — kg per acre per year — for the raw-material
vs member-acreage cross-check (KAU contradiction review 2026-10-08,
Pattern 3 / tester Priority-1 list).

MasterLookup category: `commodity_yield`; `code` matches the `commodity`
category codes; the yield lives in metadata['kg_per_acre_per_year'].

These are INDICATIVE state-level figures (Kerala agri statistics, rounded)
— admin-editable via the MasterLookup admin like all master data, and the
validator that reads them only ever produces a WARNING, never a block.
KAU can refine per-district values later; the check compares order of
magnitude (members' supply ceiling), not agronomic precision.

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/seed_commodity_yields.py').read())
    seed_commodity_yields()
    "
Idempotent — uses update_or_create.
"""

from apps.core.models.generic import MasterLookup

# kg / acre / year (annualised — two-crop paddy counted as two harvests)
_YIELDS = {
    'rice_paddy':     2300,   # ~2.8 t/ha/season x ~2 seasons
    'banana':         9500,
    'black_pepper':   260,    # intercropped Kerala average is far lower than monocrop
    'cardamom':       100,
    'coconut':        3400,   # ~8500 nuts/acre/yr x ~0.4 kg copra-equivalent
    'arecanut':       550,
    'cashew':         300,
    'coffee':         380,
    'rubber':         600,
    'ginger':         3200,
    'turmeric':       3300,
    'tapioca':        11500,
    'pineapple':      8000,
    'mango':          2800,
    'jackfruit':      5500,
    'papaya':         14000,
    'guava':          4500,
    'finger_millet':  700,
    'little_millet':  450,
    'pearl_millet':   600,
    'sorghum':        750,
    'foxtail_millet': 450,
    'sesame':         180,
    'mixed_vegetables': 4800,
    'bitter_gourd':   3200,
    'cucumber':       4000,
    'chilli':         1000,
    'drumstick':      2000,
    'peas':           1400,
    'mushroom':       6000,   # per acre of shed floor area equivalent
    'nutmeg':         300,
    'clove':          180,
    'cinnamon':       250,
    'cocoa':          350,
}


def seed_commodity_yields():
    created = updated = 0
    for code, kg in _YIELDS.items():
        _, was_created = MasterLookup.objects.update_or_create(
            category='commodity_yield',
            code=code,
            defaults={
                'metadata': {'kg_per_acre_per_year': kg,
                             'basis': 'Indicative Kerala state-level average (admin-editable)'},
                'is_active': True,
            },
        )
        created += was_created
        updated += (not was_created)
    print(f'Commodity yields seeded: {created} created, {updated} updated '
          f'({len(_YIELDS)} total).')
