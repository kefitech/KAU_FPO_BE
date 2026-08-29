"""
Seed KAU spec §2.3.6 + §2.3.13 + §2.3.14 + §2.3.15 master data.

Includes:
    - DPRLandOwnershipType (§2.3.6 C — 7 types)
    - DPRSiteStatus (§2.3.6 D — 6 statuses)
    - DPRBuildingType (§2.3.14 B — 19 types)
    - DPRCivilCategory (§2.3.14 C — site development items)
    - DPRMachineryCategory (§2.3.15 A — 12 categories with depreciation defaults)
    - DPRSupportingAsset (§2.3.15 H — supporting assets)
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


def seed_land_ownership_types():
    """Spec §2.3.6 C / §2.3.13 A — 7 ownership options."""
    from apps.database.models import DPRLandOwnershipType
    _upsert(DPRLandOwnershipType, [
        {'code': 'owned_fpo',            'label_en': 'Owned by FPO'},
        {'code': 'owned_members',        'label_en': 'Owned by Members'},
        {'code': 'leased',               'label_en': 'Leased'},
        {'code': 'rented',               'label_en': 'Rented'},
        {'code': 'government_land',      'label_en': 'Government Land'},
        {'code': 'proposed_purchase',    'label_en': 'Proposed to be Purchased'},
        {'code': 'other',                'label_en': 'Others'},
    ])


def seed_site_statuses():
    """Spec §2.3.6 D — 6 site statuses."""
    from apps.database.models import DPRSiteStatus
    _upsert(DPRSiteStatus, [
        {'code': 'existing_facility',       'label_en': 'Existing Facility'},
        {'code': 'vacant_land',             'label_en': 'Vacant Land'},
        {'code': 'under_construction',      'label_en': 'Under Construction'},
        {'code': 'existing_to_modify',      'label_en': 'Existing Building to be Modified'},
        {'code': 'existing_to_expand',      'label_en': 'Existing Building to be Expanded'},
        {'code': 'other',                   'label_en': 'Others'},
    ])


def seed_building_types():
    """Spec §2.3.14 B — 19 building types."""
    from apps.database.models import DPRBuildingType
    _upsert(DPRBuildingType, [
        {'code': 'administrative_office',    'label_en': 'Administrative Office'},
        {'code': 'processing_hall',          'label_en': 'Processing Hall'},
        {'code': 'storage_warehouse',        'label_en': 'Storage Warehouse'},
        {'code': 'cold_storage',             'label_en': 'Cold Storage'},
        {'code': 'pack_house',               'label_en': 'Pack House'},
        {'code': 'raw_material_store',       'label_en': 'Raw Material Store'},
        {'code': 'finished_goods_store',     'label_en': 'Finished Goods Store'},
        {'code': 'qc_lab',                   'label_en': 'Quality Control Laboratory'},
        {'code': 'training_hall',            'label_en': 'Training Hall'},
        {'code': 'staff_room',               'label_en': 'Staff Room'},
        {'code': 'toilet_block',             'label_en': 'Toilet Block'},
        {'code': 'security_cabin',           'label_en': 'Security Cabin'},
        {'code': 'utility_room',             'label_en': 'Utility Room'},
        {'code': 'generator_room',           'label_en': 'Generator Room'},
        {'code': 'electrical_room',          'label_en': 'Electrical Room'},
        {'code': 'parking_area',             'label_en': 'Parking Area'},
        {'code': 'loading_unloading',        'label_en': 'Loading / Unloading Platform'},
        {'code': 'other',                    'label_en': 'Others'},
    ])


def seed_civil_categories():
    """Spec §2.3.14 C — Site development category dropdown."""
    from apps.database.models import DPRCivilCategory
    _upsert(DPRCivilCategory, [
        {'code': 'land_development',      'label_en': 'Land Development'},
        {'code': 'site_levelling',        'label_en': 'Site Levelling'},
        {'code': 'internal_roads',        'label_en': 'Internal Roads'},
        {'code': 'compound_wall',         'label_en': 'Compound Wall'},
        {'code': 'gate',                  'label_en': 'Gate'},
        {'code': 'drainage_system',       'label_en': 'Drainage System'},
        {'code': 'parking_area',          'label_en': 'Parking Area'},
        {'code': 'borewell',              'label_en': 'Borewell'},
        {'code': 'water_tank',            'label_en': 'Water Tank'},
        {'code': 'septic_tank',           'label_en': 'Septic Tank'},
        {'code': 'rainwater_harvesting',  'label_en': 'Rainwater Harvesting'},
        {'code': 'fire_water_tank',       'label_en': 'Fire Water Tank'},
        {'code': 'other',                 'label_en': 'Others'},
    ])


def seed_machinery_categories():
    """
    Spec §2.3.15 A — 12 categories.
    Default depreciation rate feeds Ch 4.8 (calculation engine).
    """
    from apps.database.models import DPRMachineryCategory
    _upsert(DPRMachineryCategory, [
        {'code': 'processing',     'label_en': 'Processing',          'default_depreciation_rate_pct': 15, 'default_useful_life_years': 10},
        {'code': 'packaging',      'label_en': 'Packaging',           'default_depreciation_rate_pct': 15, 'default_useful_life_years': 10},
        {'code': 'material_handling', 'label_en': 'Material Handling', 'default_depreciation_rate_pct': 15, 'default_useful_life_years': 10},
        {'code': 'quality_control', 'label_en': 'Quality Control',    'default_depreciation_rate_pct': 10, 'default_useful_life_years': 10},
        {'code': 'cold_chain',     'label_en': 'Cold Chain',          'default_depreciation_rate_pct': 15, 'default_useful_life_years': 10},
        {'code': 'utility',        'label_en': 'Utility',             'default_depreciation_rate_pct': 10, 'default_useful_life_years': 15},
        {'code': 'agricultural',   'label_en': 'Agricultural',        'default_depreciation_rate_pct': 15, 'default_useful_life_years': 10},
        {'code': 'laboratory',     'label_en': 'Laboratory',          'default_depreciation_rate_pct': 10, 'default_useful_life_years': 10},
        {'code': 'office',         'label_en': 'Office',              'default_depreciation_rate_pct': 20, 'default_useful_life_years': 5},
        {'code': 'it',             'label_en': 'IT Equipment',        'default_depreciation_rate_pct': 33, 'default_useful_life_years': 3},
        {'code': 'vehicle',        'label_en': 'Vehicle',             'default_depreciation_rate_pct': 20, 'default_useful_life_years': 8},
        {'code': 'other',          'label_en': 'Others',              'default_depreciation_rate_pct': 10, 'default_useful_life_years': 10},
    ])


def seed_supporting_assets():
    """Spec §2.3.15 H — supporting asset list (~20)."""
    from apps.database.models import DPRSupportingAsset
    _upsert(DPRSupportingAsset, [
        {'code': 'trolleys',           'label_en': 'Trolleys'},
        {'code': 'pallets',            'label_en': 'Pallets'},
        {'code': 'storage_bins',       'label_en': 'Storage Bins'},
        {'code': 'racks',              'label_en': 'Racks'},
        {'code': 'crates',             'label_en': 'Crates'},
        {'code': 'weighing_scales',    'label_en': 'Weighing Scales'},
        {'code': 'forklifts',          'label_en': 'Forklifts'},
        {'code': 'conveyors',          'label_en': 'Conveyors'},
        {'code': 'hand_tools',         'label_en': 'Hand Tools'},
        {'code': 'safety_equipment',   'label_en': 'Safety Equipment'},
        {'code': 'fire_safety_eqp',    'label_en': 'Fire Safety Equipment'},
        {'code': 'office_furniture',   'label_en': 'Office Furniture'},
        {'code': 'computers',          'label_en': 'Computers'},
        {'code': 'printers',           'label_en': 'Printers'},
        {'code': 'cctv',               'label_en': 'CCTV'},
        {'code': 'ups',                'label_en': 'UPS'},
        {'code': 'dg_set',             'label_en': 'DG Set'},
        {'code': 'solar_equipment',    'label_en': 'Solar Equipment'},
        {'code': 'other_fixed_assets', 'label_en': 'Other Fixed Assets'},
    ])


def seed_infrastructure():
    print('Seeding infrastructure & machinery master data...')
    seed_land_ownership_types()
    seed_site_statuses()
    seed_building_types()
    seed_civil_categories()
    seed_machinery_categories()
    seed_supporting_assets()
    print('Done.')
