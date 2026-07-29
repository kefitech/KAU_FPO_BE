"""
Seed FPO Master Data
====================

Seeds MasterLookup entries for all FPO registration dropdowns:
  1. legal_structure      — legal acts under which FPOs can register
  2. signatory_designation — designations for the signatory field
  3. promoting_agency     — promoting/implementing agencies
  4. block                — Kerala blocks per district (fixed, 180 blocks)
  5. commodity            — commodity master list (EN + ML, from KAU June 2026)
  6. bank_name            — major Indian banks for Step 4

All entries use update_or_create — safe to re-run.
Translations seeded in Translation table (category = MasterLookup.category).

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/seed_fpo_master_data.py').read())
    seed_fpo_master_data()
    "
"""


def seed_fpo_master_data():
    from apps.core.models.generic import MasterLookup
    from apps.database.models import Language, TranslationCategory, Translation

    lang_en = Language.objects.get(code='en')
    lang_ml = Language.objects.get(code='ml')

    def _seed_lookup(category, entries, category_label, category_desc):
        """Helper: seed MasterLookup + Translation rows for a category."""
        cat, _ = TranslationCategory.objects.get_or_create(
            code=category,
            defaults={'name': category_label, 'description': category_desc},
        )
        for i, entry in enumerate(entries):
            MasterLookup.objects.update_or_create(
                category=category, code=entry['code'],
                defaults={
                    'description': entry.get('description', ''),
                    'display_order': i,
                    'is_active': True,
                    'metadata': entry.get('metadata', {}),
                },
            )
            Translation.objects.update_or_create(
                category=cat, key=entry['code'], language=lang_en,
                defaults={'value': entry['en']},
            )
            Translation.objects.update_or_create(
                category=cat, key=entry['code'], language=lang_ml,
                defaults={'value': entry.get('ml', entry['en'])},
            )
        print(f"  {category}: {len(entries)} entries seeded")

    # ──────────────────────────────────────────────────────────────────────────
    # 1. Legal Structure
    # ──────────────────────────────────────────────────────────────────────────
    _seed_lookup('legal_structure', [
        {'code': 'companies_act',      'en': 'Companies Act 2013',                             'ml': 'കമ്പനി നിയമം 2013',                                  'metadata': {'requires_cin': True}},
        {'code': 'producer_companies', 'en': 'Producer Companies Act',                          'ml': 'പ്രൊഡ്യൂസർ കമ്പനീസ് ആക്ട്',                          'metadata': {'requires_cin': True}},
        {'code': 'kerala_cooperative', 'en': 'Kerala Co-operative Societies Act 1969',          'ml': 'കേരള സഹകരണ സംഘം ആക്ട് 1969',                        'metadata': {'requires_cin': False}},
        {'code': 'societies_act',      'en': 'Societies Registration Act 1860',                 'ml': 'സൊസൈറ്റീസ് രജിസ്ട്രേഷൻ ആക്ട് 1860',                 'metadata': {'requires_cin': False}},
        {'code': 'multistate_coop',    'en': 'Multi-State Co-operative Societies Act 2002',     'ml': 'മൾട്ടി-സ്റ്റേറ്റ് സഹകരണ സംഘം ആക്ട് 2002',           'metadata': {'requires_cin': False}},
        {'code': 'state_specific_csa', 'en': 'State-Specific Co-operative Societies Act',       'ml': 'സംസ്ഥാന-നിർദ്ദിഷ്ട സഹകരണ സംഘം ആക്ട്',               'metadata': {'requires_cin': False, 'has_sub_dropdown': True}},
        {'code': 'other',              'en': 'Other',                                           'ml': 'മറ്റ്',                                              'metadata': {'requires_cin': False}},
    ], 'Legal Structure', 'Legal acts under which FPOs register')

    # ──────────────────────────────────────────────────────────────────────────
    # 1b. State-specific CSA sub-options
    # ──────────────────────────────────────────────────────────────────────────
    state_csa_acts = [
        'Andaman and Nicobar Islands Co-operative Societies Regulation, 1973',
        'Andhra Pradesh Co-operative Societies Act, 1964',
        'Andhra Pradesh Mutually Aided Co-operative Societies (MACS) Act, 1995',
        'Arunachal Pradesh Co-operative Societies Act, 1978',
        'Assam Co-operative Societies Act, 2007',
        'Bihar Co-operative Societies Act, 1935',
        'Bihar Self-Reliant Co-operative Societies Act, 1997',
        'Chattisgarh Co-operative Societies Act, 1960',
        'Chattisgarh Swayatta Sahakari Adhiniyam, 1999',
        'Delhi Co-operative Societies Act, 2003',
        'Goa Co-operative Societies Act, 2001',
        'Gujarat Co-operative Societies Act, 1961',
        'Haryana Co-operative Societies Act, 1984',
        'Himachal Pradesh Co-operative Societies Act, 1968',
        'Jammu & Kashmir Co-operative Societies Act, 1989',
        'Jharkhand Self-Reliant Co-operative Societies Act, 2002',
        'Jharkhand Co-operative Societies Act, 2008',
        'Karnataka Co-operative Societies Act, 1959',
        'Karnataka Souharda Sahakari Act, 1997',
        'Kerala Co-operative Societies Act, 1969',
        'Lakshadweep Co-operative Societies Regulation, 1960',
        'Madhya Pradesh Co-operative Societies Act, 1960',
        'Madhya Pradesh Swayatta Sahakari Adhiniyam, 1999',
        'Maharashtra Co-operative Societies Act, 1960',
        'Manipur Co-operative Societies Act, 1976',
        'Meghalaya Co-operative Societies Act, 2015',
        'Mizoram Co-operative Societies Act, 2006',
        'Nagaland Co-operative Societies Act, 2017',
        'Odisha Co-operative Societies Act, 1962',
        'Odisha Self-Reliant Co-operative Societies Act, 2001',
        'Puducherry Co-operative Societies Act, 1972',
        'Punjab Co-operative Societies Act, 1961',
        'Rajasthan Co-operative Societies Act, 2001',
        'Sikkim Co-operative Societies Act, 1978',
        'Tamil Nadu Co-operative Societies Act, 1983',
        'Telangana Co-operative Societies Act, 1964',
        'Telangana Mutually Aided Co-operative Societies (MACS) Act, 1995',
        'Tripura Co-operative Societies Act, 1974',
        'Uttar Pradesh Co-operative Societies Act, 1965',
        'Uttarakhand Co-operative Societies Act, 2003',
        'West Bengal Co-operative Societies Act, 2006',
    ]

    import re
    csa_entries = []
    for act in state_csa_acts:
        code = re.sub(r'[^a-z0-9]+', '_', act.lower()).strip('_')[:50]
        csa_entries.append({'code': code, 'en': act, 'ml': act, 'metadata': {'parent': 'state_specific_csa'}})

    cat_csa, _ = TranslationCategory.objects.get_or_create(
        code='state_csa_act',
        defaults={'name': 'State CSA Acts', 'description': 'State-specific cooperative societies acts'},
    )
    for i, entry in enumerate(csa_entries):
        MasterLookup.objects.update_or_create(
            category='state_csa_act', code=entry['code'],
            defaults={'description': entry['en'], 'display_order': i, 'is_active': True, 'metadata': entry['metadata']},
        )
        Translation.objects.update_or_create(
            category=cat_csa, key=entry['code'], language=lang_en,
            defaults={'value': entry['en']},
        )
        Translation.objects.update_or_create(
            category=cat_csa, key=entry['code'], language=lang_ml,
            defaults={'value': entry['ml']},
        )
    print(f"  state_csa_act: {len(csa_entries)} entries seeded")

    # ──────────────────────────────────────────────────────────────────────────
    # 2. Signatory Designation
    # ──────────────────────────────────────────────────────────────────────────
    _seed_lookup('signatory_designation', [
        {'code': 'chairperson',       'en': 'Chairperson',                    'ml': 'ചെയർപേഴ്‌സൺ'},
        {'code': 'chairman',          'en': 'Chairman',                       'ml': 'ചെയർമാൻ'},
        {'code': 'president',         'en': 'President',                      'ml': 'പ്രസിഡന്റ്'},
        {'code': 'managing_director', 'en': 'Managing Director',               'ml': 'മാനേജിംഗ് ഡയറക്ടർ'},
        {'code': 'director',          'en': 'Director',                       'ml': 'ഡയറക്ടർ'},
        {'code': 'ceo',               'en': 'Chief Executive Officer (CEO)',   'ml': 'ചീഫ് എക്സിക്യൂട്ടീവ് ഓഫീസർ (CEO)'},
        {'code': 'general_manager',   'en': 'General Manager',                'ml': 'ജനറൽ മാനേജർ'},
        {'code': 'company_secretary', 'en': 'Company Secretary',              'ml': 'കമ്പനി സെക്രട്ടറി'},
        {'code': 'other',             'en': 'Other (Specify)',                 'ml': 'മറ്റ് (വ്യക്തമാക്കുക)'},
    ], 'Signatory Designation', 'Designations for FPO authorized signatories')

    # ──────────────────────────────────────────────────────────────────────────
    # 3. Promoting Agency
    # ──────────────────────────────────────────────────────────────────────────
    _seed_lookup('promoting_agency', [
        {'code': 'sfac',   'en': "Small Farmers' Agri-Business Consortium (SFAC)",                                     'ml': 'സ്‌മോൾ ഫാർമേഴ്‌സ് അഗ്രി-ബിസിനസ് കൺസോർഷ്യം (SFAC)'},
        {'code': 'nabard', 'en': 'National Bank for Agriculture and Rural Development (NABARD)',                        'ml': 'നാഷണൽ ബാങ്ക് ഫോർ അഗ്രിക്കൾച്ചർ ആൻഡ് റൂറൽ ഡെവലപ്‌മെന്റ് (NABARD)'},
        {'code': 'ncdc',   'en': 'National Cooperative Development Corporation (NCDC)',                                 'ml': 'നാഷണൽ കോ-ഓപ്പറേറ്റീവ് ഡെവലപ്‌മെന്റ് കോർപ്പറേഷൻ (NCDC)'},
        {'code': 'nafed',  'en': 'National Agricultural Cooperative Marketing Federation of India Ltd. (NAFED)',        'ml': 'നാഷണൽ അഗ്രിക്കൾച്ചറൽ കോ-ഓപ്പറേറ്റീവ് മാർക്കറ്റിംഗ് ഫെഡറേഷൻ ഓഫ് ഇന്ത്യ (NAFED)'},
        {'code': 'fdrvc',  'en': 'Foundation for Development of Rural Value Chains (FDRVC)',                            'ml': 'ഫൗണ്ടേഷൻ ഫോർ ഡെവലപ്‌മെന്റ് ഓഫ് റൂറൽ വാല്യൂ ചെയ്‌ൻസ് (FDRVC)'},
        {'code': 'nddb',   'en': 'National Dairy Development Board (NDDB)',                                             'ml': 'നാഷണൽ ഡെയറി ഡെവലപ്‌മെന്റ് ബോർഡ് (NDDB)'},
        {'code': 'others', 'en': 'Others (specify)',                                                                    'ml': 'മറ്റുള്ളവ (വ്യക്തമാക്കുക)'},
    ], 'Promoting Agency', 'Promoting/implementing agencies for FPOs')

    # ──────────────────────────────────────────────────────────────────────────
    # 4. Kerala Blocks (180 blocks per district)
    # ──────────────────────────────────────────────────────────────────────────
    KERALA_BLOCKS = {
        'ALP': ['Ambalappuzha', 'Aryad', 'Bharanikkavu', 'Champakulam', 'Chengannur',
                'Harippad', 'Kanjikuzhy', 'Mavelikkara', 'Muthukulam', 'Pattanakkad',
                'Thycattussery', 'Veliyanad'],
        'EKM': ['Alangad', 'Angamaly', 'Edappally', 'Koovappady', 'Kothamangalam',
                'Mulanthuruthy', 'Muvattupuzha', 'Palluruthy', 'Pampakuda', 'Parakkadavu',
                'Paravur', 'Vadavucode', 'Vazhakulam', 'Vypin'],
        'IDK': ['Adimali', 'Azhutha', 'Devikulam', 'Elemdesam', 'Idukki',
                'Kattappana', 'Nedumkandam', 'Thodupuzha'],
        'KNR': ['Edakkad', 'Irikkur', 'Iritty', 'Kalliasseri', 'Kannur',
                'Kuthuparamba', 'Panoor', 'Payyannur', 'Peravoor', 'Taliparamba', 'Thalassery'],
        'KSD': ['Kanhangad', 'Karadka', 'Kasaragod', 'Manjeshwar', 'Nileshwara', 'Parappa'],
        'KLM': ['Anchal', 'Chadayamangalam', 'Chavara', 'Chittumala', 'Ithikkara',
                'Kottarakkara', 'Mukhathala', 'Oachira', 'Pathanapuram', 'Sasthamcottah', 'Vettikkavala'],
        'KTM': ['Erattupetta', 'Ettumanoor', 'Kaduthuruthy', 'Kanjirappally', 'Lalam',
                'Madappally', 'Pallom', 'Pampady', 'Uzhavoor', 'Vaikom', 'Vazhoor'],
        'KZD': ['Balusseri', 'Chelannur', 'Koduvally', 'Kozhikode', 'Kunnamangalam',
                'Kunnummal', 'Melady', 'Panthalayani', 'Perambra', 'Thodannur',
                'Thuneri', 'Vadakara'],
        'MLP': ['Areakode', 'Kalikavu', 'Kondotty', 'Kuttippuram', 'Malappuram',
                'Mankada', 'Nilambur', 'Perinthalmanna', 'Perumpadappu', 'Ponnani',
                'Tanur', 'Tirur', 'Tirurangadi', 'Vengara', 'Wandoor'],
        'PKD': ['Alathur', 'Attappadi', 'Chittur', 'Kollengode', 'Kuzhalmannam',
                'Malampuzha', 'Mannarkad', 'Nemmara', 'Ottappalam', 'Palakkad',
                'Pattambi', 'Sreekrishnapuram', 'Trithala'],
        'PTA': ['Elanthoor', 'Koipuram', 'Konni', 'Mallappally', 'Pandalam',
                'Parakode', 'Pulikeezhu', 'Ranni'],
        'TVM': ['Athiyannur', 'Chirayinkeezhu', 'Kilimanoor', 'Nedumangad', 'Nemom',
                'Parassala', 'Perumkadavila', 'Pothencode', 'Vamanapuram', 'Varkala', 'Vellanad'],
        'TSR': ['Anthikkad', 'Chalakudy', 'Chavakkad', 'Cherpu', 'Chowannur',
                'Irinjalakkuda', 'Kodakara', 'Mala', 'Mathilakam', 'Mullassery',
                'Ollukkara', 'Pazhayannur', 'Puzhakkal', 'Thalikkulam',
                'Vellangallur', 'Wadakkanchery'],
        'WYD': ['Kalpetta', 'Mananthavady', 'Panamaram', 'Sulthan Bathery'],
    }

    cat_block, _ = TranslationCategory.objects.get_or_create(
        code='block',
        defaults={'name': 'Kerala Blocks', 'description': 'Administrative blocks per Kerala district'},
    )
    total_blocks = 0
    for district_code, blocks in KERALA_BLOCKS.items():
        for i, block_name in enumerate(blocks):
            code = import_re().sub(r'[^a-z0-9]+', '_', block_name.lower()).strip('_')
            MasterLookup.objects.update_or_create(
                category='block', code=code,
                defaults={
                    'description': block_name,
                    'display_order': i,
                    'is_active': True,
                    'metadata': {'district': district_code},
                },
            )
            Translation.objects.update_or_create(
                category=cat_block, key=code, language=lang_en,
                defaults={'value': block_name},
            )
            Translation.objects.update_or_create(
                category=cat_block, key=code, language=lang_ml,
                defaults={'value': block_name},
            )
            total_blocks += 1
    print(f"  block: {total_blocks} entries seeded across 14 districts")

    # ──────────────────────────────────────────────────────────────────────────
    # 5. Commodity Master List (KAU confirmed, June 2026)
    # ──────────────────────────────────────────────────────────────────────────
    COMMODITIES = [
        # Major Agricultural Commodities
        {'code': 'rice_paddy',           'en': 'Rice / Paddy',                               'ml': 'നെല്ല്',                                    'metadata': {'section': 'agricultural'}},
        {'code': 'wheat',                'en': 'Wheat',                                      'ml': 'ഗോതമ്പ്',                                   'metadata': {'section': 'agricultural'}},
        {'code': 'finger_millet',        'en': 'Finger Millet (Ragi)',                        'ml': 'റാഗി',                                      'metadata': {'section': 'agricultural'}},
        {'code': 'little_millet',        'en': 'Little Millet',                               'ml': 'ചാമ',                                       'metadata': {'section': 'agricultural'}},
        {'code': 'pearl_millet',         'en': 'Pearl Millet (Bajra)',                         'ml': 'കംബു / ബാജ്ര',                              'metadata': {'section': 'agricultural'}},
        {'code': 'sorghum',              'en': 'Sorghum',                                    'ml': 'ചോളം',                                      'metadata': {'section': 'agricultural'}},
        {'code': 'foxtail_millet',       'en': 'Foxtail Millet',                              'ml': 'തിന',                                       'metadata': {'section': 'agricultural'}},
        {'code': 'sesame',               'en': 'Sesame',                                     'ml': 'എള്ള്',                                     'metadata': {'section': 'agricultural'}},
        {'code': 'tapioca_cassava',      'en': 'Tapioca / Cassava',                           'ml': 'കപ്പ',                                      'metadata': {'section': 'agricultural'}},
        {'code': 'arrowroot',            'en': 'Arrowroot',                                  'ml': 'കൂവ',                                       'metadata': {'section': 'agricultural'}},
        {'code': 'coconut',              'en': 'Coconut',                                    'ml': 'തെങ്ങ് / തേങ്ങ',                            'metadata': {'section': 'agricultural'}},
        {'code': 'arecanut',             'en': 'Arecanut',                                   'ml': 'അടയ്ക്ക',                                   'metadata': {'section': 'agricultural'}},
        {'code': 'rubber',               'en': 'Rubber',                                     'ml': 'റബ്ബർ',                                     'metadata': {'section': 'agricultural'}},
        {'code': 'coffee',               'en': 'Coffee',                                     'ml': 'കാപ്പി',                                    'metadata': {'section': 'agricultural'}},
        {'code': 'black_pepper',         'en': 'Black Pepper',                               'ml': 'കുരുമുളക്',                                 'metadata': {'section': 'agricultural'}},
        {'code': 'cardamom',             'en': 'Cardamom',                                   'ml': 'ഏലം',                                       'metadata': {'section': 'agricultural'}},
        {'code': 'nutmeg',               'en': 'Nutmeg',                                     'ml': 'ജാതിക്ക',                                   'metadata': {'section': 'agricultural'}},
        {'code': 'cinnamon',             'en': 'Cinnamon',                                   'ml': 'കറുവപ്പട്ട',                                'metadata': {'section': 'agricultural'}},
        {'code': 'cocoa',                'en': 'Cocoa',                                      'ml': 'കൊക്കോ',                                    'metadata': {'section': 'agricultural'}},
        {'code': 'chilli',               'en': 'Chilli',                                     'ml': 'മുളക്',                                     'metadata': {'section': 'agricultural'}},
        {'code': 'coriander',            'en': 'Coriander',                                  'ml': 'മല്ലി',                                     'metadata': {'section': 'agricultural'}},
        {'code': 'turmeric',             'en': 'Turmeric',                                   'ml': 'മഞ്ഞൾ',                                     'metadata': {'section': 'agricultural'}},
        {'code': 'ginger',               'en': 'Ginger',                                     'ml': 'ഇഞ്ചി',                                     'metadata': {'section': 'agricultural'}},
        {'code': 'tamarind',             'en': 'Tamarind',                                   'ml': 'പുളി',                                      'metadata': {'section': 'agricultural'}},
        {'code': 'honey',                'en': 'Honey',                                      'ml': 'തേൻ',                                       'metadata': {'section': 'agricultural'}},
        {'code': 'mushroom',             'en': 'Mushroom',                                   'ml': 'കൂൺ',                                       'metadata': {'section': 'agricultural'}},
        {'code': 'poultry',              'en': 'Poultry (Egg & Chicks)',                      'ml': 'കോഴിവളർത്തൽ',                              'metadata': {'section': 'agricultural'}},
        {'code': 'organic_farm_produce', 'en': 'Organic Farm Produce',                       'ml': 'ജൈവ കാർഷിക ഉൽപ്പന്നങ്ങൾ',                 'metadata': {'section': 'agricultural'}},
        # Horticultural — Fruits
        {'code': 'banana',               'en': 'Banana',                                     'ml': 'വാഴപ്പഴം',                                  'metadata': {'section': 'horticultural_fruits'}},
        {'code': 'jackfruit',            'en': 'Jackfruit',                                  'ml': 'ചക്ക',                                      'metadata': {'section': 'horticultural_fruits'}},
        {'code': 'mango',                'en': 'Mango',                                      'ml': 'മാങ്ങ',                                     'metadata': {'section': 'horticultural_fruits'}},
        {'code': 'pineapple',            'en': 'Pineapple',                                  'ml': 'കൈതച്ചക്ക',                                 'metadata': {'section': 'horticultural_fruits'}},
        {'code': 'papaya',               'en': 'Papaya',                                     'ml': 'പപ്പായ',                                    'metadata': {'section': 'horticultural_fruits'}},
        {'code': 'passion_fruit',        'en': 'Passion Fruit',                              'ml': 'പാഷൻ ഫ്രൂട്ട്',                            'metadata': {'section': 'horticultural_fruits'}},
        {'code': 'guava',                'en': 'Guava',                                      'ml': 'പേരയ്ക്ക',                                  'metadata': {'section': 'horticultural_fruits'}},
        # Horticultural — Vegetables
        {'code': 'bitter_gourd',         'en': 'Bitter Gourd',                               'ml': 'പാവയ്ക്ക',                                  'metadata': {'section': 'horticultural_vegetables'}},
        {'code': 'cucumber',             'en': 'Cucumber',                                   'ml': 'വെള്ളരി',                                   'metadata': {'section': 'horticultural_vegetables'}},
        {'code': 'peas',                 'en': 'Peas',                                       'ml': 'പയർ',                                       'metadata': {'section': 'horticultural_vegetables'}},
        {'code': 'drumstick',            'en': 'Drumstick / Moringa',                         'ml': 'മുരിങ്ങ',                                   'metadata': {'section': 'horticultural_vegetables'}},
        {'code': 'banana_stem',          'en': 'Banana Stem',                                'ml': 'വാഴത്തണ്ട്',                               'metadata': {'section': 'horticultural_vegetables'}},
        {'code': 'mixed_vegetables',     'en': 'Mixed Vegetables',                           'ml': 'പച്ചക്കറികൾ',                              'metadata': {'section': 'horticultural_vegetables'}},
        # Horticultural — Tuber Crops
        {'code': 'tapioca_tuber',        'en': 'Tapioca',                                    'ml': 'കപ്പ',                                      'metadata': {'section': 'horticultural_tubers'}},
        {'code': 'arrowroot_tuber',      'en': 'Arrowroot',                                  'ml': 'കൂവ',                                       'metadata': {'section': 'horticultural_tubers'}},
        {'code': 'other_tuber_crops',    'en': 'Other Tuber Crops',                          'ml': 'മറ്റു കിഴങ്ങുവർഗങ്ങൾ',                    'metadata': {'section': 'horticultural_tubers'}},
        # Value-Added Categories
        {'code': 'rice_value_added',     'en': 'Rice-based Value Added Products',            'ml': 'നെല്ല്/അരി അധിഷ്ഠിത മൂല്യവർദ്ധിത ഉൽപ്പന്നങ്ങൾ',    'metadata': {'section': 'value_added'}},
        {'code': 'millet_value_added',   'en': 'Millet-based Value Added Products',          'ml': 'മില്ലറ്റ് അധിഷ്ഠിത മൂല്യവർദ്ധിത ഉൽപ്പന്നങ്ങൾ',         'metadata': {'section': 'value_added'}},
        {'code': 'banana_value_added',   'en': 'Banana Value Added Products',                'ml': 'വാഴപ്പഴ മൂല്യവർദ്ധിത ഉൽപ്പന്നങ്ങൾ',                 'metadata': {'section': 'value_added'}},
        {'code': 'jackfruit_value_added','en': 'Jackfruit Value Added Products',             'ml': 'ചക്ക മൂല്യവർദ്ധിത ഉൽപ്പന്നങ്ങൾ',                     'metadata': {'section': 'value_added'}},
        {'code': 'tapioca_value_added',  'en': 'Tapioca Value Added Products',               'ml': 'കപ്പ മൂല്യവർദ്ധിത ഉൽപ്പന്നങ്ങൾ',                      'metadata': {'section': 'value_added'}},
        {'code': 'mango_value_added',    'en': 'Mango Value Added Products',                 'ml': 'മാങ്ങ മൂല്യവർദ്ധിത ഉൽപ്പന്നങ്ങൾ',                     'metadata': {'section': 'value_added'}},
        {'code': 'pineapple_value_added','en': 'Pineapple Value Added Products',             'ml': 'കൈതച്ചക്ക മൂല്യവർദ്ധിത ഉൽപ്പന്നങ്ങൾ',               'metadata': {'section': 'value_added'}},
        {'code': 'coconut_value_added',  'en': 'Coconut Value Added Products',               'ml': 'തേങ്ങ മൂല്യവർദ്ധിത ഉൽപ്പന്നങ്ങൾ',                     'metadata': {'section': 'value_added'}},
        {'code': 'spice_value_added',    'en': 'Spice Value Added Products',                 'ml': 'സുഗന്ധവ്യഞ്ജന മൂല്യവർദ്ധിത ഉൽപ്പന്നങ്ങൾ',              'metadata': {'section': 'value_added'}},
        {'code': 'turmeric_value_added', 'en': 'Turmeric Value Added Products',              'ml': 'മഞ്ഞൾ മൂല്യവർദ്ധിത ഉൽപ്പന്നങ്ങൾ',                      'metadata': {'section': 'value_added'}},
        {'code': 'ginger_value_added',   'en': 'Ginger Value Added Products',                'ml': 'ഇഞ്ചി മൂല്യവർദ്ധിത ഉൽപ്പന്നങ്ങൾ',                      'metadata': {'section': 'value_added'}},
        {'code': 'honey_products',       'en': 'Honey-based Products',                       'ml': 'തേൻ അധിഷ്ഠിത ഉൽപ്പന്നങ്ങൾ',                          'metadata': {'section': 'value_added'}},
        {'code': 'mushroom_value_added', 'en': 'Mushroom Value Added Products',              'ml': 'കൂൺ മൂല്യവർദ്ധിത ഉൽപ്പന്നങ്ങൾ',                       'metadata': {'section': 'value_added'}},
        {'code': 'fruit_processing',     'en': 'Fruit Processing Products',                  'ml': 'പഴവർഗ സംസ്കരിത ഉൽപ്പന്നങ്ങൾ',                        'metadata': {'section': 'value_added'}},
        {'code': 'vegetable_processing', 'en': 'Vegetable Processing Products',              'ml': 'പച്ചക്കറി സംസ്കരിത ഉൽപ്പന്നങ്ങൾ',                    'metadata': {'section': 'value_added'}},
        {'code': 'tuber_processing',     'en': 'Tuber Crop Processing Products',             'ml': 'കിഴങ്ങുവർഗ സംസ്കരിത ഉൽപ്പന്നങ്ങൾ',                   'metadata': {'section': 'value_added'}},
        {'code': 'spice_processing',     'en': 'Spice Processing Products',                  'ml': 'സുഗന്ധവ്യഞ്ജന സംസ്കരണ ഉൽപ്പന്നങ്ങൾ',                 'metadata': {'section': 'value_added'}},
        {'code': 'bakery_products',      'en': 'Bakery Products',                            'ml': 'ബേക്കറി ഉൽപ്പന്നങ്ങൾ',                               'metadata': {'section': 'value_added'}},
        {'code': 'health_foods',         'en': 'Traditional Health Foods / Nutritional Mixes','ml': 'ആരോഗ്യ മിശ്രിതങ്ങൾ / പോഷകാഹാര ഉൽപ്പന്നങ്ങൾ',           'metadata': {'section': 'value_added'}},
    ]
    _seed_lookup('commodity', COMMODITIES, 'Commodity', 'Agricultural commodities for FPO registration')

    # ──────────────────────────────────────────────────────────────────────────
    # 6. Major Banks (common Indian banks for Step 4 bank name dropdown)
    # ──────────────────────────────────────────────────────────────────────────
    BANKS = [
        'State Bank of India', 'Canara Bank', 'Bank of Baroda', 'Union Bank of India',
        'Punjab National Bank', 'Bank of India', 'Indian Bank', 'Central Bank of India',
        'UCO Bank', 'Indian Overseas Bank', 'Bank of Maharashtra', 'Punjab & Sind Bank',
        'HDFC Bank', 'ICICI Bank', 'Axis Bank', 'Kotak Mahindra Bank', 'Yes Bank',
        'IDFC FIRST Bank', 'Federal Bank', 'South Indian Bank', 'Dhanlaxmi Bank',
        'Karnataka Bank', 'Catholic Syrian Bank', 'Karur Vysya Bank',
        'Kerala Gramin Bank', 'Canara Bank (Gramin)', 'NABARD',
        'Kerala State Co-operative Bank', 'District Co-operative Bank',
        'Primary Agricultural Credit Society (PACS)',
        'Other',
    ]
    bank_entries = []
    for bank in BANKS:
        import re as re2
        code = re2.sub(r'[^a-z0-9]+', '_', bank.lower()).strip('_')[:50]
        bank_entries.append({'code': code, 'en': bank, 'ml': bank})
    _seed_lookup('bank_name', bank_entries, 'Bank Names', 'Banks for FPO Step 4 bank details')

    print('\nFPO master data seeded successfully.')
    print('Run seed_menu() and seed_fpo_permissions() if not already done.')


def import_re():
    import re
    return re
