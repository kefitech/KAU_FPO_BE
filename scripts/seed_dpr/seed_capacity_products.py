"""
Seed KAU spec §2.3.5 + §2.3.9 master data.

Includes:
    - DPRCapacityUnit (§2.3.9 A — 13 units)
    - DPRCapacityBasis (§2.3.9 A — 7 time bases)
    - DPRProductType (§2.3.5 — 4 types)
    - DPRProductCategory (§2.3.5 — high-level groupings)

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/seed_dpr/seed_capacity_products.py').read())
    seed_capacity_products()
    "
"""


def _upsert(model, rows):
    created = updated = 0
    for i, data in enumerate(rows):
        code = data.pop('code')
        _, is_new = model.objects.update_or_create(
            code=code, defaults={**data, 'order': data.get('order', i * 10)},
        )
        created += is_new; updated += (not is_new)
    print(f'  {model.__name__:32s} → {created} created, {updated} updated')


def seed_capacity_units():
    from apps.database.models import DPRCapacityUnit
    _upsert(DPRCapacityUnit, [
        {'code': 'kg',           'label_en': 'Kilograms (kg)'},
        {'code': 'mt',           'label_en': 'Metric Tonnes (MT)'},
        {'code': 'quintal',      'label_en': 'Quintal'},
        {'code': 'tonnes',       'label_en': 'Tonnes'},
        {'code': 'number',       'label_en': 'Number'},
        {'code': 'litres',       'label_en': 'Litres'},
        {'code': 'cubic_metres', 'label_en': 'Cubic Metres'},
        {'code': 'bags',         'label_en': 'Bags'},
        {'code': 'boxes',        'label_en': 'Boxes'},
        {'code': 'crates',       'label_en': 'Crates'},
        {'code': 'trays',        'label_en': 'Trays'},
        {'code': 'units',        'label_en': 'Units'},
        {'code': 'customers',    'label_en': 'Customers'},
        {'code': 'services',     'label_en': 'Services'},
        {'code': 'other',        'label_en': 'Others'},
    ])


def seed_capacity_basis():
    from apps.database.models import DPRCapacityBasis
    _upsert(DPRCapacityBasis, [
        {'code': 'per_hour',   'label_en': 'Per Hour'},
        {'code': 'per_shift',  'label_en': 'Per Shift'},
        {'code': 'per_day',    'label_en': 'Per Day'},
        {'code': 'per_week',   'label_en': 'Per Week'},
        {'code': 'per_month',  'label_en': 'Per Month'},
        {'code': 'per_season', 'label_en': 'Per Season'},
        {'code': 'per_year',   'label_en': 'Per Year'},
    ])


def seed_product_types():
    """Spec §2.3.5 — Product Type dropdown."""
    from apps.database.models import DPRProductType
    _upsert(DPRProductType, [
        {'code': 'finished',       'label_en': 'Finished Product'},
        {'code': 'intermediate',   'label_en': 'Intermediate Product'},
        {'code': 'by_product',     'label_en': 'By-product'},
        {'code': 'service',        'label_en': 'Service'},
    ])


def seed_product_categories():
    """Spec §2.3.5 — Product Category dropdown."""
    from apps.database.models import DPRProductCategory
    _upsert(DPRProductCategory, [
        {'code': 'grain_cereal',       'label_en': 'Grains & Cereals'},
        {'code': 'pulses',             'label_en': 'Pulses'},
        {'code': 'oilseeds',           'label_en': 'Oilseeds'},
        {'code': 'vegetables',         'label_en': 'Vegetables'},
        {'code': 'fruits',             'label_en': 'Fruits'},
        {'code': 'spices',             'label_en': 'Spices & Condiments'},
        {'code': 'plantation',         'label_en': 'Plantation Crops'},
        {'code': 'flowers',            'label_en': 'Flowers'},
        {'code': 'medicinal_aromatic', 'label_en': 'Medicinal & Aromatic Plants'},
        {'code': 'livestock_prod',     'label_en': 'Livestock Products (Milk, Meat, Egg)'},
        {'code': 'fish_marine',        'label_en': 'Fish & Marine Products'},
        {'code': 'processed_food',     'label_en': 'Processed Food'},
        {'code': 'packaged_beverage',  'label_en': 'Packaged Beverages'},
        {'code': 'organic_input',      'label_en': 'Organic / Bio-inputs'},
        {'code': 'seeds_planting',     'label_en': 'Seeds & Planting Material'},
        {'code': 'feed_fodder',        'label_en': 'Feed & Fodder'},
        {'code': 'agri_service',       'label_en': 'Agri Services'},
        {'code': 'other',              'label_en': 'Others'},
    ])


def seed_capacity_products():
    print('Seeding capacity & products master data...')
    seed_capacity_units()
    seed_capacity_basis()
    seed_product_types()
    seed_product_categories()
    print('Done.')
