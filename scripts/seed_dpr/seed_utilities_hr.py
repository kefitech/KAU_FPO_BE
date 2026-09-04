"""
Seed KAU spec §2.3.16 (Utilities) + §2.3.17 (HR) master data.

Includes:
    - DPRFuelType (§2.3.16 C — 10 fuel types)
    - DPRWasteType (§2.3.16 F — 8 waste types)
    - DPRRenewableInitiative (§2.3.16 J — 8 initiatives)
    - DPRTrainingArea (§2.3.17 E — 9 training areas)
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


def seed_fuel_types():
    """Spec §2.3.16 C — 10 fuel types."""
    from apps.database.models import DPRFuelType
    _upsert(DPRFuelType, [
        {'code': 'diesel',       'label_en': 'Diesel'},
        {'code': 'petrol',       'label_en': 'Petrol'},
        {'code': 'lpg',          'label_en': 'LPG'},
        {'code': 'png',          'label_en': 'PNG (Piped Natural Gas)'},
        {'code': 'firewood',     'label_en': 'Firewood'},
        {'code': 'biomass',      'label_en': 'Biomass'},
        {'code': 'briquettes',   'label_en': 'Briquettes'},
        {'code': 'furnace_oil',  'label_en': 'Furnace Oil'},
        {'code': 'biogas',       'label_en': 'Biogas'},
        {'code': 'other',        'label_en': 'Others'},
    ])


def seed_waste_types():
    """Spec §2.3.16 F — 8 waste types."""
    from apps.database.models import DPRWasteType
    _upsert(DPRWasteType, [
        {'code': 'organic',       'label_en': 'Organic Waste'},
        {'code': 'solid',         'label_en': 'Solid Waste'},
        {'code': 'liquid',        'label_en': 'Liquid Waste'},
        {'code': 'plastic',       'label_en': 'Plastic Waste'},
        {'code': 'hazardous',     'label_en': 'Hazardous Waste'},
        {'code': 'packaging',     'label_en': 'Packaging Waste'},
        {'code': 'wastewater',    'label_en': 'Wastewater'},
        {'code': 'other',         'label_en': 'Others'},
    ])


def seed_renewable_initiatives():
    """Spec §2.3.16 J — 8 renewable energy initiatives."""
    from apps.database.models import DPRRenewableInitiative
    _upsert(DPRRenewableInitiative, [
        {'code': 'solar_power',            'label_en': 'Solar Power'},
        {'code': 'solar_water_heater',     'label_en': 'Solar Water Heater'},
        {'code': 'biogas_plant',           'label_en': 'Biogas Plant'},
        {'code': 'biomass_gasifier',       'label_en': 'Biomass Gasifier'},
        {'code': 'wind_energy',            'label_en': 'Wind Energy'},
        {'code': 'rainwater_harvesting',   'label_en': 'Rainwater Harvesting'},
        {'code': 'energy_efficient_eqp',   'label_en': 'Energy Efficient Equipment'},
        {'code': 'other',                  'label_en': 'Others'},
    ])


def seed_training_areas():
    """Spec §2.3.17 E — 9 training areas."""
    from apps.database.models import DPRTrainingArea
    _upsert(DPRTrainingArea, [
        {'code': 'machine_operation',    'label_en': 'Machine Operation'},
        {'code': 'quality_control',      'label_en': 'Quality Control'},
        {'code': 'food_safety',          'label_en': 'Food Safety'},
        {'code': 'financial_management', 'label_en': 'Financial Management'},
        {'code': 'marketing',            'label_en': 'Marketing'},
        {'code': 'digital_systems',      'label_en': 'Digital Systems'},
        {'code': 'safety_procedures',    'label_en': 'Safety Procedures'},
        {'code': 'maintenance',          'label_en': 'Maintenance'},
        {'code': 'other',                'label_en': 'Others'},
    ])


def seed_utilities_hr():
    print('Seeding utilities & HR master data...')
    seed_fuel_types()
    seed_waste_types()
    seed_renewable_initiatives()
    seed_training_areas()
    print('Done.')
