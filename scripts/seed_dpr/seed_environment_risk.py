"""
Seed KAU spec §2.3.20 (Environmental) + §2.3.22 (Risk) master data.

Includes:
    - DPREnvironmentalImpact (§2.3.20 A — 10 impact categories)
    - DPRClimateRisk (§2.3.20 C — 8 climate risks)
    - DPRRiskCategory (§2.3.22 — 6 risk groupings)
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


def seed_environmental_impacts():
    """Spec §2.3.20 A — 10 environmental impact types."""
    from apps.database.models import DPREnvironmentalImpact
    _upsert(DPREnvironmentalImpact, [
        {'code': 'air_emissions',   'label_en': 'Air Emissions'},
        {'code': 'dust',            'label_en': 'Dust'},
        {'code': 'noise',           'label_en': 'Noise'},
        {'code': 'wastewater',      'label_en': 'Wastewater'},
        {'code': 'solid_waste',     'label_en': 'Solid Waste'},
        {'code': 'organic_waste',   'label_en': 'Organic Waste'},
        {'code': 'plastic_waste',   'label_en': 'Plastic Waste'},
        {'code': 'hazardous_waste', 'label_en': 'Hazardous Waste'},
        {'code': 'odour',           'label_en': 'Odour'},
        {'code': 'other',           'label_en': 'Others'},
    ])


def seed_climate_risks():
    """Spec §2.3.20 C — 8 climate risks."""
    from apps.database.models import DPRClimateRisk
    _upsert(DPRClimateRisk, [
        {'code': 'flood',            'label_en': 'Flood'},
        {'code': 'drought',          'label_en': 'Drought'},
        {'code': 'cyclone',          'label_en': 'Cyclone'},
        {'code': 'heat_stress',      'label_en': 'Heat Stress'},
        {'code': 'salinity',         'label_en': 'Salinity'},
        {'code': 'pest_outbreak',    'label_en': 'Pest Outbreak'},
        {'code': 'disease_outbreak', 'label_en': 'Disease Outbreak'},
        {'code': 'other',            'label_en': 'Others'},
    ])


def seed_risk_categories():
    """Spec §2.3.22 — 6 risk category groupings."""
    from apps.database.models import DPRRiskCategory
    _upsert(DPRRiskCategory, [
        {'code': 'production',    'label_en': 'Production Risks'},
        {'code': 'market',        'label_en': 'Market Risks'},
        {'code': 'financial',     'label_en': 'Financial Risks'},
        {'code': 'institutional', 'label_en': 'Institutional Risks'},
        {'code': 'environmental', 'label_en': 'Environmental Risks'},
        {'code': 'regulatory',    'label_en': 'Regulatory Risks'},
    ])


def seed_environment_risk():
    print('Seeding environment & risk master data...')
    seed_environmental_impacts()
    seed_climate_risks()
    seed_risk_categories()
    print('Done.')
