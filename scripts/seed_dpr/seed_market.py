"""
Seed KAU spec §2.3.11 (Market Assessment) + §2.3.12 (Technology) master data.

Includes:
    - DPRMarketingChannel (§2.3.11 D — 16 channels)
    - DPRCustomerCategory (§2.3.11 A — 13 categories)
    - DPRBuyerType (§2.3.11 C — buyer types)
    - DPRPromotionalActivity (§2.3.11 G — 8 activities with is_digital flag)
    - DPRTechnologyReason (§2.3.12 B — 15+ reasons with requires_justification flag)
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


def seed_marketing_channels():
    """Spec §2.3.11 D — 16 marketing channels."""
    from apps.database.models import DPRMarketingChannel
    _upsert(DPRMarketingChannel, [
        {'code': 'farm_gate_sales',         'label_en': 'Farm Gate Sales'},
        {'code': 'collection_centre',       'label_en': 'Collection Centre'},
        {'code': 'wholesale_market',        'label_en': 'Wholesale Market'},
        {'code': 'retail_outlet',           'label_en': 'Retail Outlet'},
        {'code': 'supermarkets',            'label_en': 'Supermarkets'},
        {'code': 'institutional_buyers',    'label_en': 'Institutional Buyers'},
        {'code': 'hotels',                  'label_en': 'Hotels'},
        {'code': 'restaurants',             'label_en': 'Restaurants'},
        {'code': 'food_processing_ind',     'label_en': 'Food Processing Industries'},
        {'code': 'export',                  'label_en': 'Export'},
        {'code': 'e_commerce',              'label_en': 'E-commerce'},
        {'code': 'government_procurement',  'label_en': 'Government Procurement'},
        {'code': 'online_marketplace',      'label_en': 'Online Marketplace'},
        {'code': 'direct_consumer_sales',   'label_en': 'Direct Consumer Sales'},
        {'code': 'distributor_network',     'label_en': 'Distributor Network'},
        {'code': 'franchise',               'label_en': 'Franchise'},
        {'code': 'other',                   'label_en': 'Others'},
    ])


def seed_customer_categories():
    """Spec §2.3.11 A — 13 customer categories."""
    from apps.database.models import DPRCustomerCategory
    _upsert(DPRCustomerCategory, [
        {'code': 'individual_consumers',  'label_en': 'Individual Consumers'},
        {'code': 'farmers',               'label_en': 'Farmers'},
        {'code': 'fpos',                  'label_en': 'Farmer Producer Organisations (FPOs)'},
        {'code': 'cooperatives',          'label_en': 'Cooperatives'},
        {'code': 'retail_shops',          'label_en': 'Retail Shops'},
        {'code': 'wholesalers',           'label_en': 'Wholesalers'},
        {'code': 'processors',            'label_en': 'Processors'},
        {'code': 'industries',            'label_en': 'Industries'},
        {'code': 'exporters',             'label_en': 'Exporters'},
        {'code': 'government_agencies',   'label_en': 'Government Agencies'},
        {'code': 'institutions',          'label_en': 'Institutions'},
        {'code': 'online_customers',      'label_en': 'Online Customers'},
        {'code': 'other',                 'label_en': 'Others'},
    ])


def seed_buyer_types():
    """Spec §2.3.11 C — Buyer Category dropdown."""
    from apps.database.models import DPRBuyerType
    _upsert(DPRBuyerType, [
        {'code': 'retail_chain',          'label_en': 'Retail Chain'},
        {'code': 'supermarket',           'label_en': 'Supermarket'},
        {'code': 'wholesale',             'label_en': 'Wholesale Trader'},
        {'code': 'exporter',              'label_en': 'Exporter'},
        {'code': 'food_processor',        'label_en': 'Food Processor'},
        {'code': 'institutional',         'label_en': 'Institutional Buyer'},
        {'code': 'government',            'label_en': 'Government Agency'},
        {'code': 'hotel_restaurant',      'label_en': 'Hotel / Restaurant'},
        {'code': 'online_platform',       'label_en': 'Online Platform'},
        {'code': 'other',                 'label_en': 'Others'},
    ])


def seed_promotional_activities():
    """Spec §2.3.11 G — 8 activities. is_digital flag for AI content selection."""
    from apps.database.models import DPRPromotionalActivity
    _upsert(DPRPromotionalActivity, [
        {'code': 'print_media',        'label_en': 'Print Media',        'is_digital': False},
        {'code': 'social_media',       'label_en': 'Social Media',       'is_digital': True},
        {'code': 'digital_marketing',  'label_en': 'Digital Marketing',  'is_digital': True},
        {'code': 'exhibitions',        'label_en': 'Exhibitions',        'is_digital': False},
        {'code': 'trade_fairs',        'label_en': 'Trade Fairs',        'is_digital': False},
        {'code': 'buyer_seller_meets', 'label_en': 'Buyer-Seller Meets', 'is_digital': False},
        {'code': 'local_campaigns',    'label_en': 'Local Campaigns',    'is_digital': False},
        {'code': 'other',              'label_en': 'Others',             'is_digital': False},
    ])


def seed_intended_markets():
    """Spec §2.3.11 A — Intended Market scope (per product)."""
    from apps.database.models import DPRIntendedMarket
    _upsert(DPRIntendedMarket, [
        {'code': 'local',      'label_en': 'Local'},
        {'code': 'state',      'label_en': 'State'},
        {'code': 'regional',   'label_en': 'Regional'},
        {'code': 'national',   'label_en': 'National'},
        {'code': 'export',     'label_en': 'Export'},
        {'code': 'multiple',   'label_en': 'Multiple Markets'},
    ])


def seed_technology_reasons():
    """Spec §2.3.12 B — 15+ technology-selection reasons."""
    from apps.database.models import DPRTechnologyReason
    _upsert(DPRTechnologyReason, [
        {'code': 'higher_productivity',       'label_en': 'Higher Productivity'},
        {'code': 'better_product_quality',    'label_en': 'Better Product Quality'},
        {'code': 'lower_operating_cost',      'label_en': 'Lower Operating Cost'},
        {'code': 'lower_capital_cost',        'label_en': 'Lower Capital Cost'},
        {'code': 'energy_efficient',          'label_en': 'Energy Efficient'},
        {'code': 'labour_saving',             'label_en': 'Labour Saving'},
        {'code': 'environment_friendly',      'label_en': 'Environment Friendly'},
        {'code': 'export_standard',           'label_en': 'Export Standard'},
        {'code': 'market_requirement',        'label_en': 'Market Requirement'},
        {'code': 'govt_recommendation',       'label_en': 'Government Recommendation'},
        {'code': 'previous_experience',       'label_en': 'Previous Experience'},
        {'code': 'consultant_recommendation', 'label_en': 'Consultant Recommendation'},
        {'code': 'easy_maintenance',          'label_en': 'Easy Maintenance'},
        {'code': 'scalability',               'label_en': 'Scalability'},
        {'code': 'spare_parts_availability',  'label_en': 'Availability of Spare Parts'},
        {'code': 'other',                     'label_en': 'Others', 'requires_justification': True},
    ])


def seed_market():
    print('Seeding market & technology master data...')
    seed_marketing_channels()
    seed_customer_categories()
    seed_buyer_types()
    seed_promotional_activities()
    seed_intended_markets()
    seed_technology_reasons()
    print('Done.')
