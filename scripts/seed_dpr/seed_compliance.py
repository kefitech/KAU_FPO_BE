"""
Seed KAU spec §2.3.19 (Statutory Approvals, Licences & Regulatory Compliance).

Grouped into 7 KAU categories:
    A. Business Registrations
    B. Project Approvals
    C. Environmental Compliance
    D. Food Safety & Quality
    E. Labour Compliance
    F. Insurance
    G. Legal / Pending Issues (not seeded — reported ad-hoc by FPO)

Each row includes `category`, `default_mandatory`, and `issuing_authority_default`.
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


def seed_statutory_registrations():
    from apps.database.models import DPRStatutoryRegistration
    C = DPRStatutoryRegistration.Category

    rows = [
        # A — Business Registrations (mandatory)
        {'code': 'fpo_registration',    'label_en': 'FPO / Producer Company Registration', 'category': C.BUSINESS, 'default_mandatory': True,  'issuing_authority_default': 'Registrar of Companies (RoC)'},
        {'code': 'pan',                 'label_en': 'PAN',                                  'category': C.BUSINESS, 'default_mandatory': True,  'issuing_authority_default': 'Income Tax Department'},
        {'code': 'gst',                 'label_en': 'GST Registration',                     'category': C.BUSINESS, 'default_mandatory': True,  'issuing_authority_default': 'GSTN'},
        {'code': 'tan',                 'label_en': 'TAN',                                  'category': C.BUSINESS, 'default_mandatory': False, 'issuing_authority_default': 'Income Tax Department'},
        {'code': 'udyam',               'label_en': 'UDYAM Registration',                   'category': C.BUSINESS, 'default_mandatory': False, 'issuing_authority_default': 'Ministry of MSME'},
        {'code': 'iec',                 'label_en': 'Import Export Code (IEC)',             'category': C.BUSINESS, 'default_mandatory': False, 'issuing_authority_default': 'DGFT'},
        {'code': 'apeda',               'label_en': 'APEDA Registration',                   'category': C.BUSINESS, 'default_mandatory': False, 'issuing_authority_default': 'APEDA'},
        {'code': 'spice_board',         'label_en': 'Spice Board Registration',             'category': C.BUSINESS, 'default_mandatory': False, 'issuing_authority_default': 'Spices Board of India'},
        {'code': 'coconut_dev_board',   'label_en': 'Coconut Development Board Registration', 'category': C.BUSINESS, 'default_mandatory': False, 'issuing_authority_default': 'Coconut Development Board'},
        {'code': 'rubber_board',        'label_en': 'Rubber Board Registration',            'category': C.BUSINESS, 'default_mandatory': False, 'issuing_authority_default': 'Rubber Board'},

        # B — Project Approvals
        {'code': 'building_permit',        'label_en': 'Building Permit',                'category': C.PROJECT, 'default_mandatory': True,  'issuing_authority_default': 'Local Body (Panchayat / Municipality)'},
        {'code': 'factory_licence',        'label_en': 'Factory Licence',                'category': C.PROJECT, 'default_mandatory': True,  'issuing_authority_default': 'Factory Inspector'},
        {'code': 'trade_licence',          'label_en': 'Trade Licence',                  'category': C.PROJECT, 'default_mandatory': True,  'issuing_authority_default': 'Local Body'},
        {'code': 'panchayat_licence',      'label_en': 'Panchayat / Municipality Licence','category': C.PROJECT, 'default_mandatory': True,  'issuing_authority_default': 'Local Body'},
        {'code': 'fire_noc',               'label_en': 'Fire NOC',                       'category': C.PROJECT, 'default_mandatory': False, 'issuing_authority_default': 'Fire & Rescue Services'},
        {'code': 'electrical_inspectorate', 'label_en': 'Electrical Inspectorate Approval', 'category': C.PROJECT, 'default_mandatory': False, 'issuing_authority_default': 'Electrical Inspectorate'},
        {'code': 'boiler_inspectorate',    'label_en': 'Boiler Inspectorate Approval',   'category': C.PROJECT, 'default_mandatory': False, 'issuing_authority_default': 'Boiler Inspectorate'},
        {'code': 'legal_metrology',        'label_en': 'Legal Metrology Certification',  'category': C.PROJECT, 'default_mandatory': False, 'issuing_authority_default': 'Legal Metrology Department'},
        {'code': 'ground_water_permit',    'label_en': 'Ground Water Permission',        'category': C.PROJECT, 'default_mandatory': False, 'issuing_authority_default': 'CGWA / State Ground Water Board'},
        {'code': 'explosive_licence',      'label_en': 'Explosive Licence',              'category': C.PROJECT, 'default_mandatory': False, 'issuing_authority_default': 'Chief Controller of Explosives'},

        # C — Environmental Compliance
        {'code': 'ec',                     'label_en': 'Environmental Clearance',        'category': C.ENVIRONMENTAL, 'default_mandatory': False, 'issuing_authority_default': 'MoEFCC / SEIAA'},
        {'code': 'consent_establish',      'label_en': 'Consent to Establish (CTE)',     'category': C.ENVIRONMENTAL, 'default_mandatory': True,  'issuing_authority_default': 'KSPCB'},
        {'code': 'consent_operate',        'label_en': 'Consent to Operate (CTO)',       'category': C.ENVIRONMENTAL, 'default_mandatory': True,  'issuing_authority_default': 'KSPCB'},
        {'code': 'waste_disposal_auth',    'label_en': 'Waste Disposal Authorisation',   'category': C.ENVIRONMENTAL, 'default_mandatory': False, 'issuing_authority_default': 'KSPCB'},
        {'code': 'plastic_waste_rules',    'label_en': 'Plastic Waste Rules Compliance', 'category': C.ENVIRONMENTAL, 'default_mandatory': False, 'issuing_authority_default': 'KSPCB'},
        {'code': 'biomedical_waste',       'label_en': 'Biomedical Waste Authorisation', 'category': C.ENVIRONMENTAL, 'default_mandatory': False, 'issuing_authority_default': 'KSPCB'},
        {'code': 'e_waste',                'label_en': 'E-Waste Authorisation',          'category': C.ENVIRONMENTAL, 'default_mandatory': False, 'issuing_authority_default': 'KSPCB'},

        # D — Food Safety & Quality
        {'code': 'fssai',                  'label_en': 'FSSAI Licence',                  'category': C.FOOD_QUALITY, 'default_mandatory': True,  'issuing_authority_default': 'FSSAI'},
        {'code': 'organic_cert',           'label_en': 'Organic Certification',          'category': C.FOOD_QUALITY, 'default_mandatory': False, 'issuing_authority_default': 'Accredited Certification Body'},
        {'code': 'haccp',                  'label_en': 'HACCP',                          'category': C.FOOD_QUALITY, 'default_mandatory': False, 'issuing_authority_default': 'Accredited Certification Body'},
        {'code': 'iso_22000',              'label_en': 'ISO 22000',                      'category': C.FOOD_QUALITY, 'default_mandatory': False, 'issuing_authority_default': 'Accredited Certification Body'},
        {'code': 'gmp',                    'label_en': 'GMP',                            'category': C.FOOD_QUALITY, 'default_mandatory': False, 'issuing_authority_default': 'Accredited Certification Body'},
        {'code': 'ghp',                    'label_en': 'GHP',                            'category': C.FOOD_QUALITY, 'default_mandatory': False, 'issuing_authority_default': 'Accredited Certification Body'},
        {'code': 'pgs',                    'label_en': 'PGS Certification',              'category': C.FOOD_QUALITY, 'default_mandatory': False, 'issuing_authority_default': 'PGS India Council'},
        {'code': 'india_organic',          'label_en': 'India Organic',                  'category': C.FOOD_QUALITY, 'default_mandatory': False, 'issuing_authority_default': 'APEDA / NPOP'},
        {'code': 'globalgap',              'label_en': 'GlobalG.A.P.',                   'category': C.FOOD_QUALITY, 'default_mandatory': False, 'issuing_authority_default': 'Accredited Certification Body'},

        # E — Labour Compliance
        {'code': 'minimum_wages',          'label_en': 'Minimum Wages Compliance',       'category': C.LABOUR, 'default_mandatory': True,  'issuing_authority_default': 'Labour Department'},
        {'code': 'epf',                    'label_en': 'EPF Registration',               'category': C.LABOUR, 'default_mandatory': True,  'issuing_authority_default': 'EPFO'},
        {'code': 'esi',                    'label_en': 'ESI Registration',               'category': C.LABOUR, 'default_mandatory': True,  'issuing_authority_default': 'ESIC'},
        {'code': 'bonus_act',              'label_en': 'Bonus Act Compliance',           'category': C.LABOUR, 'default_mandatory': False, 'issuing_authority_default': 'Labour Department'},
        {'code': 'gratuity',               'label_en': 'Gratuity Compliance',            'category': C.LABOUR, 'default_mandatory': False, 'issuing_authority_default': 'Labour Department'},
        {'code': 'contract_labour',        'label_en': 'Contract Labour Licence',        'category': C.LABOUR, 'default_mandatory': False, 'issuing_authority_default': 'Labour Department'},
        {'code': 'shops_establishments',   'label_en': 'Shops & Establishments Registration', 'category': C.LABOUR, 'default_mandatory': False, 'issuing_authority_default': 'Labour Department'},

        # F — Insurance
        {'code': 'building_insurance',     'label_en': 'Building Insurance',             'category': C.INSURANCE, 'default_mandatory': False, 'issuing_authority_default': 'General Insurance Company'},
        {'code': 'machinery_insurance',    'label_en': 'Machinery Insurance',            'category': C.INSURANCE, 'default_mandatory': False, 'issuing_authority_default': 'General Insurance Company'},
        {'code': 'stock_insurance',        'label_en': 'Stock Insurance',                'category': C.INSURANCE, 'default_mandatory': False, 'issuing_authority_default': 'General Insurance Company'},
        {'code': 'fire_insurance',        'label_en': 'Fire Insurance',                  'category': C.INSURANCE, 'default_mandatory': False, 'issuing_authority_default': 'General Insurance Company'},
        {'code': 'vehicle_insurance',      'label_en': 'Vehicle Insurance',              'category': C.INSURANCE, 'default_mandatory': False, 'issuing_authority_default': 'General Insurance Company'},
        {'code': 'employee_insurance',     'label_en': 'Employee Insurance',             'category': C.INSURANCE, 'default_mandatory': False, 'issuing_authority_default': 'General Insurance Company'},
        {'code': 'public_liability',       'label_en': 'Public Liability Insurance',     'category': C.INSURANCE, 'default_mandatory': False, 'issuing_authority_default': 'General Insurance Company'},
        {'code': 'product_liability',      'label_en': 'Product Liability Insurance',    'category': C.INSURANCE, 'default_mandatory': False, 'issuing_authority_default': 'General Insurance Company'},
    ]
    _upsert(DPRStatutoryRegistration, rows)


def seed_compliance():
    print('Seeding compliance master data...')
    seed_statutory_registrations()
    print('Done.')
