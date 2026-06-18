"""
Seed Schemes & Subsidies
==========================
13 government schemes from KAU RCD document (5. Schemes – initial list.docx)

Usage:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/seed_schemes.py').read())
    seed_schemes()
    "
"""

from apps.database.models.schemes import Scheme, SchemeCategory


SCHEMES = [
    {
        'order': 1,
        'name_en': 'Formation and Promotion of 10,000 Farmer Producer Organizations (FPOs)',
        'name_ml': '10,000 കർഷക ഉൽപാദക സംഘടനകളുടെ (FPO) രൂപീകരണവും പ്രോത്സാഹനവും',
        'category': SchemeCategory.CAPACITY,
        'administering_body': 'Ministry of Agriculture & Farmers Welfare, GoI through SFAC, NABARD, NCDC and CBBOs',
        'objective': 'Support newly formed or existing FPOs through formation, nurturing, capacity building and handholding.',
        'eligibility': 'Newly formed or existing FPOs; registered as Producer Company, Cooperative Society, Society, or other eligible legal entity; must consist primarily of producer members.',
        'benefit_details': 'Financial support for formation and nurturing; capacity building and training; professional handholding through CBBOs; assistance for business planning and governance.',
        'application_process': 'Routed through implementing agencies, CBBOs, NABARD, SFAC, or NCDC.',
        'official_link': 'https://sfacindia.com',
    },
    {
        'order': 2,
        'name_en': 'Equity Grant Fund Scheme',
        'name_ml': 'ഇക്വിറ്റി ഗ്രാന്റ് ഫണ്ട് പദ്ധതി',
        'category': SchemeCategory.CREDIT,
        'administering_body': 'Small Farmers\' Agribusiness Consortium (SFAC)',
        'objective': 'Strengthen the net worth and borrowing capacity of Farmer Producer Companies.',
        'eligibility': 'Registered Farmer Producer Companies; member farmers must contribute share capital; must satisfy SFAC eligibility norms.',
        'benefit_details': 'Matching equity grant up to prescribed limits; strengthens net worth and borrowing capacity; improves creditworthiness.',
        'application_process': 'Apply through SFAC with prescribed documents and audited records.',
        'official_link': 'https://sfacindia.com/procedure_for_Equity_Grant.aspx',
    },
    {
        'order': 3,
        'name_en': 'Credit Guarantee Fund Scheme for FPOs',
        'name_ml': 'കർഷക ഉൽപാദക സംഘടനകൾക്കുള്ള ക്രെഡിറ്റ് ഗ്യാരണ്ടി ഫണ്ട് പദ്ധതി',
        'category': SchemeCategory.CREDIT,
        'administering_body': 'SFAC',
        'objective': 'Improve access to collateral-free credit for FPOs by providing guarantee cover to lending institutions.',
        'eligibility': 'Registered FPOs seeking institutional loans; loan sanctioned by eligible lending institutions.',
        'benefit_details': 'Credit guarantee cover to lending institutions; improves access to collateral-free credit; reduces lending risk for banks.',
        'application_process': 'Routed through participating banks and SFAC.',
        'official_link': 'https://www.nabard.org/pdf/cgsfpo.pdf',
    },
    {
        'order': 4,
        'name_en': 'Agriculture Infrastructure Fund (AIF)',
        'name_ml': 'കാർഷിക അടിസ്ഥാന സൗകര്യ നിധി',
        'category': SchemeCategory.INFRA,
        'administering_body': 'Ministry of Agriculture & Farmers Welfare, Government of India',
        'objective': 'Provide medium and long-term debt financing for post-harvest management and agri-infrastructure.',
        'eligibility': 'FPOs, PACS, Cooperatives, Agri entrepreneurs, Startups.',
        'benefit_details': 'Medium and long-term debt financing; interest subvention; credit guarantee support; funding for warehouses, cold storage, processing units, collection centres and logistics.',
        'application_process': 'Apply through Agriculture Infrastructure Fund portal and participating banks.',
        'official_link': 'https://agriinfra.dac.gov.in',
    },
    {
        'order': 5,
        'name_en': 'PM Formalisation of Micro Food Processing Enterprises (PMFME)',
        'name_ml': 'പ്രധാനമന്ത്രി സൂക്ഷ്മ ഭക്ഷ്യ സംസ്‌കരണ സംരംഭങ്ങളുടെ ഔപചാരികവത്കരണ പദ്ധതി',
        'category': SchemeCategory.INFRA,
        'administering_body': 'Ministry of Food Processing Industries',
        'objective': 'Support micro food processing enterprises through credit-linked capital subsidy and capacity building.',
        'eligibility': 'FPOs, SHGs, Cooperatives, Food processing enterprises.',
        'benefit_details': 'Credit-linked capital subsidy; support for common infrastructure; branding and marketing support; capacity building.',
        'application_process': 'Apply through State Nodal Agencies and PMFME portal.',
        'official_link': 'https://pmfme.mofpi.gov.in/pmfme/newsletters/groupapp.html',
    },
    {
        'order': 6,
        'name_en': 'Mission for Integrated Development of Horticulture (MIDH)',
        'name_ml': 'സമഗ്ര ഹോർട്ടികൾച്ചർ വികസന ദൗത്യം',
        'category': SchemeCategory.INFRA,
        'administering_body': 'Department of Agriculture & Farmers Welfare',
        'objective': 'Promote holistic development of horticulture sector including production, post-harvest management and marketing.',
        'eligibility': 'FPOs, Farmer groups, Horticulture producers.',
        'benefit_details': 'Nursery development support; protected cultivation; post-harvest infrastructure; pack houses and cold storage support.',
        'application_process': 'Apply through State Horticulture Mission.',
        'official_link': 'https://midh.gov.in',
    },
    {
        'order': 7,
        'name_en': 'Rashtriya Krishi Vikas Yojana (RKVY)',
        'name_ml': 'ദേശീയ കാർഷിക വികസന പദ്ധതി',
        'category': SchemeCategory.INFRA,
        'administering_body': 'Ministry of Agriculture & Farmers Welfare',
        'objective': 'Incentivize states to increase public investment in agriculture and allied sectors.',
        'eligibility': 'FPOs, Farmer groups, Agricultural enterprises.',
        'benefit_details': 'Infrastructure support; innovation projects; agri-business promotion; value chain development.',
        'application_process': 'Submitted through State Agriculture Department under approved projects.',
        'official_link': 'https://rkvy.nic.in',
    },
    {
        'order': 8,
        'name_en': 'NABARD Producer Organization Development Fund (PODF)',
        'name_ml': 'പ്രൊഡ്യൂസർ ഓർഗനൈസേഷൻ ഡെവലപ്മെന്റ് ഫണ്ട്',
        'category': SchemeCategory.CAPACITY,
        'administering_body': 'NABARD',
        'objective': 'Support capacity building, grant assistance and business development for Producer Organizations.',
        'eligibility': 'Producer Organizations and FPOs; NABARD-supported producer collectives.',
        'benefit_details': 'Capacity building; grant assistance; business development support; professional management support.',
        'application_process': 'Apply through NABARD regional offices or implementing agencies.',
        'official_link': 'https://www.nabard.org',
    },
    {
        'order': 9,
        'name_en': 'Pradhan Mantri Fasal Bima Yojana (PMFBY)',
        'name_ml': 'പ്രധാനമന്ത്രി ഫസൽ ബീമ യോജന',
        'category': SchemeCategory.INSURANCE,
        'administering_body': 'Ministry of Agriculture & Farmers Welfare',
        'objective': 'Provide comprehensive crop insurance against natural calamities to stabilize farmer income.',
        'eligibility': 'Eligible farmers including members of FPOs.',
        'benefit_details': 'Crop insurance against natural calamities; yield loss compensation; risk mitigation.',
        'application_process': 'Apply through banks, insurance companies or PMFBY portal.',
        'official_link': 'https://pmfby.gov.in',
    },
    {
        'order': 10,
        'name_en': 'e-NAM (National Agriculture Market)',
        'name_ml': 'ദേശീയ കാർഷിക വിപണി (ഇ-നാം)',
        'category': SchemeCategory.MARKETING,
        'administering_body': 'Ministry of Agriculture & Farmers Welfare',
        'objective': 'Create a unified national market for agricultural commodities with transparent price discovery.',
        'eligibility': 'FPOs, Farmers, Traders.',
        'benefit_details': 'Access to wider markets; transparent price discovery; online trading platform.',
        'application_process': 'Registration through e-NAM portal and linked markets.',
        'official_link': 'https://enam.gov.in',
    },
    {
        'order': 11,
        'name_en': 'ONDC for Agriculture and Farmer Collectives',
        'name_ml': 'ഓപ്പൺ നെറ്റ്‌വർക്ക് ഫോർ ഡിജിറ്റൽ കൊമേഴ്‌സ് (ONDC)',
        'category': SchemeCategory.MARKETING,
        'administering_body': 'Open Network for Digital Commerce',
        'objective': 'Enable FPOs and farmer collectives to access digital markets and wider customer reach.',
        'eligibility': 'FPOs, Producer collectives, Agri enterprises.',
        'benefit_details': 'Digital market access; wider customer reach; reduced dependence on intermediaries.',
        'application_process': 'Onboarding through approved ONDC network participants.',
        'official_link': 'https://ondc.org',
    },
    {
        'order': 12,
        'name_en': 'Kisan Credit Card (KCC)',
        'name_ml': 'കിസാൻ ക്രെഡിറ്റ് കാർഡ്',
        'category': SchemeCategory.CREDIT,
        'administering_body': 'Government of India through participating banks',
        'objective': 'Provide timely and adequate credit support to farmers for their agricultural operations.',
        'eligibility': 'Individual farmers; eligible members of FPOs.',
        'benefit_details': 'Short-term crop loans; working capital support; interest subvention benefits.',
        'application_process': 'Apply through commercial banks, cooperative banks and regional rural banks.',
        'official_link': 'https://pmkisan.gov.in',
    },
]


def seed_schemes():
    created = 0
    updated = 0

    for data in SCHEMES:
        obj, was_created = Scheme.objects.update_or_create(
            name_en=data['name_en'],
            defaults={k: v for k, v in data.items() if k != 'name_en'},
        )
        if was_created:
            created += 1
        else:
            updated += 1

    print(f'Schemes seeded: {created} created, {updated} updated. Total: {Scheme.objects.count()}')
