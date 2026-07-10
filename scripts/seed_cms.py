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
            'ml': (
                'കർഷക ഉൽപ്പാദക സംഘടന (FPO) എന്നത് ഇൻപുട്ടുകൾ, സാങ്കേതികവിദ്യ, വായ്പ, സംസ്കരണ സൗകര്യങ്ങൾ, '
                'വിപണി എന്നിവ മെച്ചപ്പെടുത്തുന്നതിനായി കർഷകർ ഉടമസ്ഥതയിലും നിയന്ത്രണത്തിലും നടത്തുന്ന '
                'നിയമപ്രകാരം രജിസ്റ്റർ ചെയ്ത സ്ഥാപനമാണ്.\n\n'
                'ഘട്ടം I: നിയമ രജിസ്ട്രേഷൻ\n\n'
                'പടി 1 — ആവശ്യമായ കർഷക അംഗങ്ങളെ സമാഹരിക്കുക\n'
                'യോഗ്യരായ കർഷകരുടെ ഒരു കൂട്ടത്തെ സംഘടിപ്പിക്കുക. ഒരു പ്രൊഡ്യൂസർ കമ്പനിക്ക് കുറഞ്ഞത് 10 ഉൽപ്പാദക അംഗങ്ങൾ ആവശ്യമാണ്.\n\n'
                'പടി 2 — ഡിജിറ്റൽ സിഗ്നേച്ചർ സർട്ടിഫിക്കറ്റ് (DSC) നേടുക\n'
                'MCA-യിൽ ഇലക്ട്രോണിക് ഫയൽ ചെയ്യുന്നതിന് നിർബന്ധിതമാണ്. ഡയറക്ടർമാർക്ക് ക്ലാസ് 3 DSC ആവശ്യമാണ്.\n\n'
                'പടി 3 — ഡയറക്ടർ ഐഡന്റിഫിക്കേഷൻ നമ്പർ (DIN) ലഭ്യമാക്കുക\n'
                'എല്ലാ ഡയറക്ടർക്കും സാധുവായ DIN ഉണ്ടായിരിക്കണം.\n\n'
                'പടി 4 — കമ്പനിയുടെ പേര് സംവരണം ചെയ്യുക\n'
                'പേര് അദ്വിതീയമായിരിക്കണം, "Producer Company Limited" എന്ന് അവസാനിക്കണം.\n\n'
                'പടി 5 — മെമ്മോറാണ്ടവും ആർട്ടിക്കിൾസ് ഓഫ് അസോസിയേഷനും തയ്യാറാക്കുക\n'
                'MoA ലക്ഷ്യങ്ങൾ നിർവചിക്കുന്നു; AoA ഭരണ ഘടന നിർവചിക്കുന്നു.\n\n'
                'പടി 6 — SPICe+ ഇൻകോർപ്പറേഷൻ അപ്ലിക്കേഷൻ സമർപ്പിക്കുക\n'
                'MCA SPICe+ സിസ്റ്റം വഴി ഓൺലൈനായി സമർപ്പിക്കുക.\n\n'
                'പടി 7 — ഇൻകോർപ്പറേഷൻ സർട്ടിഫിക്കറ്റ് നേടുക\n'
                'രജിസ്ട്രാർ ഓഫ് കമ്പനീസ് (RoC)-ൽ നിന്ന്. നിയമ നിലനിൽപ്പും CIN-ഉം സ്ഥിരീകരിക്കുന്നു.\n\n'
                'ഘട്ടം II: ഇൻകോർപ്പറേഷൻ ശേഷം ചെയ്യേണ്ടവ\n\n'
                'പടി 8 — PAN, TAN നേടുക\n'
                'ബാങ്ക് അക്കൗണ്ടുകൾ, നികുതി അനുസരണം, സാമ്പത്തിക ഇടപാടുകൾ എന്നിവയ്ക്ക് ആവശ്യമാണ്.\n\n'
                'പടി 9 — ബാങ്ക് അക്കൗണ്ട് തുറക്കുക\n'
                'പ്രൊഡ്യൂസർ കമ്പനിയുടെ പേരിൽ ഒരു സമർപ്പിത കറന്റ് അക്കൗണ്ട്.\n\n'
                'പടി 10 — ഓഹരി മൂലധനം ശേഖരിക്കുക, പ്രവർത്തനം ആരംഭിക്കുക\n'
                'ഓഹരി ഇഷ്യൂ ചെയ്യുക, മൂലധനം നിക്ഷേപിക്കുക, രജിസ്റ്ററുകൾ സൂക്ഷിക്കുക, ബിസിനസ് പ്രവർത്തനങ്ങൾ ആരംഭിക്കുക.'
            ),
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
    (
        'What is a Farmer Producer Organization (FPO)?',
        'A Farmer Producer Organization (FPO) is a legally registered organization formed and owned by farmers for improving production, aggregation, processing, marketing, and access to services. It enables farmers to collectively undertake economic activities and improve their bargaining power in the market.',
        'കർഷക ഉൽപ്പാദക സംഘടന (FPO) എന്നത് ഉൽപ്പാദനം, കൂട്ടായ ശേഖരണം, സംസ്കരണം, വിപണനം, സേവന ലഭ്യത എന്നിവ മെച്ചപ്പെടുത്തുന്നതിനായി കർഷകർ രൂപീകരിക്കുകയും ഉടമസ്ഥപ്പെടുത്തുകയും ചെയ്യുന്ന നിയമപ്രകാരം രജിസ്റ്റർ ചെയ്ത സ്ഥാപനമാണ്. വിപണിയിൽ കൂട്ടായ്മ ഉണ്ടാക്കിയും വിലപേശൽ ശേഷി മെച്ചപ്പെടുത്തിയും സാമ്പത്തിക പ്രവർത്തനങ്ങൾ നടത്തുവാൻ ഇത് കർഷകരെ സഹായിക്കുന്നു.',
        'കർഷക ഉൽപ്പാദക സംഘടന (FPO) എന്നാൽ എന്ത്?',
    ),
    (
        'What is a Producer Company?',
        'A Producer Company is a company registered under the Companies Act by primary producers such as farmers, fishers, livestock rearers, and other producer groups. It combines the professional management features of a company with the mutual assistance principles of a cooperative.',
        'പ്രൊഡ്യൂസർ കമ്പനി എന്നത് കർഷകർ, മത്സ്യത്തൊഴിലാളികൾ, കന്നുകാലി വളർത്തൽക്കാർ, മറ്റ് ഉൽപ്പാദക ഗ്രൂപ്പുകൾ തുടങ്ങിയ പ്രാഥമിക ഉൽപ്പാദകർ കമ്പനീസ് ആക്ട് പ്രകാരം രജിസ്റ്റർ ചെയ്ത കമ്പനിയാണ്. ഒരു കമ്പനിയുടെ തൊഴിൽ ഭരണ സവിശേഷതകളും ഒരു സഹകരണ സ്ഥാപനത്തിന്റെ പരസ്പര സഹായ തത്ത്വങ്ങളും ഇതിൽ സമ്മേളിക്കുന്നു.',
        'പ്രൊഡ്യൂസർ കമ്പനി എന്നാൽ എന്ത്?',
    ),
    (
        'Who can become a member of an FPO?',
        'Any primary producer engaged in agriculture, horticulture, livestock, fisheries, plantation crops, or allied activities can become a member, subject to the eligibility criteria specified in the FPO\'s Articles of Association and membership rules.',
        'കൃഷി, തോട്ടകൃഷി, കന്നുകാലി വളർത്തൽ, മത്സ്യബന്ധനം, തോട്ടം വിളകൾ അല്ലെങ്കിൽ അനുബന്ധ പ്രവർത്തനങ്ങളിൽ ഏർപ്പെടുന്ന ഏതൊരു പ്രാഥമിക ഉൽപ്പാദകനും, FPO-യുടെ ആർട്ടിക്കിൾസ് ഓഫ് അസോസിയേഷൻ, അംഗത്വ നിയമങ്ങൾ എന്നിവ അനുസരിച്ചുള്ള യോഗ്യതാ മാനദണ്ഡങ്ങൾക്ക് വിധേയമായി അംഗമാകാം.',
        'ഒരു FPO-യിൽ ആർക്കൊക്കെ അംഗമാകാം?',
    ),
    (
        'How many members are required to form an FPO?',
        'A minimum of 10 producer members is required to register a Producer Company. However, larger membership is encouraged to improve business viability and collective strength.',
        'ഒരു പ്രൊഡ്യൂസർ കമ്പനി രജിസ്റ്റർ ചെയ്യുന്നതിന് കുറഞ്ഞത് 10 ഉൽപ്പാദക അംഗങ്ങൾ ആവശ്യമാണ്. എന്നിരുന്നാലും, ബിസിനസ് ലാഭ്യതയും കൂട്ടായ ശക്തിയും മെച്ചപ്പെടുത്തുന്നതിന് കൂടുതൽ അംഗത്വം പ്രോൽസാഹിപ്പിക്കപ്പെടുന്നു.',
        'ഒരു FPO രൂപീകരിക്കാൻ എത്ര അംഗങ്ങൾ ആവശ്യമാണ്?',
    ),
    (
        'What are the benefits of joining an FPO?',
        'Members can benefit from collective procurement of inputs, better market access, improved price realization, access to training and extension services, easier access to institutional credit, access to government schemes and support programs, and processing and value-addition opportunities.',
        'കൂട്ടായ ഇൻപുട്ട് സംഭരണം, മെച്ചപ്പെട്ട വിപണി ലഭ്യത, മെച്ചപ്പെട്ട വില ലഭ്യത, പരിശീലനവും വ്യാപന സേവനങ്ങളും, സ്ഥാപന വായ്പ ലഭ്യത, സർക്കാർ പദ്ധതികളും പിന്തുണ പരിപാടികളും, സംസ്കരണ, മൂല്യ വർദ്ധന അവസരങ്ങൾ തുടങ്ങിയ ആനുകൂല്യങ്ങൾ അംഗങ്ങൾക്ക് ലഭ്യമാകും.',
        'FPO-യിൽ ചേരുന്നതിന്റെ ഗുണങ്ങൾ എന്തൊക്കെ?',
    ),
    (
        'What is share capital?',
        'Share capital refers to the amount contributed by members through the purchase of shares in the FPO. It represents ownership participation in the organization.',
        'ഓഹരി മൂലധനം എന്നത് FPO-യിൽ ഓഹരി വാങ്ങുന്നതിലൂടെ അംഗങ്ങൾ സംഭാവന ചെയ്യുന്ന തുകയാണ്. ഇത് സംഘടനയിലെ ഉടമസ്ഥ പങ്കാളിത്തത്തെ പ്രതിനിധാനം ചെയ്യുന്നു.',
        'ഓഹരി മൂലധനം എന്നാൽ എന്ത്?',
    ),
    (
        'Is share capital refundable?',
        'The refundability and transferability of share capital are governed by the provisions of the Producer Company\'s Articles of Association and applicable legal provisions.',
        'ഓഹരി മൂലധനം തിരിച്ചടയ്ക്കാനാകുമോ, കൈമാറ്റം ചെയ്യാനാകുമോ എന്നത് പ്രൊഡ്യൂസർ കമ്പനിയുടെ ആർട്ടിക്കിൾസ് ഓഫ് അസോസിയേഷന്റെ വ്യവസ്ഥകളും ബാധകമായ നിയമ വ്യവസ്ഥകളും അനുസരിച്ചാണ് നിർണ്ണയിക്കപ്പെടുന്നത്.',
        'ഓഹരി മൂലധനം തിരിച്ചടയ്ക്കാനാകുമോ?',
    ),
    (
        'What is the role of the Board of Directors?',
        'The Board of Directors is responsible for providing strategic direction, governance, policy decisions, financial oversight, and ensuring compliance with legal and regulatory requirements.',
        'ഡയറക്ടർ ബോർഡ് തന്ത്രപ്രധാന ദിശാബോധം, ഭരണം, നയ തീരുമാനങ്ങൾ, സാമ്പത്തിക മേൽനോട്ടം, നിയമ, നിയന്ത്രണ ആവശ്യകതകൾ പാലിക്കൽ എന്നിവ ഉറപ്പുവരുത്തുന്നതിൽ ഉത്തരവാദിത്വം വഹിക്കുന്നു.',
        'ഡയറക്ടർ ബോർഡിന്റെ പങ്ക് എന്ത്?',
    ),
    (
        'What is an Annual General Meeting (AGM)?',
        'The AGM is a statutory meeting of members where important matters such as annual reports, audited accounts, appointment of auditors, and key resolutions are presented and approved.',
        'AGM (വാർഷിക പൊതുയോഗം) എന്നത് അംഗങ്ങളുടെ നിയമാനുസൃതമായ ഒരു യോഗമാണ്. അതിൽ വാർഷിക റിപ്പോർട്ടുകൾ, ഓഡിറ്റ് ചെയ്ത അക്കൗണ്ടുകൾ, ഓഡിറ്റർമാരുടെ നിയമനം, പ്രധാന പ്രമേയങ്ങൾ തുടങ്ങിയ കാര്യങ്ങൾ അവതരിപ്പിക്കുകയും അംഗീകരിക്കുകയും ചെയ്യുന്നു.',
        'വാർഷിക പൊതുയോഗം (AGM) എന്നാൽ എന്ത്?',
    ),
    (
        'What is a Chief Executive Officer (CEO) in an FPO?',
        'The CEO is the professional executive responsible for managing the day-to-day operations of the FPO under the guidance of the Board of Directors.',
        'FPO-യിലെ ചീഫ് എക്സിക്യൂട്ടീവ് ഓഫീസർ (CEO) ഡയറക്ടർ ബോർഡിന്റെ മാർഗ്ഗനിർദ്ദേശപ്രകാരം FPO-യുടെ ദൈനംദിന പ്രവർത്തനങ്ങൾ നിയന്ത്രിക്കുന്ന പ്രൊഫഷണൽ എക്സിക്യൂട്ടീവ് ആണ്.',
        'FPO-യിൽ CEO-യുടെ പങ്ക് എന്ത്?',
    ),
    (
        'What is the difference between a member and a shareholder?',
        'In most Producer Companies, members become shareholders by purchasing shares. Members participate in governance and business activities, while shareholders also possess ownership rights through shareholding.',
        'മിക്ക പ്രൊഡ്യൂസർ കമ്പനികളിലും, ഓഹരി വാങ്ങുന്നതിലൂടെ അംഗങ്ങൾ ഓഹരിഉടമകളാകുന്നു. അംഗങ്ങൾ ഭരണ, ബിസിനസ് പ്രവർത്തനങ്ങളിൽ പങ്കെടുക്കുന്നു; ഓഹരിഉടമകൾ ഓഹരി ഉടമസ്ഥതയിലൂടെ ഉടമസ്ഥ അവകാശങ്ങൾ കൂടി കൈവശം വയ്ക്കുന്നു.',
        'അംഗവും ഓഹരിഉടമയും തമ്മിലുള്ള വ്യത്യാസം എന്ത്?',
    ),
    (
        'Can an FPO avail bank loans?',
        'Yes. Eligible FPOs can access institutional credit from commercial banks, cooperative banks, regional rural banks, and other financial institutions subject to applicable lending norms.',
        'അതെ. യോഗ്യരായ FPO-കൾക്ക് ബാധകമായ വായ്പ നിയമങ്ങൾക്ക് വിധേയമായി വാണിജ്യ ബാങ്കുകൾ, സഹകരണ ബാങ്കുകൾ, പ്രാദേശിക ഗ്രാമീണ ബാങ്കുകൾ, മറ്റ് ധനകാര്യ സ്ഥാപനങ്ങൾ എന്നിവയിൽ നിന്ന് സ്ഥാപന വായ്പ ലഭ്യമാക്കാം.',
        'FPO-യ്ക്ക് ബാങ്ക് വായ്പ ലഭ്യമാകുമോ?',
    ),
    (
        'What is the Credit Guarantee Fund Scheme for FPOs?',
        'The Credit Guarantee Fund Scheme helps improve access to collateral-free credit by providing guarantee cover to lending institutions extending loans to eligible FPOs.',
        'ക്രെഡിറ്റ് ഗ്യാരണ്ടി ഫണ്ട് സ്കീം, അർഹരായ FPO-കൾക്ക് വായ്പ നൽകുന്ന ധനകാര്യ സ്ഥാപനങ്ങൾക്ക് ഗ്യാരണ്ടി കവർ നൽകി, ഈടില്ലാ വായ്പ ലഭ്യത മെച്ചപ്പെടുത്തുന്നു.',
        'FPO-കൾക്കുള്ള ക്രെഡിറ്റ് ഗ്യാരണ്ടി ഫണ്ട് സ്കീം എന്ത്?',
    ),
    (
        'What government schemes are available for FPOs?',
        'FPOs may be eligible for various schemes related to formation and promotion, credit support, infrastructure development, processing and value addition, market linkage, capacity building, crop insurance, and export promotion. Please refer to the Schemes and Subsidies section of the portal for updated information.',
        'FPO-കൾ രൂപീകരണം, പ്രോൽസാഹനം, വായ്പ സഹായം, അടിസ്ഥാന സൗകര്യ വികസനം, സംസ്കരണം, മൂല്യ വർദ്ധന, വിപണി ബന്ധം, ശേഷിവികസനം, വിള ഇൻഷുറൻസ്, കയറ്റുമതി പ്രോൽസാഹനം തുടങ്ങിയ പദ്ധതികൾക്ക് അർഹരായേക്കാം. ഏറ്റവും പുതിയ വിവരങ്ങൾക്ക് പോർട്ടലിന്റെ പദ്ധതികളും സബ്സിഡികളും വിഭാഗം കാണുക.',
        'FPO-കൾക്ക് ഏതൊക്കെ സർക്കാർ പദ്ധതികൾ ലഭ്യമാണ്?',
    ),
    (
        'What is the Agriculture Infrastructure Fund (AIF)?',
        'The Agriculture Infrastructure Fund provides medium and long-term financing support for infrastructure such as warehouses, cold storages, processing units, collection centers, and logistics facilities.',
        'കൃഷി അടിസ്ഥാന സൗകര്യ നിധി (AIF) ഗോഡൗണുകൾ, ശീതീകരണ സൗകര്യങ്ങൾ, സംസ്കരണ ഘടകങ്ങൾ, ശേഖരണ കേന്ദ്രങ്ങൾ, ലോജിസ്റ്റിക്സ് സൗകര്യങ്ങൾ തുടങ്ങിയ അടിസ്ഥാന സൗകര്യ വിഭവങ്ങൾക്ക് ഇടക്കാലവും ദീർഘകാലവുമായ ധനസഹായം നൽകുന്നു.',
        'കൃഷി അടിസ്ഥാന സൗകര്യ നിധി (AIF) എന്നാൽ എന്ത്?',
    ),
    (
        'What is meant by market linkage?',
        'Market linkage refers to establishing structured connections between producers and buyers such as wholesalers, processors, retailers, exporters, institutions, and digital marketplaces.',
        'വിപണി ബന്ധം (Market Linkage) എന്നത് ഉൽപ്പാദകർക്കും മൊത്തക്കച്ചവടക്കാർ, സംസ്കരണക്കാർ, ചില്ലറ വ്യാപാരികൾ, കയറ്റുമതിക്കാർ, സ്ഥാപനങ്ങൾ, ഡിജിറ്റൽ കമ്പോളങ്ങൾ തുടങ്ങിയ വാങ്ങുന്നവർക്കും ഇടയിൽ ഘടനാപ്പെട്ട ബന്ധം സ്ഥാപിക്കുന്നതിനെ സൂചിപ്പിക്കുന്നു.',
        'വിപണി ബന്ധം (Market Linkage) എന്നാൽ എന്ത്?',
    ),
    (
        'Can an FPO engage in processing and value addition?',
        'Yes. FPOs can undertake processing, grading, packaging, branding, and value-addition activities subject to applicable licenses and regulations.',
        'അതെ. ബാധകമായ ലൈസൻസുകൾക്കും നിയന്ത്രണങ്ങൾക്കും വിധേയമായി FPO-കൾക്ക് സംസ്കരണം, ഗ്രേഡിംഗ്, പാക്കേജിംഗ്, ബ്രാൻഡിംഗ്, മൂല്യ വർദ്ധന പ്രവർത്തനങ്ങൾ എന്നിവ ഏറ്റെടുക്കാം.',
        'ഒരു FPO-യ്ക്ക് സംസ്കരണ, മൂല്യ വർദ്ധന പ്രവർത്തനങ്ങൾ ഏറ്റെടുക്കാമോ?',
    ),
    (
        'What is an FPO Tier Classification?',
        'The KAU-FPO platform classifies FPOs into different tiers based on parameters such as governance, management capacity, membership strength, financial performance, infrastructure, and business development. Tier classification is intended to support assessment, monitoring, and institutional development.',
        'KAU-FPO പ്ലാറ്റ്ഫോം FPO-കളെ ഭരണം, മാനേജ്മെന്റ് ശേഷി, അംഗത്വ ബലം, സാമ്പത്തിക പ്രകടനം, അടിസ്ഥാന സൗകര്യം, ബിസിനസ് വികസനം തുടങ്ങിയ മാനദണ്ഡങ്ങൾ അടിസ്ഥാനമാക്കി വ്യത്യസ്ത ടയറുകളായി തരംതിരിക്കുന്നു. ടയർ വർഗ്ഗീകരണം വിലയിരുത്തൽ, നിരീക്ഷണം, സ്ഥാപന വികസനം എന്നിവ പിന്തുണയ്ക്കാൻ ഉദ്ദേശിക്കപ്പെട്ടിരിക്കുന്നു.',
        'FPO ടയർ വർഗ്ഗീകരണം എന്നാൽ എന്ത്?',
    ),
    (
        'Does a higher tier indicate better performance?',
        'Generally, higher-tier FPOs demonstrate stronger institutional systems, business performance, compliance, and operational capacity. However, tier classification is intended as a developmental tool and not as a ranking of individual farmers.',
        'പൊതുവേ, ഉയർന്ന ടയർ FPO-കൾ ശക്തമായ സ്ഥാപന സംവിധാനങ്ങൾ, ബിസിനസ് പ്രകടനം, അനുസരണം, പ്രവർത്തന ശേഷി എന്നിവ പ്രകടിപ്പിക്കുന്നു. എന്നിരുന്നാലും, ടയർ വർഗ്ഗീകരണം ഒരു വികസന ഉപകരണമായി ഉദ്ദേശിക്കപ്പെടുന്നു, ഒറ്റ കർഷകരുടെ റാങ്കിംഗ് ആയി അല്ല.',
        'ഉയർന്ന ടയർ മെച്ചപ്പെട്ട പ്രകടനം സൂചിപ്പിക്കുന്നുണ്ടോ?',
    ),
    (
        'How often is the tier classification updated?',
        'Tier classification may be updated periodically based on the latest information provided by the FPO and any revisions to the approved assessment framework.',
        'FPO നൽകുന്ന ഏറ്റവും പുതിയ വിവരങ്ങളുടെയും അംഗീകൃത മൂല്യനിർണ്ണ ചട്ടക്കൂടിലെ പരിഷ്കരണങ്ങളുടെയും അടിസ്ഥാനത്തിൽ ടയർ വർഗ്ഗീകരണം ആനുകാലികമായി അപ്ഡേറ്റ് ചെയ്തേക്കാം.',
        'ടയർ വർഗ്ഗീകരണം എത്ര കാലത്തിലൊരിക്കൽ അപ്ഡേറ്റ് ചെയ്യും?',
    ),
    (
        'What documents should an FPO maintain?',
        'Important documents include: Certificate of Incorporation, PAN and TAN records, Board resolutions, Membership register, Shareholder register, Audited financial statements, AGM records, Statutory filings, and Business plans and project reports.',
        'സൂക്ഷിക്കേണ്ട പ്രധാന രേഖകൾ: ഇൻകോർപ്പറേഷൻ സർട്ടിഫിക്കറ്റ്, PAN, TAN രേഖകൾ, ബോർഡ് പ്രമേയങ്ങൾ, അംഗത്വ രജിസ്റ്റർ, ഓഹരിഉടമ രജിസ്റ്റർ, ഓഡിറ്റ് ചെയ്ത സാമ്പത്തിക പ്രസ്താവനകൾ, AGM രേഖകൾ, നിയമ ഫയലിംഗുകൾ, ബിസിനസ് പ്ലാനുകൾ, പ്രൊജക്ട് റിപ്പോർട്ടുകൾ.',
        'ഒരു FPO ഏതൊക്കെ രേഖകൾ സൂക്ഷിക്കണം?',
    ),
    (
        'Why is compliance important for an FPO?',
        'Regular compliance improves transparency, accountability, access to finance, eligibility for schemes, and overall institutional credibility.',
        'പതിവ് നിയമ അനുസരണം സുതാര്യത, ഉത്തരവാദിത്വം, ധനകാര്യ ലഭ്യത, പദ്ധതി അർഹത, മൊത്തത്തിലുള്ള സ്ഥാപന വിശ്വാസ്യത എന്നിവ മെച്ചപ്പെടുത്തുന്നു.',
        'ഒരു FPO-യ്ക്ക് നിയമ അനുസരണം എന്തുകൊണ്ട് പ്രധാനം?',
    ),
    (
        'Can an FPO operate in multiple commodities?',
        'Yes. Subject to its Memorandum and Articles of Association, an FPO may undertake activities involving multiple commodities and allied enterprises.',
        'അതെ. ഒരു FPO-യ്ക്ക് അതിന്റെ മെമ്മോറാണ്ടവും ആർട്ടിക്കിൾസ് ഓഫ് അസോസിയേഷനും അനുസരിച്ച്, ഒന്നിലധികം ചരക്കുകൾ, അനുബന്ധ സംരംഭങ്ങൾ എന്നിവ ഉൾക്കൊള്ളുന്ന പ്രവർത്തനങ്ങൾ ഏറ്റെടുക്കാം.',
        'ഒരു FPO-യ്ക്ക് ഒന്നിലധികം ചരക്കുകളിൽ പ്രവർത്തിക്കാമോ?',
    ),
    (
        'Can fisheries, livestock, and plantation producer groups form FPOs?',
        'Yes. Producer Organizations may be formed by fishers, livestock producers, plantation growers, and other primary producers in addition to farmers.',
        'അതെ. കർഷകർക്കൊപ്പം മത്സ്യത്തൊഴിലാളികൾ, കന്നുകാലി ഉൽപ്പാദകർ, തോട്ടം കർഷകർ, മറ്റ് പ്രാഥമിക ഉൽപ്പാദകർ എന്നിവർക്കും ഉൽപ്പാദക സംഘടനകൾ രൂപീകരിക്കാം.',
        'മത്സ്യബന്ധനം, കന്നുകാലി, തോട്ടം ഉൽപ്പാദക ഗ്രൂപ്പുകൾക്ക് FPO രൂപീകരിക്കാമോ?',
    ),
    (
        'Where can I obtain technical or business support for my FPO?',
        'Support may be obtained from Kerala Agricultural University, NABARD, SFAC, Krishi Vigyan Kendras (KVKs), Department of Agriculture Development and Farmers\' Welfare, Commodity Boards, and Approved consultants and experts listed in the Expert Directory section of this portal.',
        'കേരള കാർഷിക സർവകലാശാല, NABARD, SFAC, കൃഷി വിജ്ഞാന കേന്ദ്രങ്ങൾ (KVK), കൃഷി, കർഷക ക്ഷേമ വകുപ്പ്, ചരക്ക് ബോർഡുകൾ, ഈ പോർട്ടലിന്റെ വിദഗ്ധ ഡയറക്ടറി വിഭാഗത്തിൽ ലിസ്റ്റ് ചെയ്ത അംഗീകൃത ഉപദേശകർ, വിദഗ്ധർ എന്നിവരിൽ നിന്ന് സഹായം ലഭ്യമാകും.',
        'എന്റെ FPO-യ്ക്ക് സാങ്കേതിക അല്ലെങ്കിൽ ബിസിനസ് പിന്തുണ എവിടെ നിന്ന് ലഭിക്കും?',
    ),
]

SCHEMES_FAQS = [
    (
        'What government schemes are available for Farmer Producer Organizations (FPOs)?',
        'FPOs may be eligible for various central and state government schemes related to FPO formation and promotion, credit support, infrastructure development, processing and value addition, market linkage, capacity building, crop insurance, and export promotion. Please refer to the Schemes and Subsidies section of this portal for the latest scheme details.',
        'FPO-കൾ രൂപീകരണം, പ്രോൽസാഹനം, വായ്പ സഹായം, അടിസ്ഥാന സൗകര്യ വികസനം, സംസ്കരണം, മൂല്യ വർദ്ധന, വിപണി ബന്ധം, ശേഷിവികസനം, വിള ഇൻഷുറൻസ്, കയറ്റുമതി പ്രോൽസാഹനം എന്നിവ സംബന്ധിച്ച വിവിധ കേന്ദ്ര, സംസ്ഥാന സർക്കാർ പദ്ധതികൾക്ക് അർഹരായേക്കാം. ഏറ്റവും പുതിയ പദ്ധതി വിവരങ്ങൾക്ക് ഈ പോർട്ടലിന്റെ പദ്ധതികളും സബ്സിഡികളും വിഭാഗം കാണുക.',
        'കർഷക ഉൽപ്പാദക സംഘടനകൾക്ക് (FPO) ഏതൊക്കെ സർക്കാർ പദ്ധതികൾ ലഭ്യമാണ്?',
    ),
    (
        'Can newly formed FPOs apply for government support schemes?',
        'Yes. Many schemes are specifically designed to support newly formed FPOs. However, eligibility criteria vary depending on the scheme, registration status, membership strength, and operational readiness of the FPO.',
        'അതെ. പുതുതായി രൂപീകരിക്കപ്പെട്ട FPO-കളെ പ്രത്യേകം പിന്തുണയ്ക്കാൻ ലക്ഷ്യം വച്ച് ഒട്ടനവധി പദ്ധതികൾ ഉണ്ട്. എന്നിരുന്നാലും, അർഹതാ മാനദണ്ഡങ്ങൾ പദ്ധതി, രജിസ്ട്രേഷൻ നില, അംഗ ബലം, FPO-യുടെ പ്രവർത്തന സജ്ജത എന്നിവ അനുസരിച്ച് വ്യത്യാസപ്പെടുന്നു.',
        'പുതുതായി രൂപീകരിക്കപ്പെട്ട FPO-കൾക്ക് സർക്കാർ പദ്ധതികൾക്ക് അപ്ലിക്കേഷൻ നൽകാമോ?',
    ),
    (
        'What is the Central Sector Scheme for Formation and Promotion of 10,000 FPOs?',
        'This flagship Government of India programme supports the formation, promotion, handholding, capacity building, and business development of Farmer Producer Organizations through designated implementing agencies and Cluster-Based Business Organizations (CBBOs).',
        '10,000 FPO-കളുടെ രൂപീകരണ, പ്രോൽസാഹന കേന്ദ്ര സർക്കാർ പദ്ധതി, ഇന്ത്യ സർക്കാരിന്റെ ഒരു ഫ്ലാഗ്ഷിപ്പ് പദ്ധതിയാണ്. നിർദ്ദിഷ്ട നടത്തിപ്പ് ഏജൻസികൾ, ക്ലസ്റ്റർ ബേസ്ഡ് ബിസിനസ് ഓർഗനൈസേഷനുകൾ (CBBOs) എന്നിവ വഴി കർഷക ഉൽപ്പാദക സംഘടനകളുടെ രൂപീകരണം, പ്രോൽസാഹനം, കൈത്തിരിനൽ, ശേഷിവികസനം, ബിസിനസ് വികസനം എന്നിവ ഇത് പിന്തുണയ്ക്കുന്നു.',
        '10,000 FPO-കളുടെ രൂപീകരണ, പ്രോൽസാഹന കേന്ദ്ര പദ്ധതി എന്ത്?',
    ),
    (
        'What is the role of SFAC in supporting FPOs?',
        'The Small Farmers Agribusiness Consortium (SFAC) provides support through various initiatives including Equity Grant assistance, Credit Guarantee support, FPO promotion programmes, Market linkage initiatives, and Capacity building activities.',
        'ചെറുകിട കർഷക അഗ്രിബിസിനസ് കൺസോർഷ്യം (SFAC) ഇക്വിറ്റി ഗ്രാന്റ് സഹായം, ക്രെഡിറ്റ് ഗ്യാരണ്ടി പിന്തുണ, FPO പ്രോൽസാഹന പദ്ധതികൾ, വിപണി ബന്ധ സംരംഭങ്ങൾ, ശേഷിവികസന പ്രവർത്തനങ്ങൾ എന്നിവ ഉൾക്കൊള്ളുന്ന വിവിധ സംരംഭങ്ങൾ വഴി FPO-കൾക്ക് പിന്തുണ നൽകുന്നു.',
        'FPO-കളെ പിന്തുണയ്ക്കുന്നതിൽ SFAC-ന്റെ പങ്ക് എന്ത്?',
    ),
    (
        'What is the Equity Grant Fund Scheme?',
        'The Equity Grant Fund Scheme provides matching equity support to eligible FPOs based on member share capital contributions. The objective is to strengthen the net worth of FPOs and improve their ability to access institutional finance.',
        'ഇക്വിറ്റി ഗ്രാന്റ് ഫണ്ട് സ്കീം, അർഹരായ FPO-കൾക്ക് അംഗ ഓഹരി മൂലധന സംഭാവനകൾ അടിസ്ഥാനമാക്കി ഇക്വിറ്റി പിന്തുണ നൽകുന്നു. FPO-കളുടെ നെറ്റ് വർത്ത് ശക്തിപ്പെടുത്തുകയും സ്ഥാപന ധനകാര്യ ലഭ്യത മെച്ചപ്പെടുത്തുകയും ചെയ്യുക എന്നതാണ് ഉദ്ദേശ്യം.',
        'ഇക്വിറ്റി ഗ്രാന്റ് ഫണ്ട് സ്കീം എന്ത്?',
    ),
    (
        'What is the Credit Guarantee Fund Scheme for FPOs?',
        'The Credit Guarantee Fund Scheme provides guarantee cover to lending institutions extending loans to eligible FPOs. This helps improve access to collateral-free credit and reduces lending risks for banks.',
        'ക്രെഡിറ്റ് ഗ്യാരണ്ടി ഫണ്ട് സ്കീം, അർഹരായ FPO-കൾക്ക് വായ്പ നൽകുന്ന ധനകാര്യ സ്ഥാപനങ്ങൾക്ക് ഗ്യാരണ്ടി കവർ നൽകുന്നു. ഇത് ഈടില്ലാ വായ്പ ലഭ്യത മെച്ചപ്പെടുത്താനും ബാങ്കുകൾക്ക് വായ്പ അപകടസാധ്യത കുറയ്ക്കാനും സഹായിക്കുന്നു.',
        'FPO-കൾക്കുള്ള ക്രെഡിറ്റ് ഗ്യാരണ്ടി ഫണ്ട് സ്കീം എന്ത്?',
    ),
    (
        'Can FPOs obtain bank loans?',
        'Yes. FPOs may obtain working capital loans, term loans, infrastructure loans, and business expansion loans from commercial banks, cooperative banks, regional rural banks, and other financial institutions, subject to eligibility and lending norms.',
        'അതെ. FPO-കൾക്ക് അർഹത, വായ്പ നിയമങ്ങൾ എന്നിവ അനുസരിച്ച് വാണിജ്യ ബാങ്കുകൾ, സഹകരണ ബാങ്കുകൾ, പ്രാദേശിക ഗ്രാമീണ ബാങ്കുകൾ, മറ്റ് ധനകാര്യ സ്ഥാപനങ്ങൾ എന്നിവയിൽ നിന്ന് പ്രവർത്തന മൂലധന വായ്പ, ടേം ലോൺ, അടിസ്ഥാന സൗകര്യ വായ്പ, ബിസിനസ് വ്യാപന വായ്പ എന്നിവ ലഭ്യമാക്കാം.',
        'FPO-കൾക്ക് ബാങ്ക് വായ്പ ലഭ്യമാകുമോ?',
    ),
    (
        'What documents are generally required for availing institutional credit?',
        'The following documents are commonly required: Certificate of Incorporation/Registration, PAN, Audited financial statements, Board resolution, Business plan or project report, Bank account details, Shareholding records, and KYC documents of authorised representatives.',
        'സ്ഥാപന വായ്പ ലഭ്യമാക്കുന്നതിന് പൊതുവേ ആവശ്യമായ രേഖകൾ: ഇൻകോർപ്പറേഷൻ/രജിസ്ട്രേഷൻ സർട്ടിഫിക്കറ്റ്, PAN, ഓഡിറ്റ് ചെയ്ത സാമ്പത്തിക പ്രസ്താവനകൾ, ബോർഡ് പ്രമേയം, ബിസിനസ് പ്ലാൻ അല്ലെങ്കിൽ പ്രൊജക്ട് റിപ്പോർട്ട്, ബാങ്ക് അക്കൗണ്ട് വിവരങ്ങൾ, ഓഹരി ഉടമ രേഖകൾ, അധികൃത പ്രതിനിധികളുടെ KYC രേഖകൾ.',
        'സ്ഥാപന വായ്പ ലഭ്യമാക്കുന്നതിന് ഏതൊക്കെ രേഖകൾ ആവശ്യമാണ്?',
    ),
    (
        'What is the Agriculture Infrastructure Fund (AIF)?',
        'The Agriculture Infrastructure Fund is a financing facility that provides medium and long-term debt financing support for agricultural infrastructure projects such as warehouses, cold storages, collection centres, processing units, sorting and grading facilities, and logistics infrastructure.',
        'കൃഷി അടിസ്ഥാന സൗകര്യ നിധി (AIF) ഗോഡൗണുകൾ, ശീതീകരണ സൗകര്യങ്ങൾ, ശേഖരണ കേന്ദ്രങ്ങൾ, സംസ്കരണ ഘടകങ്ങൾ, തരംതിരിക്കൽ, ഗ്രേഡിംഗ് സൗകര്യങ്ങൾ, ലോജിസ്റ്റിക്സ് അടിസ്ഥാന സൗകര്യം തുടങ്ങിയ കൃഷി അടിസ്ഥാന സൗകര്യ പദ്ധതികൾക്ക് ഇടക്കാലവും ദീർഘകാലവുമായ കടം ധനസഹായം നൽകുന്ന ഒരു ധനസഹായ സൗകര്യമാണ്.',
        'കൃഷി അടിസ്ഥാന സൗകര്യ നിധി (AIF) എന്ത്?',
    ),
    (
        'Can FPOs receive assistance for storage and processing infrastructure?',
        'Yes. Various schemes support warehousing, cold storage, processing units, pack houses, collection centres, and value addition facilities through Agriculture Infrastructure Fund (AIF), PMFME, MIDH, and other government programmes.',
        'അതെ. കൃഷി അടിസ്ഥാന സൗകര്യ നിധി (AIF), PMFME, MIDH, മറ്റ് സർക്കാർ പദ്ധതികൾ എന്നിവ വഴി ഗോഡൗൺ, ശീതീകരണ സൗകര്യം, സംസ്കരണ ഘടകങ്ങൾ, പാക് ഹൗസ്, ശേഖരണ കേന്ദ്രങ്ങൾ, മൂല്യ വർദ്ധന സൗകര്യങ്ങൾ എന്നിവ പിന്തുണ ലഭ്യമാണ്.',
        'FPO-കൾക്ക് സംഭരണ, സംസ്കരണ അടിസ്ഥാന സൗകര്യ സഹായം ലഭിക്കുമോ?',
    ),
    (
        'What is PM Formalisation of Micro Food Processing Enterprises (PMFME)?',
        'PMFME is a Government of India programme that supports food processing enterprises through credit-linked capital subsidy, common infrastructure support, branding assistance, marketing support, and capacity building. Eligible FPOs engaged in food processing may apply under the scheme.',
        'PMFME (PM ഫോർമലൈസേഷൻ ഓഫ് മൈക്രോ ഫുഡ് പ്രോസസ്സിംഗ് എന്റർപ്രൈസസ്) ഇന്ത്യ സർക്കാരിന്റെ ഒരു പദ്ധതിയാണ്. ക്രെഡിറ്റ്-ലിങ്ക്ഡ് ക്യാപ്പിറ്റൽ സബ്സിഡി, പൊതു അടിസ്ഥാന സൗകര്യ പിന്തുണ, ബ്രാൻഡിംഗ് സഹായം, വിപണന പിന്തുണ, ശേഷിവികസനം എന്നിവ വഴി ഭക്ഷ്യ സംസ്കരണ സംരംഭങ്ങൾക്ക് ഇത് പിന്തുണ നൽകുന്നു. ഭക്ഷ്യ സംസ്കരണത്തിൽ ഏർപ്പെട്ടിരിക്കുന്ന അർഹരായ FPO-കൾക്ക് ഈ പദ്ധതി പ്രകാരം അപ്ലിക്കേഷൻ നൽകാം.',
        'PM ഫോർമലൈസേഷൻ ഓഫ് മൈക്രോ ഫുഡ് പ്രോസസ്സിംഗ് എന്റർപ്രൈസസ് (PMFME) എന്ത്?',
    ),
    (
        'Can FPOs receive assistance for branding and packaging?',
        'Yes. Certain schemes provide support for brand development, product packaging, marketing materials, product standardisation, and market promotion. The availability of such support depends on the applicable scheme guidelines.',
        'അതെ. ചില പദ്ധതികൾ ബ്രാൻഡ് വികസനം, ഉൽപ്പന്ന പാക്കേജിംഗ്, വിപണന മെറ്റീരിയൽ, ഉൽപ്പന്ന മാനദണ്ഡവൽക്കരണം, വിപണി പ്രോൽസാഹനം എന്നിവ പിന്തുണ നൽകുന്നു. ഇത്തരം സഹായത്തിന്റെ ലഭ്യത ബാധകമായ പദ്ധതി മാർഗ്ഗനിർദ്ദേശങ്ങളെ ആശ്രയിക്കുന്നു.',
        'FPO-കൾക്ക് ബ്രാൻഡിംഗ്, പാക്കേജിംഗ് സഹായം ലഭ്യമാണോ?',
    ),
    (
        'Are there schemes specifically for horticulture-based FPOs?',
        'Yes. Horticulture-based FPOs may be eligible for support under programmes such as Mission for Integrated Development of Horticulture (MIDH), State horticulture programmes, and Infrastructure and value chain development projects.',
        'അതെ. തോട്ടകൃഷി അടിസ്ഥാനമായ FPO-കൾ, ഹോർട്ടികൾച്ചറിനുള്ള ഇന്റഗ്രേറ്റഡ് ഡെവലപ്മെന്റ് മിഷൻ (MIDH), സംസ്ഥാന ഹോർട്ടികൾച്ചർ പദ്ധതികൾ, അടിസ്ഥാന സൗകര്യ, മൂല്യ ശൃംഖല വികസന പദ്ധതികൾ എന്നിവ പ്രകാരം സഹായത്തിന് അർഹരായേക്കാം.',
        'തോട്ടകൃഷി അടിസ്ഥാനമുള്ള FPO-കൾക്ക് പ്രത്യേക പദ്ധതികൾ ഉണ്ടോ?',
    ),
    (
        'Are fisheries and livestock FPOs eligible for government support?',
        'Yes. Producer organizations engaged in fisheries, aquaculture, dairy, livestock, poultry, and allied sectors may be eligible for sector-specific schemes in addition to general FPO support programmes.',
        'അതെ. മത്സ്യബന്ധനം, ജലകൃഷി, ഡെയറി, കന്നുകാലി, കോഴി, അനുബന്ധ മേഖലകളിൽ ഏർപ്പെട്ടിരിക്കുന്ന ഉൽപ്പാദക സംഘടനകൾ, പൊതു FPO പിന്തുണ പദ്ധതികൾക്ക് പുറമേ, മേഖല-നിർദ്ദിഷ്ട പദ്ധതികൾക്ക് അർഹരായേക്കാം.',
        'മത്സ്യബന്ധന, കന്നുകാലി FPO-കൾ സർക്കാർ പിന്തുണയ്ക്ക് അർഹരാണോ?',
    ),
    (
        'What is crop insurance and how can FPO members benefit?',
        'Crop insurance helps farmers manage risks arising from natural calamities, adverse weather conditions, and yield losses. Individual members may avail benefits under applicable crop insurance schemes such as the Pradhan Mantri Fasal Bima Yojana (PMFBY).',
        'വിള ഇൻഷുറൻസ് പ്രകൃതി ദുരന്തങ്ങൾ, പ്രതികൂല കാലാവസ്ഥ, ഉൽപ്പാദന നഷ്ടം എന്നിവ മൂലമുള്ള അപകടസാധ്യതകൾ നിയന്ത്രിക്കാൻ കർഷകരെ സഹായിക്കുന്നു. വ്യക്തിഗത അംഗങ്ങൾക്ക് പ്രധാൻ മന്ത്രി ഫസൽ ബീമ യോജന (PMFBY) പോലുള്ള ബാധകമായ വിള ഇൻഷുറൻസ് പദ്ധതികൾ പ്രകാരം ആനുകൂല്യങ്ങൾ ലഭ്യമാക്കാം.',
        'വിള ഇൻഷുറൻസ് എന്ത്, FPO അംഗങ്ങൾക്ക് എങ്ങനെ ഗുണകരം?',
    ),
    (
        'Can FPOs participate in export promotion programmes?',
        'Yes. Eligible FPOs can participate in export-oriented initiatives and receive support for export readiness, quality certification, packaging improvements, international market linkage, and buyer-seller meets.',
        'അതെ. അർഹരായ FPO-കൾക്ക് കയറ്റുമതി-അധിഷ്ഠിത സംരംഭങ്ങളിൽ പങ്കെടുക്കാനും കയറ്റുമതി സജ്ജത, ഗുണമേന്മ സർട്ടിഫിക്കേഷൻ, പാക്കേജിംഗ് മെച്ചപ്പെടുത്തൽ, അന്താരാഷ്ട്ര വിപണി ബന്ധം, ക്രേതാ-വിക്രേതാ സഭകൾ എന്നിവ പ്രകാരം സഹായം ലഭ്യമാക്കാനും സാധിക്കും.',
        'FPO-കൾക്ക് കയറ്റുമതി പ്രോൽസാഹന പദ്ധതികളിൽ പങ്കെടുക്കാമോ?',
    ),
    (
        'What is meant by market linkage support?',
        'Market linkage support helps FPOs establish connections with wholesalers, retail chains, processors, institutional buyers, government procurement agencies, and exporters. Such linkages improve market access and price realization for members.',
        'വിപണി ബന്ധ പിന്തുണ FPO-കൾക്ക് മൊത്തക്കച്ചവടക്കാർ, ചില്ലറ ശൃംഖലകൾ, സംസ്കരണക്കാർ, സ്ഥാപന വാങ്ങുന്നവർ, സർക്കാർ സംഭരണ ഏജൻസികൾ, കയറ്റുമതിക്കാർ എന്നിവരുമായി ബന്ധം ഉണ്ടാക്കാൻ സഹായിക്കുന്നു. ഇത്തരം ബന്ധങ്ങൾ അംഗങ്ങൾക്ക് വിപണി ലഭ്യതയും വില ലഭ്യതയും മെച്ചപ്പെടുത്തുന്നു.',
        'വിപണി ബന്ധ പിന്തുണ (Market Linkage Support) എന്നാൽ എന്ത്?',
    ),
    (
        'Can FPOs receive training and capacity-building support?',
        'Yes. Capacity-building programmes are offered by institutions such as Kerala Agricultural University, NABARD, SFAC, NCDC, Krishi Vigyan Kendras (KVKs), and the Department of Agriculture Development and Farmers\' Welfare.',
        'അതെ. കേരള കാർഷിക സർവകലാശാല, NABARD, SFAC, NCDC, കൃഷി വിജ്ഞാന കേന്ദ്രങ്ങൾ (KVK), കൃഷി, കർഷക ക്ഷേമ വകുപ്പ് തുടങ്ങിയ സ്ഥാപനങ്ങൾ ശേഷിവികസന പദ്ധതികൾ വാഗ്ദാനം ചെയ്യുന്നു.',
        'FPO-കൾക്ക് പരിശീലന, ശേഷിവികസന പിന്തുണ ലഭ്യമാകുമോ?',
    ),
    (
        'How can an FPO know whether it is eligible for a particular scheme?',
        'Eligibility depends on factors such as legal status of the FPO, years of operation, membership strength, financial performance, business activity, and infrastructure requirements. Users are advised to carefully review scheme guidelines before applying.',
        'ഒരു FPO-യുടെ നിയമ പദവി, പ്രവർത്തന വർഷങ്ങൾ, അംഗ ബലം, സാമ്പത്തിക പ്രകടനം, ബിസിനസ് പ്രവർത്തനം, അടിസ്ഥാന സൗകര്യ ആവശ്യകതകൾ തുടങ്ങിയ ഘടകങ്ങളെ ആശ്രയിക്കുന്നു. അപ്ലിക്കേഷൻ നൽകുന്നതിന് മുമ്പ് ഉപയോക്താക്കൾ ശ്രദ്ധാപൂർവ്വം പദ്ധതി മാർഗ്ഗനിർദ്ദേശങ്ങൾ പരിശോധിക്കണം.',
        'ഒരു FPO ഒരു പ്രത്യേക പദ്ധതിക്ക് അർഹമാണോ എന്ന് എങ്ങനെ അറിയും?',
    ),
    (
        'Does a higher FPO tier improve access to schemes and financial support?',
        'Some programmes may consider governance quality, operational performance, compliance, and institutional strength while assessing applications. A stronger tier classification may improve credibility and readiness for certain opportunities, though scheme eligibility is governed by the specific guidelines of each programme.',
        'ചില പദ്ധതികൾ അപ്ലിക്കേഷനുകൾ വിലയിരുത്തുമ്പോൾ ഭരണ ഗുണമേന്മ, പ്രവർത്തന പ്രകടനം, അനുസരണം, സ്ഥാപന ബലം എന്നിവ പരിഗണിക്കാം. ശക്തമായ ടയർ വർഗ്ഗീകരണം ചില അവസരങ്ങൾക്ക് വിശ്വാസ്യതയും സജ്ജതയും മെച്ചപ്പെടുത്തിയേക്കാം, എന്നിരുന്നാലും പദ്ധതി അർഹത ഓരോ പദ്ധതിയുടെയും നിർദ്ദിഷ്ട മാർഗ്ഗനിർദ്ദേശങ്ങൾ അനുസരിച്ചാണ്.',
        'ഉയർന്ന FPO ടയർ പദ്ധതി, ധനസഹായ ലഭ്യത മെച്ചപ്പെടുത്തുന്നുണ്ടോ?',
    ),
    (
        'Can one FPO avail benefits under multiple schemes?',
        'Yes. Subject to scheme guidelines and eligibility conditions, an FPO may avail support from multiple programmes. However, duplication of assistance for the same activity may not be permitted under certain schemes.',
        'അതെ. പദ്ധതി മാർഗ്ഗനിർദ്ദേശങ്ങൾ, അർഹതാ ഉപാധികൾ എന്നിവ അനുസരിച്ച്, ഒരു FPO ഒന്നിലധികം പദ്ധതികൾ പ്രകാരം പിന്തുണ ലഭ്യമാക്കാം. എന്നിരുന്നാലും, ഒരേ പ്രവർത്തനത്തിന് ഇരട്ടി സഹായം ചില പദ്ധതികൾ പ്രകാരം അനുവദനീയമല്ലായിരിക്കാം.',
        'ഒരു FPO-യ്ക്ക് ഒന്നിലധികം പദ്ധതികൾ പ്രകാരം ആനുകൂല്യം ലഭ്യമാക്കാമോ?',
    ),
    (
        'Are all schemes available throughout the year?',
        'No. Some schemes operate continuously, while others are announced periodically with specific application windows, budget allocations, or project approvals.',
        'ഇല്ല. ചില പദ്ധതികൾ തുടർച്ചയായി പ്രവർത്തിക്കുന്നു, മറ്റുള്ളവ ആനുകാലികമായി നിർദ്ദിഷ്ട അപ്ലിക്കേഷൻ കാലഘട്ടങ്ങൾ, ബജറ്റ് വിഹിതം, അല്ലെങ്കിൽ പദ്ധതി അംഗീകാരങ്ങൾ എന്നിവ ഉള്ളതായി പ്രഖ്യാപിക്കപ്പെടുന്നു.',
        'എല്ലാ പദ്ധതികളും വർഷം മുഴുവൻ ലഭ്യമാണോ?',
    ),
    (
        'Where can I obtain assistance in applying for schemes?',
        'FPOs may seek support from Kerala Agricultural University, NABARD, SFAC, Department of Agriculture Development and Farmers\' Welfare, Krishi Vigyan Kendras (KVKs), Commodity Boards, and Approved consultants and experts listed in the Expert Directory section of this portal.',
        'FPO-കൾ കേരള കാർഷിക സർവകലാശാല, NABARD, SFAC, കൃഷി, കർഷക ക്ഷേമ വകുപ്പ്, കൃഷി വിജ്ഞാന കേന്ദ്രങ്ങൾ (KVK), ചരക്ക് ബോർഡുകൾ, ഈ പോർട്ടലിന്റെ വിദഗ്ധ ഡയറക്ടറി വിഭാഗത്തിൽ ലിസ്റ്റ് ചെയ്ത അംഗീകൃത ഉപദേശകർ, വിദഗ്ധർ എന്നിവരിൽ നിന്ന് സഹായം തേടാം.',
        'പദ്ധതി അപ്ലിക്കേഷനിൽ സഹായം എവിടെ നിന്ന് ലഭ്യമാകും?',
    ),
    (
        'How can I stay updated on newly launched schemes and subsidies?',
        'Users are encouraged to regularly visit the Schemes and Subsidies section of this portal, where new schemes, notifications, application deadlines, and eligibility updates will be published.',
        'ഉപയോക്താക്കൾ ഈ പോർട്ടലിന്റെ പദ്ധതികളും സബ്സിഡികളും വിഭാഗം പതിവായി സന്ദർശിക്കണം. അവിടെ പുതിയ പദ്ധതികൾ, അറിയിപ്പുകൾ, അപ്ലിക്കേഷൻ അവസാന തീയതി, അർഹതാ അപ്ഡേറ്റുകൾ എന്നിവ പ്രസിദ്ധീകരിക്കും.',
        'പുതുതായി ആരംഭിക്കുന്ന പദ്ധതികൾ, സബ്സിഡികൾ എന്നിവ എങ്ങനെ അറിയാം?',
    ),
    (
        'Where can I find official scheme guidelines and application links?',
        'Each scheme listed in the Schemes and Subsidies section contains scheme description, eligibility criteria, benefit details, application process, official website links, and relevant documents and notifications where available.',
        'പദ്ധതികളും സബ്സിഡികളും വിഭാഗത്തിൽ ലിസ്റ്റ് ചെയ്ത ഓരോ പദ്ധതിയിലും പദ്ധതി വിവരണം, അർഹതാ മാനദണ്ഡങ്ങൾ, ആനുകൂല്യ വിവരങ്ങൾ, അപ്ലിക്കേഷൻ പ്രക്രിയ, ഔദ്യോഗിക വെബ്സൈറ്റ് ലിങ്കുകൾ, ലഭ്യമായ പ്രസക്ത രേഖകൾ, അറിയിപ്പുകൾ എന്നിവ ഉൾക്കൊള്ളുന്നു.',
        'ഔദ്യോഗിക പദ്ധതി മാർഗ്ഗനിർദ്ദേശങ്ങളും അപ്ലിക്കേഷൻ ലിങ്കുകളും എവിടെ കിട്ടും?',
    ),
    (
        'What is the NABARD Producer Organization Development Fund (PODF)?',
        'The NABARD PODF provides capacity building support, grant assistance, and business development funding for Producer Organizations and FPOs through NABARD regional offices and implementing agencies.',
        'NABARD ഉൽപ്പാദക സംഘടന വികസന നിധി (PODF), NABARD പ്രാദേശിക ഓഫീസുകൾ, നടത്തിപ്പ് ഏജൻസികൾ എന്നിവ വഴി ഉൽപ്പാദക സംഘടനകൾക്കും FPO-കൾക്കും ശേഷിവികസന പിന്തുണ, ഗ്രാന്റ് സഹായം, ബിസിനസ് വികസന ഫണ്ടിംഗ് നൽകുന്നു.',
        'NABARD ഉൽപ്പാദക സംഘടന വികസന നിധി (PODF) എന്ത്?',
    ),
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
    for i, (q_en, a_en, a_ml, q_ml) in enumerate(FPO_GENERAL_FAQS, start=1):
        FAQ.objects.create(
            question={'en': q_en, 'ml': q_ml},
            answer={'en': a_en, 'ml': a_ml},
            category=FAQCategory.FPO_GENERAL,
            order=i,
        )
        faq_count += 1

    for i, (q_en, a_en, a_ml, q_ml) in enumerate(SCHEMES_FAQS, start=1):
        FAQ.objects.create(
            question={'en': q_en, 'ml': q_ml},
            answer={'en': a_en, 'ml': a_ml},
            category=FAQCategory.SCHEMES,
            order=i,
        )
        faq_count += 1

    print(f'FAQs: {faq_count} seeded ({len(FPO_GENERAL_FAQS)} FPO general + {len(SCHEMES_FAQS)} schemes).')
    print('Done.')
