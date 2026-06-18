"""
Seed Site Content CMS
========================
Seeds SiteBlocks, Announcements, and FAQs from KAU RCD documents.

Usage:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/seed_cms.py').read())
    seed_cms()
    "
"""

from apps.database.models.cms import SiteBlock, Announcement, AnnouncementCategory, FAQ, FAQCategory


# ─── Site Blocks ─────────────────────────────────────────────────────────────

SITE_BLOCKS = [
    {
        'block_key': 'hero_headline',
        'content': {
            'en': 'Empowering Farmer Producer Organizations Through Knowledge, Technology, and Collaboration',
            'ml': 'അറിവും സാങ്കേതികവിദ്യയും സഹകരണവും വഴി കർഷക ഉൽപാദക സംഘടനകളെ ശക്തിപ്പെടുത്തുന്നു',
        },
    },
    {
        'block_key': 'hero_subheading',
        'content': {
            'en': 'A unified digital platform connecting Farmer Producer Organizations (FPOs) with knowledge resources, experts, institutions, schemes, and growth opportunities.',
            'ml': 'കർഷക ഉൽപാദക സംഘടനകളെ (FPO) അറിവ്, വിദഗ്ധർ, സ്ഥാപനങ്ങൾ, പദ്ധതികൾ, വികസനാവസരങ്ങൾ എന്നിവയുമായി ബന്ധിപ്പിക്കുന്ന ഏകീകൃത ഡിജിറ്റൽ പ്ലാറ്റ്ഫോം.',
        },
    },
    {
        'block_key': 'hero_description',
        'content': {
            'en': 'The KAU–FPO Linkage Platform is an AI-enabled digital ecosystem developed by the Communication Centre, Kerala Agricultural University, under the KAU–FPO Linkage Programme, funded by the Mission for Integrated Development of Horticulture (MIDH) through the State Horticulture Mission (SHM), Government of Kerala. Designed to strengthen Farmer-Producer Organisations through technology, knowledge, institutional partnerships, and market-oriented support, the platform provides a unified gateway to registration, expert services, schemes, resources, networking, and performance assessment.',
            'ml': 'കേരള കാർഷിക സർവകലാശാലയുടെ കമ്മ്യൂണിക്കേഷൻ സെന്ററിന്റെ നേതൃത്വത്തിൽ, സ്റ്റേറ്റ് ഹോർട്ടികൾച്ചർ മിഷൻ (SHM), കേരള സർക്കാർ മുഖേന മിഷൻ ഫോർ ഇന്റഗ്രേറ്റഡ് ഡെവലപ്മെന്റ് ഓഫ് ഹോർട്ടികൾച്ചർ (MIDH) പദ്ധതിയുടെ പിന്തുണയോടെ നടപ്പിലാക്കുന്ന KAU–FPO Linkage Programmeന്റെ ഭാഗമായി വികസിപ്പിച്ച കൃത്രിമ ബുദ്ധി (AI) അടിസ്ഥാനമാക്കിയ ഡിജിറ്റൽ പ്ലാറ്റ്ഫോമാണ് KAU–FPO Linkage Platform.',
        },
    },
    {
        'block_key': 'about_title',
        'content': {
            'en': 'About the KAU–FPO Linkage Programme',
            'ml': 'KAU–FPO ബന്ധന പരിപാടിയെക്കുറിച്ച്',
        },
    },
    {
        'block_key': 'about_body',
        'content': {
            'en': (
                'The KAU–FPO Linkage Platform is an AI-enabled digital ecosystem developed under the KAU–FPO Linkage Programme, '
                'a state-level initiative of Kerala Agricultural University (KAU) aimed at strengthening Farmer Producer Organizations '
                '(FPOs) across Kerala through institutional support, capacity building, technology integration, and market-oriented interventions.\n\n'
                'The programme is funded by the Mission for Integrated Development of Horticulture (MIDH) through the State Horticulture '
                'Mission (SHM), Government of Kerala. It seeks to build sustainable linkages between FPOs and key stakeholders including '
                'academic institutions, government departments, financial institutions, technical experts, agribusiness enterprises, and markets.\n\n'
                'Beyond the development of this digital platform, the programme has undertaken a wide range of FPO strengthening activities '
                'including training programmes, exposure visits, webinars, business planning support, Detailed Project Report (DPR) preparation, '
                'facilitation of financial assistance for external capacity-building programmes, and performance enhancement advisory services.\n\n'
                'The KAU–FPO Linkage Platform serves as the digital backbone of this initiative by providing a unified space for FPO registration, '
                'performance assessment, expert connect, scheme discovery, knowledge dissemination, institutional networking, and data-driven '
                'decision support.'
            ),
            'ml': (
                'കേരള കാർഷിക സർവകലാശാല (KAU) നടപ്പിലാക്കുന്ന KAU–FPO Linkage Programmeന്റെ ഭാഗമായി വികസിപ്പിച്ച കൃത്രിമ ബുദ്ധി (AI) '
                'അടിസ്ഥാനമാക്കിയുള്ള ഡിജിറ്റൽ പ്ലാറ്റ്ഫോമാണ് KAU–FPO Linkage Platform. കേരളത്തിലെ കർഷക ഉൽപാദക സംഘടനകളെ (FPOs) '
                'സ്ഥാപന പിന്തുണ, ശേഷിവികസനം, സാങ്കേതികവിദ്യയുടെ പ്രയോജനം, വിപണി അധിഷ്ഠിത ഇടപെടലുകൾ എന്നിവയിലൂടെ ശക്തിപ്പെടുത്തുക '
                'എന്നതാണ് പദ്ധതിയുടെ ലക്ഷ്യം.\n\n'
                'കേരള സർക്കാർ സ്റ്റേറ്റ് ഹോർട്ടികൾച്ചർ മിഷൻ (SHM) മുഖേന മിഷൻ ഫോർ ഇന്റഗ്രേറ്റഡ് ഡെവലപ്മെന്റ് ഓഫ് ഹോർട്ടികൾച്ചർ (MIDH) '
                'പദ്ധതിയുടെ ധനസഹായത്തോടെയാണ് ഈ പദ്ധതി നടപ്പിലാക്കുന്നത്.\n\n'
                'ഈ ഡിജിറ്റൽ പ്ലാറ്റ്ഫോം വികസിപ്പിക്കുന്നതിനു പുറമേ, എഫ്.പി.ഒകളുടെ ശേഷിവികസനത്തിനും സ്ഥാപന ശക്തീകരണത്തിനുമായി '
                'വിവിധ പരിശീലന പരിപാടികൾ, പഠനയാത്രകൾ, വെബിനാറുകൾ, ബിസിനസ് പ്ലാൻ തയ്യാറാക്കൽ എന്നിവ നടപ്പിലാക്കിയിട്ടുണ്ട്.\n\n'
                'എഫ്.പി.ഒ രജിസ്ട്രേഷൻ, പ്രകടന വിലയിരുത്തൽ, വിദഗ്ധ സേവനങ്ങൾ, പദ്ധതിവിവരങ്ങൾ, വിജ്ഞാന വിഭവങ്ങൾ, സ്ഥാപന സഹകരണം, '
                'ഡാറ്റ അധിഷ്ഠിത തീരുമാന സഹായം എന്നിവയെ ഒരൊറ്റ വേദിയിൽ ലഭ്യമാക്കുന്ന ഡിജിറ്റൽ അടിസ്ഥാന സൗകര്യമായി ഈ പ്ലാറ്റ്ഫോം പ്രവർത്തിക്കുന്നു.'
            ),
        },
    },
    {
        'block_key': 'how_to_register',
        'content': {
            'en': (
                'A Farmer Producer Organization (FPO) is a legally registered entity owned and governed by farmers for improving '
                'access to inputs, technology, credit, processing facilities, and markets.\n\n'
                'PHASE I: LEGAL REGISTRATION\n\n'
                'Step 1 — Mobilize the Required Farmer Members\n'
                'Organize a group of eligible farmers. Minimum 10 producer members required for a Producer Company.\n\n'
                'Step 2 — Obtain Digital Signature Certificates (DSC)\n'
                'Mandatory for electronic filing with MCA. Class 3 DSC required for Directors.\n\n'
                'Step 3 — Apply for Director Identification Number (DIN)\n'
                'Every Director must possess a valid DIN.\n\n'
                'Step 4 — Reserve the Company Name\n'
                'Must be unique and end with "Producer Company Limited".\n\n'
                'Step 5 — Prepare the Memorandum and Articles of Association\n'
                'MoA defines objectives; AoA defines governance structure.\n\n'
                'Step 6 — Submit the SPICe+ Incorporation Application\n'
                'Submitted online through the MCA SPICe+ system.\n\n'
                'Step 7 — Obtain the Certificate of Incorporation\n'
                'From Registrar of Companies (RoC). Confirms legal existence and CIN.\n\n'
                'PHASE II: POST-INCORPORATION SETUP\n\n'
                'Step 8 — Obtain PAN and TAN\n'
                'Required for bank accounts, tax compliance, and financial transactions.\n\n'
                'Step 9 — Open a Bank Account\n'
                'A dedicated current account in the name of the Producer Company.\n\n'
                'Step 10 — Collect Share Capital and Commence Operations\n'
                'Issue shares, deposit capital, maintain registers, and begin business activities.'
            ),
            'ml': '',
        },
    },
]


# ─── Announcements ────────────────────────────────────────────────────────────

ANNOUNCEMENTS = [
    {
        'order': 1,
        'category': AnnouncementCategory.ANNOUNCEMENT,
        'title': {
            'en': 'KAU–FPO Linkage Platform Launched',
            'ml': 'KAU–FPO Linkage പ്ലാറ്റ്ഫോം പ്രവർത്തനം ആരംഭിച്ചു',
        },
        'body': {
            'en': 'Kerala Agricultural University welcomes Farmer Producer Organizations, stakeholders, and institutions to the KAU–FPO Linkage Platform. The platform aims to strengthen FPOs through digital services, expert support, knowledge resources, and institutional networking.',
            'ml': 'കേരള കാർഷിക സർവകലാശാലയുടെ KAU–FPO Linkage Platform ലേക്ക് കർഷക ഉൽപാദക സംഘടനകളെയും മറ്റ് പങ്കാളികളെയും സ്വാഗതം ചെയ്യുന്നു. ഡിജിറ്റൽ സേവനങ്ങൾ, വിദഗ്ധ സഹായം, വിജ്ഞാന വിഭവങ്ങൾ, സ്ഥാപന സഹകരണം എന്നിവയിലൂടെ എഫ്.പി.ഒകളെ ശക്തിപ്പെടുത്തുക എന്നതാണ് പ്ലാറ്റ്ഫോമിന്റെ ലക്ഷ്യം.',
        },
    },
    {
        'order': 2,
        'category': AnnouncementCategory.ANNOUNCEMENT,
        'title': {
            'en': 'FPO Registration Portal Now Open',
            'ml': 'എഫ്.പി.ഒ രജിസ്ട്രേഷൻ പോർട്ടൽ പ്രവർത്തനസജ്ജമായി',
        },
        'body': {
            'en': 'Eligible Farmer Producer Organizations can now register on the platform and access various services, resources, scheme information, and institutional support opportunities.',
            'ml': 'അർഹമായ കർഷക ഉൽപാദക സംഘടനകൾക്ക് ഇപ്പോൾ പ്ലാറ്റ്ഫോമിൽ രജിസ്റ്റർ ചെയ്ത് വിവിധ സേവനങ്ങളും പദ്ധതിവിവരങ്ങളും സ്ഥാപന പിന്തുണകളും ലഭ്യമാക്കാം.',
        },
    },
    {
        'order': 3,
        'category': AnnouncementCategory.NEWS,
        'title': {
            'en': 'Expert Directory Introduced for FPO Support',
            'ml': 'എഫ്.പി.ഒകൾക്കായി വിദഗ്ധ സേവന ഡയറക്ടറി അവതരിപ്പിച്ചു',
        },
        'body': {
            'en': 'The platform now provides access to a curated directory of experts covering governance, agribusiness, finance, marketing, value addition, digital agriculture, and institutional development.',
            'ml': 'ഭരണം, കാർഷിക ബിസിനസ്, ധനകാര്യം, വിപണനം, മൂല്യവർധന, ഡിജിറ്റൽ കാർഷികം, സ്ഥാപന വികസനം തുടങ്ങിയ മേഖലകളിലെ വിദഗ്ധരെ ഉൾപ്പെടുത്തി ഒരു വിദഗ്ധ ഡയറക്ടറി പ്ലാറ്റ്ഫോമിൽ ലഭ്യമാണ്.',
        },
    },
    {
        'order': 4,
        'category': AnnouncementCategory.NEWS,
        'title': {
            'en': 'Schemes and Subsidies Information Repository Available',
            'ml': 'പദ്ധതികളുടെയും ധനസഹായങ്ങളുടെയും വിവരശേഖരം ലഭ്യമായി',
        },
        'body': {
            'en': 'FPOs can access updated information on government schemes, subsidies, credit facilities, insurance programmes, and infrastructure support initiatives through the platform.',
            'ml': 'സർക്കാർ പദ്ധതികൾ, ധനസഹായങ്ങൾ, വായ്പാ സൗകര്യങ്ങൾ, ഇൻഷുറൻസ് പദ്ധതികൾ, അടിസ്ഥാന സൗകര്യ വികസന സഹായങ്ങൾ എന്നിവയെക്കുറിച്ചുള്ള പുതുക്കിയ വിവരങ്ങൾ പ്ലാറ്റ്ഫോമിലൂടെ ലഭ്യമാണ്.',
        },
    },
]


# ─── FAQs ─────────────────────────────────────────────────────────────────────

FPO_GENERAL_FAQS = [
    ('What is a Farmer Producer Organization (FPO)?', 'A Farmer Producer Organization (FPO) is a legally registered organization formed and owned by farmers for improving production, aggregation, processing, marketing, and access to services. It enables farmers to collectively undertake economic activities and improve their bargaining power in the market.'),
    ('What is a Producer Company?', 'A Producer Company is a company registered under the Companies Act by primary producers such as farmers, fishers, livestock rearers, and other producer groups. It combines the professional management features of a company with the mutual assistance principles of a cooperative.'),
    ('Who can become a member of an FPO?', 'Any primary producer engaged in agriculture, horticulture, livestock, fisheries, plantation crops, or allied activities can become a member, subject to the eligibility criteria specified in the FPO\'s Articles of Association and membership rules.'),
    ('How many members are required to form an FPO?', 'A minimum of 10 producer members is required to register a Producer Company. However, larger membership is encouraged to improve business viability and collective strength.'),
    ('What are the benefits of joining an FPO?', 'Members can benefit from collective procurement of inputs, better market access, improved price realization, access to training and extension services, easier access to institutional credit, access to government schemes and support programs, and processing and value-addition opportunities.'),
    ('What is share capital?', 'Share capital refers to the amount contributed by members through the purchase of shares in the FPO. It represents ownership participation in the organization.'),
    ('Is share capital refundable?', 'The refundability and transferability of share capital are governed by the provisions of the Producer Company\'s Articles of Association and applicable legal provisions.'),
    ('What is the role of the Board of Directors?', 'The Board of Directors is responsible for providing strategic direction, governance, policy decisions, financial oversight, and ensuring compliance with legal and regulatory requirements.'),
    ('What is an Annual General Meeting (AGM)?', 'The AGM is a statutory meeting of members where important matters such as annual reports, audited accounts, appointment of auditors, and key resolutions are presented and approved.'),
    ('What is a Chief Executive Officer (CEO) in an FPO?', 'The CEO is the professional executive responsible for managing the day-to-day operations of the FPO under the guidance of the Board of Directors.'),
    ('What is the difference between a member and a shareholder?', 'In most Producer Companies, members become shareholders by purchasing shares. Members participate in governance and business activities, while shareholders also possess ownership rights through shareholding.'),
    ('Can an FPO avail bank loans?', 'Yes. Eligible FPOs can access institutional credit from commercial banks, cooperative banks, regional rural banks, and other financial institutions subject to applicable lending norms.'),
    ('What is the Credit Guarantee Fund Scheme for FPOs?', 'The Credit Guarantee Fund Scheme helps improve access to collateral-free credit by providing guarantee cover to lending institutions extending loans to eligible FPOs.'),
    ('What government schemes are available for FPOs?', 'FPOs may be eligible for various schemes related to formation and promotion, credit support, infrastructure development, processing and value addition, market linkage, capacity building, crop insurance, and export promotion. Please refer to the Schemes and Subsidies section of the portal for updated information.'),
    ('What is the Agriculture Infrastructure Fund (AIF)?', 'The Agriculture Infrastructure Fund provides medium and long-term financing support for infrastructure such as warehouses, cold storages, processing units, collection centers, and logistics facilities.'),
    ('What is meant by market linkage?', 'Market linkage refers to establishing structured connections between producers and buyers such as wholesalers, processors, retailers, exporters, institutions, and digital marketplaces.'),
    ('Can an FPO engage in processing and value addition?', 'Yes. FPOs can undertake processing, grading, packaging, branding, and value-addition activities subject to applicable licenses and regulations.'),
    ('What is an FPO Tier Classification?', 'The KAU-FPO platform classifies FPOs into different tiers based on parameters such as governance, management capacity, membership strength, financial performance, infrastructure, and business development. Tier classification is intended to support assessment, monitoring, and institutional development.'),
    ('Does a higher tier indicate better performance?', 'Generally, higher-tier FPOs demonstrate stronger institutional systems, business performance, compliance, and operational capacity. However, tier classification is intended as a developmental tool and not as a ranking of individual farmers.'),
    ('How often is the tier classification updated?', 'Tier classification may be updated periodically based on the latest information provided by the FPO and any revisions to the approved assessment framework.'),
    ('What documents should an FPO maintain?', 'Important documents include: Certificate of Incorporation, PAN and TAN records, Board resolutions, Membership register, Shareholder register, Audited financial statements, AGM records, Statutory filings, and Business plans and project reports.'),
    ('Why is compliance important for an FPO?', 'Regular compliance improves transparency, accountability, access to finance, eligibility for schemes, and overall institutional credibility.'),
    ('Can an FPO operate in multiple commodities?', 'Yes. Subject to its Memorandum and Articles of Association, an FPO may undertake activities involving multiple commodities and allied enterprises.'),
    ('Can fisheries, livestock, and plantation producer groups form FPOs?', 'Yes. Producer Organizations may be formed by fishers, livestock producers, plantation growers, and other primary producers in addition to farmers.'),
    ('Where can I obtain technical or business support for my FPO?', 'Support may be obtained from Kerala Agricultural University, NABARD, SFAC, Krishi Vigyan Kendras (KVKs), Department of Agriculture Development and Farmers\' Welfare, Commodity Boards, and Approved consultants and experts listed in the Expert Directory section of this portal.'),
]

SCHEMES_FAQS = [
    ('What government schemes are available for Farmer Producer Organizations (FPOs)?', 'FPOs may be eligible for various central and state government schemes related to FPO formation and promotion, credit support, infrastructure development, processing and value addition, market linkage, capacity building, crop insurance, and export promotion. Please refer to the Schemes and Subsidies section of this portal for the latest scheme details.'),
    ('Can newly formed FPOs apply for government support schemes?', 'Yes. Many schemes are specifically designed to support newly formed FPOs. However, eligibility criteria vary depending on the scheme, registration status, membership strength, and operational readiness of the FPO.'),
    ('What is the Central Sector Scheme for Formation and Promotion of 10,000 FPOs?', 'This flagship Government of India programme supports the formation, promotion, handholding, capacity building, and business development of Farmer Producer Organizations through designated implementing agencies and Cluster-Based Business Organizations (CBBOs).'),
    ('What is the role of SFAC in supporting FPOs?', 'The Small Farmers Agribusiness Consortium (SFAC) provides support through various initiatives including Equity Grant assistance, Credit Guarantee support, FPO promotion programmes, Market linkage initiatives, and Capacity building activities.'),
    ('What is the Equity Grant Fund Scheme?', 'The Equity Grant Fund Scheme provides matching equity support to eligible FPOs based on member share capital contributions. The objective is to strengthen the net worth of FPOs and improve their ability to access institutional finance.'),
    ('What is the Credit Guarantee Fund Scheme for FPOs?', 'The Credit Guarantee Fund Scheme provides guarantee cover to lending institutions extending loans to eligible FPOs. This helps improve access to collateral-free credit and reduces lending risks for banks.'),
    ('Can FPOs obtain bank loans?', 'Yes. FPOs may obtain working capital loans, term loans, infrastructure loans, and business expansion loans from commercial banks, cooperative banks, regional rural banks, and other financial institutions, subject to eligibility and lending norms.'),
    ('What documents are generally required for availing institutional credit?', 'The following documents are commonly required: Certificate of Incorporation/Registration, PAN, Audited financial statements, Board resolution, Business plan or project report, Bank account details, Shareholding records, and KYC documents of authorised representatives.'),
    ('What is the Agriculture Infrastructure Fund (AIF)?', 'The Agriculture Infrastructure Fund is a financing facility that provides medium and long-term debt financing support for agricultural infrastructure projects such as warehouses, cold storages, collection centres, processing units, sorting and grading facilities, and logistics infrastructure.'),
    ('Can FPOs receive assistance for storage and processing infrastructure?', 'Yes. Various schemes support warehousing, cold storage, processing units, pack houses, collection centres, and value addition facilities through Agriculture Infrastructure Fund (AIF), PMFME, MIDH, and other government programmes.'),
    ('What is PM Formalisation of Micro Food Processing Enterprises (PMFME)?', 'PMFME is a Government of India programme that supports food processing enterprises through credit-linked capital subsidy, common infrastructure support, branding assistance, marketing support, and capacity building. Eligible FPOs engaged in food processing may apply under the scheme.'),
    ('Can FPOs receive assistance for branding and packaging?', 'Yes. Certain schemes provide support for brand development, product packaging, marketing materials, product standardisation, and market promotion. The availability of such support depends on the applicable scheme guidelines.'),
    ('Are there schemes specifically for horticulture-based FPOs?', 'Yes. Horticulture-based FPOs may be eligible for support under programmes such as Mission for Integrated Development of Horticulture (MIDH), State horticulture programmes, and Infrastructure and value chain development projects.'),
    ('Are fisheries and livestock FPOs eligible for government support?', 'Yes. Producer organizations engaged in fisheries, aquaculture, dairy, livestock, poultry, and allied sectors may be eligible for sector-specific schemes in addition to general FPO support programmes.'),
    ('What is crop insurance and how can FPO members benefit?', 'Crop insurance helps farmers manage risks arising from natural calamities, adverse weather conditions, and yield losses. Individual members may avail benefits under applicable crop insurance schemes such as the Pradhan Mantri Fasal Bima Yojana (PMFBY).'),
    ('Can FPOs participate in export promotion programmes?', 'Yes. Eligible FPOs can participate in export-oriented initiatives and receive support for export readiness, quality certification, packaging improvements, international market linkage, and buyer-seller meets.'),
    ('What is meant by market linkage support?', 'Market linkage support helps FPOs establish connections with wholesalers, retail chains, processors, institutional buyers, government procurement agencies, and exporters. Such linkages improve market access and price realization for members.'),
    ('Can FPOs receive training and capacity-building support?', 'Yes. Capacity-building programmes are offered by institutions such as Kerala Agricultural University, NABARD, SFAC, NCDC, Krishi Vigyan Kendras (KVKs), and the Department of Agriculture Development and Farmers\' Welfare.'),
    ('How can an FPO know whether it is eligible for a particular scheme?', 'Eligibility depends on factors such as legal status of the FPO, years of operation, membership strength, financial performance, business activity, and infrastructure requirements. Users are advised to carefully review scheme guidelines before applying.'),
    ('Does a higher FPO tier improve access to schemes and financial support?', 'Some programmes may consider governance quality, operational performance, compliance, and institutional strength while assessing applications. A stronger tier classification may improve credibility and readiness for certain opportunities, though scheme eligibility is governed by the specific guidelines of each programme.'),
    ('Can one FPO avail benefits under multiple schemes?', 'Yes. Subject to scheme guidelines and eligibility conditions, an FPO may avail support from multiple programmes. However, duplication of assistance for the same activity may not be permitted under certain schemes.'),
    ('Are all schemes available throughout the year?', 'No. Some schemes operate continuously, while others are announced periodically with specific application windows, budget allocations, or project approvals.'),
    ('Where can I obtain assistance in applying for schemes?', 'FPOs may seek support from Kerala Agricultural University, NABARD, SFAC, Department of Agriculture Development and Farmers\' Welfare, Krishi Vigyan Kendras (KVKs), Commodity Boards, and Approved consultants and experts listed in the Expert Directory section of this portal.'),
    ('How can I stay updated on newly launched schemes and subsidies?', 'Users are encouraged to regularly visit the Schemes and Subsidies section of this portal, where new schemes, notifications, application deadlines, and eligibility updates will be published.'),
    ('Where can I find official scheme guidelines and application links?', 'Each scheme listed in the Schemes and Subsidies section contains scheme description, eligibility criteria, benefit details, application process, official website links, and relevant documents and notifications where available.'),
    ('What is the NABARD Producer Organization Development Fund (PODF)?', 'The NABARD PODF provides capacity building support, grant assistance, and business development funding for Producer Organizations and FPOs through NABARD regional offices and implementing agencies.'),
]


def seed_cms():
    # Seed site blocks
    b_created = b_updated = 0
    for data in SITE_BLOCKS:
        _, created = SiteBlock.objects.update_or_create(
            block_key=data['block_key'],
            defaults={'content': data['content'], 'is_active': True},
        )
        if created:
            b_created += 1
        else:
            b_updated += 1
    print(f'SiteBlocks: {b_created} created, {b_updated} updated.')

    # Seed announcements
    Announcement.objects.all().delete()
    for data in ANNOUNCEMENTS:
        Announcement.objects.create(**data)
    print(f'Announcements: {len(ANNOUNCEMENTS)} seeded.')

    # Seed FAQs
    FAQ.objects.all().delete()
    faq_count = 0
    for i, (q, a) in enumerate(FPO_GENERAL_FAQS, start=1):
        FAQ.objects.create(
            question={'en': q, 'ml': ''},
            answer={'en': a, 'ml': ''},
            category=FAQCategory.FPO_GENERAL,
            order=i,
        )
        faq_count += 1

    for i, (q, a) in enumerate(SCHEMES_FAQS, start=1):
        FAQ.objects.create(
            question={'en': q, 'ml': ''},
            answer={'en': a, 'ml': ''},
            category=FAQCategory.SCHEMES,
            order=i,
        )
        faq_count += 1

    print(f'FAQs: {faq_count} seeded ({len(FPO_GENERAL_FAQS)} FPO general + {len(SCHEMES_FAQS)} schemes).')
    print('Done.')
