"""
Seed KAU spec §2.2 + §2.3.2 + §2.3.3 + §2.3.7 master data.

Includes:
    - DPRProjectType (§2.2 field 2)
    - DPRProjectObjective (§2.2 field 6)
    - DPRProjectOutcome (§2.2 field 7)
    - DPRNatureOfBusiness (§2.3.3 — 14 options)
    - DPRProjectRationale (§2.3.7 — 29 reasons)
    - DPRComponent (§2.3.2 — 34 components across 6 groups)

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/seed_dpr/seed_project_definition.py').read())
    seed_project_definition()
    "
"""


def _upsert(model, rows):
    """Idempotent seed helper. Rows must include 'code'."""
    created = updated = 0
    for i, data in enumerate(rows):
        code = data.pop('code')
        obj, is_new = model.objects.update_or_create(
            code=code, defaults={**data, 'order': data.get('order', i * 10)},
        )
        created += is_new
        updated += (not is_new)
    print(f'  {model.__name__:32s} → {created} created, {updated} updated')


def seed_project_types():
    from apps.database.models import DPRProjectType
    _upsert(DPRProjectType, [
        {'code': 'new',                     'label_en': 'New Project'},
        {'code': 'expansion',               'label_en': 'Expansion'},
        {'code': 'diversification',         'label_en': 'Diversification'},
        {'code': 'modernisation',           'label_en': 'Modernisation'},
        {'code': 'value_addition',          'label_en': 'Value Addition'},
        {'code': 'infrastructure_dev',      'label_en': 'Infrastructure Development'},
        {'code': 'other',                   'label_en': 'Other'},
    ])


def seed_project_objectives():
    from apps.database.models import DPRProjectObjective
    _upsert(DPRProjectObjective, [
        {'code': 'increase_income',              'label_en': 'Increase farmers’ income'},
        {'code': 'value_addition',               'label_en': 'Value addition to primary produce'},
        {'code': 'reduce_post_harvest_loss',     'label_en': 'Reduce post-harvest losses'},
        {'code': 'improve_market_access',        'label_en': 'Improve market access'},
        {'code': 'employment_generation',        'label_en': 'Employment generation'},
        {'code': 'export_promotion',             'label_en': 'Export promotion'},
        {'code': 'capacity_building',            'label_en': 'Capacity building of members'},
        {'code': 'infrastructure_creation',      'label_en': 'Infrastructure creation'},
        {'code': 'improve_quality',              'label_en': 'Improve product quality'},
        {'code': 'reduce_intermediary',          'label_en': 'Reduce dependence on intermediaries'},
        {'code': 'strengthen_supply_chain',      'label_en': 'Strengthen supply chain'},
        {'code': 'improve_price_realisation',    'label_en': 'Improve price realisation'},
        {'code': 'promote_sustainability',       'label_en': 'Promote sustainable agriculture'},
        {'code': 'other',                        'label_en': 'Other'},
    ])


def seed_project_outcomes():
    from apps.database.models import DPRProjectOutcome
    _upsert(DPRProjectOutcome, [
        {'code': 'increased_farmer_income',      'label_en': 'Increased farmer income'},
        {'code': 'jobs_created',                 'label_en': 'Direct & indirect employment created'},
        {'code': 'reduced_wastage',              'label_en': 'Reduced post-harvest wastage'},
        {'code': 'better_market_access',         'label_en': 'Better market access for members'},
        {'code': 'value_added_products',         'label_en': 'Value-added products commercialised'},
        {'code': 'export_earnings',              'label_en': 'Export earnings generated'},
        {'code': 'improved_quality',             'label_en': 'Improved product quality'},
        {'code': 'brand_recognition',            'label_en': 'Brand recognition established'},
        {'code': 'strengthened_fpo',             'label_en': 'Strengthened FPO institutional capacity'},
        {'code': 'reduced_intermediation',       'label_en': 'Reduced intermediation'},
        {'code': 'women_participation',          'label_en': 'Increased women participation'},
        {'code': 'sustainable_practices',        'label_en': 'Adoption of sustainable practices'},
        {'code': 'other',                        'label_en': 'Other'},
    ])


def seed_nature_of_business():
    """Spec §2.3.3 — 14 multi-select options."""
    from apps.database.models import DPRNatureOfBusiness
    _upsert(DPRNatureOfBusiness, [
        {'code': 'primary_production',   'label_en': 'Primary Production'},
        {'code': 'aggregation',          'label_en': 'Aggregation / Procurement'},
        {'code': 'processing',           'label_en': 'Processing'},
        {'code': 'value_addition',       'label_en': 'Value Addition'},
        {'code': 'storage',              'label_en': 'Storage'},
        {'code': 'packaging',            'label_en': 'Packaging'},
        {'code': 'marketing',            'label_en': 'Marketing'},
        {'code': 'trading',              'label_en': 'Trading'},
        {'code': 'retail_sales',         'label_en': 'Retail Sales'},
        {'code': 'input_supply',         'label_en': 'Input Supply'},
        {'code': 'service_delivery',     'label_en': 'Service Delivery'},
        {'code': 'custom_hiring',        'label_en': 'Custom Hiring Services'},
        {'code': 'export',               'label_en': 'Export'},
        {'code': 'integrated_enterprise', 'label_en': 'Integrated Enterprise'},
        {'code': 'other',                'label_en': 'Others'},
    ])


def seed_project_rationales():
    """Spec §2.3.7 — 29 rationale reasons (multi-select with justification per reason)."""
    from apps.database.models import DPRProjectRationale
    _upsert(DPRProjectRationale, [
        {'code': 'reduce_post_harvest_losses',      'label_en': 'Reduce post-harvest losses'},
        {'code': 'increase_farmers_income',         'label_en': 'Increase farmers’ income'},
        {'code': 'value_addition',                  'label_en': 'Value addition'},
        {'code': 'improve_market_access',           'label_en': 'Improve market access'},
        {'code': 'export_opportunity',              'label_en': 'Export opportunity'},
        {'code': 'improve_product_quality',         'label_en': 'Improve product quality'},
        {'code': 'branding',                        'label_en': 'Branding'},
        {'code': 'packaging',                       'label_en': 'Packaging'},
        {'code': 'increase_processing_capacity',    'label_en': 'Increase processing capacity'},
        {'code': 'reduce_transportation_cost',      'label_en': 'Reduce transportation cost'},
        {'code': 'storage_requirement',             'label_en': 'Storage requirement'},
        {'code': 'reduce_wastage',                  'label_en': 'Reduce wastage'},
        {'code': 'diversification',                 'label_en': 'Diversification'},
        {'code': 'better_price_realization',        'label_en': 'Better price realization'},
        {'code': 'employment_generation',           'label_en': 'Employment generation'},
        {'code': 'member_demand',                   'label_en': 'Member demand'},
        {'code': 'government_support',              'label_en': 'Government support'},
        {'code': 'existing_business_expansion',     'label_en': 'Existing business expansion'},
        {'code': 'technology_upgradation',          'label_en': 'Technology upgradation'},
        {'code': 'import_substitution',             'label_en': 'Import substitution'},
        {'code': 'climate_resilience',              'label_en': 'Climate resilience'},
        {'code': 'organic_natural_farming',         'label_en': 'Organic / Natural farming promotion'},
        {'code': 'reduce_dependence_intermediaries', 'label_en': 'Reduce dependence on intermediaries'},
        {'code': 'improve_storage_logistics',       'label_en': 'Improve storage and logistics'},
        {'code': 'improve_quality_standards',       'label_en': 'Improve quality standards'},
        {'code': 'reduce_production_cost',          'label_en': 'Reduce production cost'},
        {'code': 'increase_processing_efficiency',  'label_en': 'Increase processing efficiency'},
        {'code': 'strengthen_member_services',      'label_en': 'Strengthen member services'},
        {'code': 'improve_market_competitiveness',  'label_en': 'Improve market competitiveness'},
        {'code': 'promote_sustainable_agriculture', 'label_en': 'Promote sustainable agriculture'},
        {'code': 'other',                           'label_en': 'Others'},
    ])


def seed_project_components():
    """
    Spec §2.3.2 — Project components across 6 groups.
    Selection drives dynamic questionnaire (Ch 1.7.2, 6.3-6.4).
    """
    from apps.database.models import DPRComponent
    G = DPRComponent.Group

    rows = []

    # Group 1 — Primary Production
    for i, (code, label) in enumerate([
        ('crop_production',        'Crop Production'),
        ('horticulture',           'Horticulture'),
        ('plantation_crops',       'Plantation Crops'),
        ('protected_cultivation',  'Protected Cultivation'),
        ('seed_production',        'Seed Production'),
        ('nursery',                'Nursery'),
        ('livestock',              'Livestock'),
        ('fisheries_aquaculture',  'Fisheries & Aquaculture'),
        ('primary_prod_other',     'Others (Primary Production)'),
    ]):
        rows.append({'code': code, 'label_en': label, 'group': G.PRIMARY_PRODUCTION, 'order': i})

    # Group 2 — Processing & Value Addition
    for i, (code, label) in enumerate([
        ('primary_processing',        'Primary Processing'),
        ('food_processing',           'Food Processing'),
        ('value_addition',            'Value Addition'),
        ('feed_manufacturing',        'Feed Manufacturing'),
        ('organic_bio_input_prod',    'Organic / Bio-input Production'),
        ('processing_other',          'Others (Processing)'),
    ]):
        rows.append({'code': code, 'label_en': label, 'group': G.PROCESSING_VALUE_ADD, 'order': i})

    # Group 3 — Storage & Post-Harvest
    for i, (code, label) in enumerate([
        ('collection_centre',   'Collection Centre'),
        ('pack_house',          'Pack House'),
        ('warehouse',           'Warehouse'),
        ('cold_storage',        'Cold Storage'),
        ('ripening_chamber',    'Ripening Chamber'),
        ('dry_storage',         'Dry Storage'),
        ('storage_other',       'Others (Storage)'),
    ]):
        rows.append({'code': code, 'label_en': label, 'group': G.STORAGE_POST_HARVEST, 'order': i})

    # Group 4 — Marketing & Business Development
    for i, (code, label) in enumerate([
        ('wholesale_marketing',  'Wholesale Marketing'),
        ('retail_outlet',        'Retail Outlet'),
        ('e_commerce',           'E-commerce'),
        ('export',               'Export'),
        ('branding_packaging',   'Branding & Packaging'),
        ('marketing_other',      'Others (Marketing)'),
    ]):
        rows.append({'code': code, 'label_en': label, 'group': G.MARKETING_BUSINESS_DEV, 'order': i})

    # Group 5 — Service-Based Enterprises
    for i, (code, label) in enumerate([
        ('agri_input_centre',           'Agri Input Centre'),
        ('custom_hiring_centre',        'Custom Hiring Centre'),
        ('farm_machinery_bank',         'Farm Machinery Bank'),
        ('soil_testing_lab',            'Soil Testing / Laboratory'),
        ('training_extension_centre',   'Training & Extension Centre'),
        ('service_other',               'Others (Service)'),
    ]):
        rows.append({'code': code, 'label_en': label, 'group': G.SERVICE_ENTERPRISES, 'order': i})

    # Group 6 — Supporting Infrastructure
    for i, (code, label) in enumerate([
        ('administrative_building',      'Administrative Building'),
        ('processing_building',          'Processing Building'),
        ('utility_infrastructure',       'Utility Infrastructure'),
        ('renewable_energy_system',      'Renewable Energy System'),
        ('internal_roads_site_dev',      'Internal Roads & Site Development'),
        ('supporting_infra_other',       'Others (Supporting Infrastructure)'),
    ]):
        rows.append({'code': code, 'label_en': label, 'group': G.SUPPORTING_INFRA, 'order': i})

    _upsert(DPRComponent, rows)


def seed_project_definition():
    """Run all project-definition group seeds."""
    print('Seeding project-definition master data...')
    seed_project_types()
    seed_project_objectives()
    seed_project_outcomes()
    seed_nature_of_business()
    seed_project_rationales()
    seed_project_components()
    print('Done.')
