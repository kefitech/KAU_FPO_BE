"""
Seed translations for the Government Portal pages.
Usage: python manage.py shell < scripts/seed_government_translations.py
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.database.models import Language, TranslationCategory, Translation

ui_category = TranslationCategory.objects.get(code='ui')
en = Language.objects.get(code='en')
ml = Language.objects.get(code='ml')


def seed(key, en_value, ml_value):
    for lang, value in [(en, en_value), (ml, ml_value)]:
        obj, created = Translation.objects.get_or_create(
            category=ui_category, key=key, language=lang,
            defaults={'value': value},
        )
        marker = 'Created' if created else 'Exists'
        print(f'{marker} {lang.code}  {key}')


print('=' * 60)
print('SEEDING GOVERNMENT DASHBOARD TRANSLATIONS')
print('=' * 60)

seed('government_dashboard.page_title', 'Government Portal', 'സര്‍ക്കാര്‍ പോര്‍ട്ടല്‍')
seed('government_dashboard.subtitle_state', 'Monitor FPO activities across Kerala', 'കേരളത്തിലുടനീളമുള്ള FPO പ്രവര്‍ത്തനങ്ങള്‍ നിരീക്ഷിക്കുക')
seed('government_dashboard.subtitle_district', 'Monitor FPO activities in your district', 'നിങ്ങളുടെ ജില്ലയിലെ FPO പ്രവര്‍ത്തനങ്ങള്‍ നിരീക്ഷിക്കുക')
seed('government_dashboard.stat_registered_fpos', 'Registered FPOs', 'രജിസ്റ്റര്‍ ചെയ്ത FPO-കള്‍')
seed('government_dashboard.stat_registered_desc_state', 'Across {{count}} districts', '{{count}} ജില്ലകളിലായി')
seed('government_dashboard.stat_registered_desc_district', 'In your district', 'നിങ്ങളുടെ ജില്ലയില്‍')
seed('government_dashboard.stat_status_categories', 'Status Categories', 'സ്റ്റാറ്റസ് വിഭാഗങ്ങള്‍')
seed('government_dashboard.stat_status_categories_desc', 'Distinct FPO statuses', 'വ്യത്യസ്ത FPO സ്റ്റാറ്റസുകള്‍')
seed('government_dashboard.stat_top_status', 'Top Status', 'ഏറ്റവും ഉയര്‍ന്ന സ്റ്റാറ്റസ്')
seed('government_dashboard.no_data', 'No data', 'ഡാറ്റ ഇല്ല')

seed('government_dashboard.stat_jurisdiction', 'Jurisdiction', 'അധികാരപരിധി')
seed('government_dashboard.jurisdiction_state', 'State', 'സംസ്ഥാനം')
seed('government_dashboard.jurisdiction_district', 'District', 'ജില്ല')
seed('government_dashboard.stat_jurisdiction_desc_state', 'All Kerala districts', 'കേരളത്തിലെ എല്ലാ ജില്ലകളും')
seed('government_dashboard.stat_jurisdiction_desc_district', 'Single district view', 'ഒരു ജില്ലാ കാഴ്ച')
seed('government_dashboard.card_district_dist_title', 'District-wise FPO Distribution', 'ജില്ല തിരിച്ചുള്ള FPO വിതരണം')
seed('government_dashboard.card_district_dist_desc', 'FPO count by district', 'ജില്ല തിരിച്ചുള്ള FPO എണ്ണം')
seed('government_dashboard.empty_no_fpos_view', 'No FPOs in view yet.', 'ഇതുവരെ FPO-കളൊന്നും ലഭ്യമല്ല.')
seed('government_dashboard.card_status_breakdown_title', 'Status Breakdown', 'സ്റ്റാറ്റസ് വിശദാംശം')
seed('government_dashboard.card_status_breakdown_desc', 'FPOs by verification status', 'സ്ഥിരീകരണ നിലയനുസരിച്ച് FPO-കള്‍')
seed('government_dashboard.empty_no_data', 'No data yet.', 'ഇതുവരെ ഡാറ്റ ലഭ്യമല്ല.')
seed('government_dashboard.card_fpos_in_view_title', 'FPOs in View', 'കാഴ്ചയിലുള്ള FPO-കള്‍')
seed('government_dashboard.card_fpos_in_view_desc_state', 'Sample across all districts', 'എല്ലാ ജില്ലകളില്‍ നിന്നുമുള്ള സാമ്പിള്‍')
seed('government_dashboard.card_fpos_in_view_desc_district', 'In your assigned district', 'നിങ്ങള്‍ക്ക് നിയോഗിച്ച ജില്ലയില്‍')
seed('government_dashboard.empty_no_fpos_found', 'No FPOs found.', 'FPO-കളൊന്നും കണ്ടെത്തിയില്ല.')

print('=' * 60)
print('DONE')
print('=' * 60)

print('=' * 60)
print('SEEDING ADMIN GOVERNMENT TABLE TRANSLATIONS')
print('=' * 60)

seed('government_table.page_title', 'Government Officials', 'സര്‍ക്കാര്‍ ഉദ്യോഗസ്ഥര്‍')
seed('government_table.page_description', 'Manage government official accounts and their jurisdiction', 'സര്‍ക്കാര്‍ ഉദ്യോഗസ്ഥരുടെ അക്കൗണ്ടുകളും അധികാരപരിധിയും നിയന്ത്രിക്കുക')
seed('government_table.add_button', 'Add Official', 'ഉദ്യോഗസ്ഥനെ ചേര്‍ക്കുക')
seed('government_table.view_title', 'Official Details', 'ഉദ്യോഗസ്ഥ വിശദാംശങ്ങള്‍')
seed('government_table.col_name', 'Name', 'പേര്')
seed('government_table.col_email', 'Email', 'ഇമെയില്‍')
seed('government_table.col_phone', 'Phone', 'ഫോണ്‍')
seed('government_table.col_designation', 'Designation', 'പദവി')
seed('government_table.col_department', 'Department', 'വകുപ്പ്')
seed('government_table.col_status', 'Status', 'സ്റ്റാറ്റസ്')
seed('government_table.col_date_joined', 'Date Joined', 'ചേര്‍ന്ന തീയതി')
seed('government_table.col_jurisdiction', 'Jurisdiction', 'അധികാരപരിധി')
seed('government_table.col_joined', 'Joined', 'ചേര്‍ന്നു')
seed('government_table.pending_approvals_button', 'Pending Approvals', 'അംഗീകാരത്തിനായി കാത്തിരിക്കുന്നവ')

print('=' * 60)
print('DONE')
print('=' * 60)
