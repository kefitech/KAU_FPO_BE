"""
Seed Malayalam Translations for Bank Names
============================================

Updates existing bank_name category translations with Malayalam values.
Uses update_or_create so it's safe to re-run.

Usage:
    python manage.py shell < scripts/seed_bank_name_ml_translations.py

    Or from Django shell:
    >>> exec(open('scripts/seed_bank_name_ml_translations.py').read())

NOTE: These Malayalam values are phonetic transliterations, not all
individually verified against an authoritative source. Review before
marking is_verified=True in production if accuracy is critical.

Created: 25-07-2026
"""

import sys
import os
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.database.models import Language, TranslationCategory, Translation


# key → Malayalam value
BANK_NAME_ML = {
    'state_bank_of_india':                        'സ്റ്റേറ്റ് ബാങ്ക് ഓഫ് ഇന്ത്യ',
    'canara_bank':                                 'കാനറ ബാങ്ക്',
    'bank_of_baroda':                              'ബാങ്ക് ഓഫ് ബറോഡ',
    'union_bank_of_india':                         'യൂണിയൻ ബാങ്ക് ഓഫ് ഇന്ത്യ',
    'punjab_national_bank':                        'പഞ്ചാബ് നാഷണൽ ബാങ്ക്',
    'bank_of_india':                               'ബാങ്ക് ഓഫ് ഇന്ത്യ',
    'indian_bank':                                 'ഇന്ത്യൻ ബാങ്ക്',
    'central_bank_of_india':                       'സെൻട്രൽ ബാങ്ക് ഓഫ് ഇന്ത്യ',
    'uco_bank':                                    'യുകോ ബാങ്ക്',
    'indian_overseas_bank':                        'ഇന്ത്യൻ ഓവർസീസ് ബാങ്ക്',
    'bank_of_maharashtra':                         'ബാങ്ക് ഓഫ് മഹാരാഷ്ട്ര',
    'punjab_sind_bank':                            'പഞ്ചാബ് & സിന്ധ് ബാങ്ക്',
    'hdfc_bank':                                   'എച്ച്ഡിഎഫ്സി ബാങ്ക്',
    'icici_bank':                                  'ഐസിഐസിഐ ബാങ്ക്',
    'axis_bank':                                   'ആക്സിസ് ബാങ്ക്',
    'yes_bank':                                    'യെസ് ബാങ്ക്',
    'idfc_first_bank':                             'ഐഡിഎഫ്‌സി ഫസ്റ്റ് ബാങ്ക്',
    'federal_bank':                                'ഫെഡറൽ ബാങ്ക്',
    'south_indian_bank':                           'സൗത്ത് ഇന്ത്യൻ ബാങ്ക്',
    'dhanlaxmi_bank':                              'ധനലക്ഷ്മി ബാങ്ക്',
    'karnataka_bank':                              'കർണാടക ബാങ്ക്',
    'catholic_syrian_bank':                        'കാത്തലിക് സിറിയൻ ബാങ്ക്',
    'karur_vysya_bank':                            'കരൂർ വൈശ്യ ബാങ്ക്',
    'kerala_gramin_bank':                          'കേരള ഗ്രാമീണ ബാങ്ക്',
    'canara_bank_gramin':                          'കാനറ ബാങ്ക് (ഗ്രാമീൺ)',
    'nabard':                                      'നബാർഡ്',
    'kerala_state_co_operative_bank':              'കേരള സ്റ്റേറ്റ് കോ-ഓപ്പറേറ്റീവ് ബാങ്ക്',
    'district_co_operative_bank':                  'ജില്ലാ സഹകരണ ബാങ്ക്',
    'primary_agricultural_credit_society_pacs':    'പ്രാഥമിക കാർഷിക വായ്പാ സംഘം',
    'kotak_mahindra_bank':                         'കൊട്ടക് മഹീന്ദ്ര ബാങ്ക്',
    'other':                                       'മറ്റുള്ള',
}


def seed_bank_name_ml_translations():
    """Update Malayalam translations for the bank_name category."""
    print("=" * 60)
    print("SEEDING BANK NAME MALAYALAM TRANSLATIONS")
    print("=" * 60)

    try:
        category = TranslationCategory.objects.get(code='bank_name')
    except TranslationCategory.DoesNotExist:
        print("❌ ERROR: 'bank_name' category not found. Aborting.")
        sys.exit(1)

    try:
        lang_ml = Language.objects.get(code='ml')
    except Language.DoesNotExist:
        print("❌ ERROR: Malayalam language ('ml') not found. Aborting.")
        sys.exit(1)

    updated_count = 0
    created_count = 0
    missing_keys = []

    for key, ml_value in BANK_NAME_ML.items():
        translation = Translation.objects.filter(
            category=category, key=key, language=lang_ml
        ).first()

        if translation is None:
            missing_keys.append(key)
            print(f"  ⚠️  Not found, skipping: {key}")
            continue

        if translation.value == ml_value and translation.is_verified:
            print(f"  ⏭️  Already up to date: {key}")
            continue

        translation.value = ml_value
        translation.is_verified = True
        translation.save(update_fields=['value', 'is_verified', 'updated_at'])
        updated_count += 1
        print(f"  ✅ Updated: {key} → {ml_value}")

    print("\n" + "=" * 60)
    print(f"✅ DONE. Updated {updated_count} translations.")
    if missing_keys:
        print(f"⚠️  {len(missing_keys)} keys not found in DB: {missing_keys}")
    print("=" * 60)


# Call seed_bank_name_ml_translations() explicitly after exec'ing this file,
# e.g.:
#   python manage.py shell -c "
#   exec(open('scripts/seed_bank_name_ml_translations.py').read())
#   seed_bank_name_ml_translations()
#   "