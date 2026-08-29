"""
Seed Kerala-Specific Commodities
================================

Adds Kerala-specific commodity rows into the SAME `core.MasterLookup` table
(category='commodity') that KAU's June 2026 base seed populated. No new
table, no duplicate list — every module (DPR §2.2, marketplace, GIS) already
FKs into MasterLookup, so these rows are usable everywhere immediately.

Adds:
  - Plantation / spice extras: cashew, coir, tea, vanilla, clove
  - Fisheries: marine fish, sardine, mackerel, tuna, shrimp, prawn,
               crab, mussel, oyster
  - Livestock: cattle (dairy), buffalo, goat, duck, rabbit
  - Sericulture: silk cocoon

All entries use `update_or_create` — safe to re-run. Both EN + ML
translations are seeded in the Translation table (category='commodity').
Display order continues from the last existing commodity so KAU's baseline
ordering stays stable.

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/seed_kerala_commodities.py').read())
    seed_kerala_commodities()
    "

Author: Athul Gopan kefi tech solutions
"""


KERALA_COMMODITIES = [
    # ── Plantation / spice extras missing from base list ──
    {'code': 'cashew',      'en': 'Cashew',                 'ml': 'കശുവണ്ടി'},
    {'code': 'coir',        'en': 'Coir (Coconut Fibre)',   'ml': 'കയർ'},
    {'code': 'tea',         'en': 'Tea',                    'ml': 'തേയില'},
    {'code': 'vanilla',     'en': 'Vanilla',                'ml': 'വാനില'},
    {'code': 'clove',       'en': 'Clove',                  'ml': 'ഗ്രാമ്പൂ'},

    # ── Fisheries & aquaculture — Kerala coast ──
    {'code': 'marine_fish', 'en': 'Marine Fish (Assorted)', 'ml': 'സമുദ്രമത്സ്യം (മിശ്ര)'},
    {'code': 'sardine',     'en': 'Sardine',                'ml': 'മത്തി'},
    {'code': 'mackerel',    'en': 'Mackerel',               'ml': 'അയല'},
    {'code': 'tuna',        'en': 'Tuna',                   'ml': 'ചൂര'},
    {'code': 'shrimp',      'en': 'Shrimp',                 'ml': 'ചെമ്മീൻ'},
    {'code': 'prawn',       'en': 'Prawn',                  'ml': 'കൊഞ്ച്'},
    {'code': 'crab',        'en': 'Crab',                   'ml': 'ഞണ്ട്'},
    {'code': 'mussel',      'en': 'Mussel',                 'ml': 'കല്ലുമ്മക്കായ'},
    {'code': 'oyster',      'en': 'Oyster',                 'ml': 'മുരു'},

    # ── Livestock ──
    {'code': 'cattle',      'en': 'Cattle (Dairy)',         'ml': 'കന്നുകാലി (പാൽ)'},
    {'code': 'buffalo',     'en': 'Buffalo',                'ml': 'എരുമ'},
    {'code': 'goat',        'en': 'Goat',                   'ml': 'ആട്'},
    {'code': 'duck',        'en': 'Duck',                   'ml': 'താറാവ്'},
    {'code': 'rabbit',      'en': 'Rabbit',                 'ml': 'മുയൽ'},

    # ── Sericulture ──
    {'code': 'silk_cocoon', 'en': 'Silk Cocoon',            'ml': 'പട്ട് കൊക്കൂൺ'},
]


def seed_kerala_commodities():
    from apps.core.models.generic import MasterLookup
    from apps.database.models import Language, Translation, TranslationCategory

    lang_en = Language.objects.get(code='en')
    lang_ml = Language.objects.get(code='ml')
    cat, _ = TranslationCategory.objects.get_or_create(
        code='commodity',
        defaults={
            'name':        'Commodity',
            'description': 'Agricultural commodities for FPO registration',
        },
    )

    # Continue display_order from where KAU's base seed ended so the
    # baseline ordering stays exactly as KAU authored it.
    last_order = (
        MasterLookup.objects
        .filter(category='commodity')
        .order_by('-display_order')
        .values_list('display_order', flat=True)
        .first()
        or -1
    )

    created = 0
    updated = 0
    for i, entry in enumerate(KERALA_COMMODITIES):
        _, was_created = MasterLookup.objects.update_or_create(
            category='commodity',
            code=entry['code'],
            defaults={
                'description':   entry.get('description', ''),
                'display_order': last_order + 1 + i,
                'is_active':     True,
                'metadata':      entry.get('metadata', {}),
            },
        )
        if was_created:
            created += 1
        else:
            updated += 1

        Translation.objects.update_or_create(
            category=cat, key=entry['code'], language=lang_en,
            defaults={'value': entry['en']},
        )
        Translation.objects.update_or_create(
            category=cat, key=entry['code'], language=lang_ml,
            defaults={'value': entry.get('ml', entry['en'])},
        )

    total = MasterLookup.objects.filter(category='commodity').count()
    print(
        f'Kerala commodities: {created} created, {updated} updated. '
        f'Total commodities now: {total}'
    )
