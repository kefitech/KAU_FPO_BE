"""
Seed KAU spec §2.3.10 (Raw Material) + §2.3.12 E (Quality Standards) master data.

Includes:
    - DPRRawMaterialSource (§2.3.10 A — 11 sources)
    - DPRProcurementModel (§2.3.10 A/C — 8 methods)
    - DPRQualityParameter (§2.3.10 D — 7 parameters)
    - DPRQualityStandard (§2.3.12 E — certifications)
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


def seed_raw_material_sources():
    """Spec §2.3.10 A — 11 sources."""
    from apps.database.models import DPRRawMaterialSource
    _upsert(DPRRawMaterialSource, [
        {'code': 'fpo_members',         'label_en': 'FPO Members'},
        {'code': 'local_farmers',       'label_en': 'Local Farmers'},
        {'code': 'local_market',        'label_en': 'Local Market'},
        {'code': 'wholesale_market',    'label_en': 'Wholesale Market'},
        {'code': 'government_agency',   'label_en': 'Government Agency'},
        {'code': 'contract_farming',    'label_en': 'Contract Farming'},
        {'code': 'other_fpo',           'label_en': 'Other FPO'},
        {'code': 'traders',             'label_en': 'Traders'},
        {'code': 'processing_industry', 'label_en': 'Processing Industry'},
        {'code': 'import',              'label_en': 'Import'},
        {'code': 'other',               'label_en': 'Others'},
    ])


def seed_procurement_models():
    """Spec §2.3.10 A/C — Procurement models & methods."""
    from apps.database.models import DPRProcurementModel
    _upsert(DPRProcurementModel, [
        {'code': 'direct_purchase',        'label_en': 'Direct Purchase'},
        {'code': 'aggregation',            'label_en': 'Aggregation'},
        {'code': 'contract_farming',       'label_en': 'Contract Farming'},
        {'code': 'collection_centre',      'label_en': 'Collection Centre'},
        {'code': 'through_members',        'label_en': 'Procurement through Members'},
        {'code': 'through_traders',        'label_en': 'Procurement through Traders'},
        {'code': 'government_procurement', 'label_en': 'Government Procurement'},
        {'code': 'combination',            'label_en': 'Combination'},
        {'code': 'other',                  'label_en': 'Others'},
    ])


def seed_quality_parameters():
    """Spec §2.3.10 D — 7 quality parameters."""
    from apps.database.models import DPRQualityParameter
    _upsert(DPRQualityParameter, [
        {'code': 'moisture',        'label_en': 'Moisture'},
        {'code': 'purity',          'label_en': 'Purity'},
        {'code': 'size',            'label_en': 'Size'},
        {'code': 'colour',          'label_en': 'Colour'},
        {'code': 'maturity',        'label_en': 'Maturity'},
        {'code': 'foreign_matter',  'label_en': 'Foreign Matter'},
        {'code': 'other',           'label_en': 'Others'},
    ])


def seed_quality_standards():
    """Spec §2.3.12 E — certification / quality standards multi-select."""
    from apps.database.models import DPRQualityStandard
    _upsert(DPRQualityStandard, [
        {'code': 'fssai',           'label_en': 'FSSAI'},
        {'code': 'agmark',          'label_en': 'AGMARK'},
        {'code': 'bis',             'label_en': 'BIS'},
        {'code': 'organic',         'label_en': 'Organic Certification'},
        {'code': 'india_organic',   'label_en': 'India Organic'},
        {'code': 'pgs',             'label_en': 'PGS (Participatory Guarantee System)'},
        {'code': 'globalgap',       'label_en': 'GlobalG.A.P.'},
        {'code': 'haccp',           'label_en': 'HACCP'},
        {'code': 'iso_22000',       'label_en': 'ISO 22000'},
        {'code': 'gmp',             'label_en': 'GMP (Good Manufacturing Practice)'},
        {'code': 'ghp',             'label_en': 'GHP (Good Hygiene Practice)'},
        {'code': 'export_cert',     'label_en': 'Export Certification'},
        {'code': 'other',           'label_en': 'Others'},
    ])


def seed_raw_material():
    print('Seeding raw material & quality master data...')
    seed_raw_material_sources()
    seed_procurement_models()
    seed_quality_parameters()
    seed_quality_standards()
    print('Done.')
