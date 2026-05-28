"""
Seed Translation Data from messages.py
======================================

Migrates existing hardcoded bilingual messages to database.

Usage:
    python manage.py shell < scripts/seed_translations.py

    Or from Django shell:
    >>> exec(open('scripts/seed_translations.py').read())

Author: Athul Gopan (Kefi Tech Solutions)
Created: 28-04-2026
"""

import sys
import os
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.database.models import Language, TranslationCategory, Translation
from apps.core.utils.messages import (
    AuthMessages,
    FPOMessages,
    ValidationMessages,
    CommonMessages,
    RoleMessages,
)


def create_languages():
    """Create initial languages"""
    print("Creating languages...")

    languages = [
        {
            'code': 'en',
            'name': 'English',
            'native_name': 'English',
            'is_default': True,
            'is_active': True,
            'display_order': 1,
            'locale': 'en_IN',
        },
        {
            'code': 'ml',
            'name': 'Malayalam',
            'native_name': 'മലയാളം',
            'is_default': False,
            'is_active': True,
            'display_order': 2,
            'locale': 'ml_IN',
        },
    ]

    for lang_data in languages:
        lang, created = Language.objects.get_or_create(
            code=lang_data['code'],
            defaults=lang_data
        )
        if created:
            print(f"✅ Created language: {lang.native_name} ({lang.code})")
        else:
            print(f"⏭️  Language already exists: {lang.native_name}")

    return Language.objects.all()


def create_categories():
    """Create translation categories"""
    print("\nCreating translation categories...")

    categories = [
        {
            'code': 'auth',
            'name': 'Authentication & Authorization',
            'description': 'Login, logout, registration, password management',
            'display_order': 1,
        },
        {
            'code': 'fpo',
            'name': 'FPO Management',
            'description': 'FPO registration, approval, documents',
            'display_order': 2,
        },
        {
            'code': 'validation',
            'name': 'Form Validation',
            'description': 'Field validation error messages',
            'display_order': 3,
        },
        {
            'code': 'common',
            'name': 'Common Messages',
            'description': 'Generic success, error, info messages',
            'display_order': 4,
        },
        {
            'code': 'role',
            'name': 'Role Management',
            'description': 'Role creation, update, deletion messages',
            'display_order': 5,
        },
        {
            'code': 'admin',
            'name': 'Admin Management',
            'description': 'Language, translation, category management messages',
            'display_order': 6,
        },
        {
            'code': 'ui',
            'name': 'UI Labels',
            'description': 'Frontend field labels, button text, page titles, placeholders — grouped by screen using dot prefix (login.title, fpo_form.name_label)',
            'display_order': 7,
        },
        {
            'code': 'menu',
            'name': 'Menu Labels',
            'description': 'Sidebar navigation menu item labels — used by /api/auth/me/ to return translated menu',
            'display_order': 8,
        },
    ]

    for cat_data in categories:
        cat, created = TranslationCategory.objects.get_or_create(
            code=cat_data['code'],
            defaults=cat_data
        )
        if created:
            print(f"✅ Created category: {cat.name}")
        else:
            print(f"⏭️  Category already exists: {cat.name}")

    return TranslationCategory.objects.all()


def migrate_message_class(category_code: str, message_class, languages):
    """Migrate messages from a message class to database"""
    category = TranslationCategory.objects.get(code=category_code)
    lang_en = languages['en']
    lang_ml = languages['ml']

    count = 0

    # Get all message attributes (uppercase constants)
    for attr_name in dir(message_class):
        if attr_name.isupper():
            message_tuple = getattr(message_class, attr_name)

            if not isinstance(message_tuple, tuple) or len(message_tuple) != 2:
                continue

            # Convert constant name to translation key
            # LOGIN_SUCCESS -> login_success
            key = attr_name.lower()

            # Create English translation
            Translation.objects.get_or_create(
                category=category,
                key=key,
                language=lang_en,
                defaults={
                    'value': message_tuple[0],  # English
                    'context': f'From {message_class.__name__}.{attr_name}',
                    'is_verified': True,
                }
            )

            # Create Malayalam translation
            Translation.objects.get_or_create(
                category=category,
                key=key,
                language=lang_ml,
                defaults={
                    'value': message_tuple[1],  # Malayalam
                    'context': f'From {message_class.__name__}.{attr_name}',
                    'is_verified': True,
                }
            )

            count += 1

    return count


def seed_admin_translations(languages):
    """Seed admin management messages that were hardcoded in views"""
    category = TranslationCategory.objects.get(code='admin')
    lang_en = languages['en']
    lang_ml = languages['ml']

    admin_messages = [
        # Language management
        ('language_created',        'Language added successfully',                  'ഭാഷ വിജയകരമായി ചേർത്തു'),
        ('language_updated',        'Language updated successfully',                'ഭാഷ വിജയകരമായി അപ്ഡേറ്റ് ചെയ്തു'),
        ('language_deleted',        'Language deleted successfully',                'ഭാഷ വിജയകരമായി ഇല്ലാതാക്കി'),
        ('language_activated',      'Language activated successfully',              'ഭാഷ വിജയകരമായി സജീവമാക്കി'),
        ('language_deactivated',    'Language deactivated successfully',            'ഭാഷ വിജയകരമായി നിഷ്ക്രിയമാക്കി'),
        ('language_set_default',    'Language set as default successfully',         'ഭാഷ ഡിഫോൾട്ടായി സജ്ജമാക്കി'),
        ('cannot_delete_default',   'Cannot delete the default language',           'ഡിഫോൾട്ട് ഭാഷ ഇല്ലാതാക്കാൻ കഴിയില്ല'),
        ('cannot_deactivate_default', 'Cannot deactivate the default language',     'ഡിഫോൾട്ട് ഭാഷ നിഷ്ക്രിയമാക്കാൻ കഴിയില്ല'),
        ('cannot_set_inactive_default', 'Cannot set an inactive language as default', 'നിഷ്ക്രിയ ഭാഷ ഡിഫോൾട്ടായി സജ്ജമാക്കാൻ കഴിയില്ല'),
        ('languages_retrieved',     'Languages retrieved successfully',             'ഭാഷകൾ വിജയകരമായി ലഭിച്ചു'),
        # Category management
        ('category_created',        'Category created successfully',                'വിഭാഗം വിജയകരമായി സൃഷ്ടിച്ചു'),
        ('category_updated',        'Category updated successfully',                'വിഭാഗം വിജയകരമായി അപ്ഡേറ്റ് ചെയ്തു'),
        ('category_deleted',        'Category deleted successfully',                'വിഭാഗം വിജയകരമായി ഇല്ലാതാക്കി'),
        ('categories_retrieved',    'Categories retrieved successfully',            'വിഭാഗങ്ങൾ വിജയകരമായി ലഭിച്ചു'),
        # Translation management
        ('translation_created',     'Translation created successfully',             'വിവർത്തനം വിജയകരമായി സൃഷ്ടിച്ചു'),
        ('translation_updated',     'Translation updated successfully',             'വിവർത്തനം വിജയകരമായി അപ്ഡേറ്റ് ചെയ്തു'),
        ('translation_deleted',     'Translation deleted successfully',             'വിവർത്തനം വിജയകരമായി ഇല്ലാതാക്കി'),
        ('translation_verified',    'Translation verified successfully',            'വിവർത്തനം വിജയകരമായി സ്ഥിരീകരിച്ചു'),
        ('translations_retrieved',  'Translations retrieved successfully',          'വിവർത്തനങ്ങൾ വിജയകരമായി ലഭിച്ചു'),
        ('bulk_translations_created', 'Translations created successfully',          'വിവർത്തനങ്ങൾ വിജയകരമായി സൃഷ്ടിച്ചു'),
        # Notification template code management
        ('template_codes_retrieved',   'Template codes retrieved successfully',     'ടെംപ്ലേറ്റ് കോഡുകൾ വിജയകരമായി ലഭിച്ചു'),
        ('template_code_created',      'Template code created successfully',        'ടെംപ്ലേറ്റ് കോഡ് വിജയകരമായി സൃഷ്ടിച്ചു'),
        ('template_code_updated',      'Template code updated successfully',        'ടെംപ്ലേറ്റ് കോഡ് വിജയകരമായി അപ്ഡേറ്റ് ചെയ്തു'),
        ('template_code_deleted',      'Template code deleted successfully',        'ടെംപ്ലേറ്റ് കോഡ് വിജയകരമായി ഇല്ലാതാക്കി'),
        ('template_code_activated',    'Template code activated successfully',      'ടെംപ്ലേറ്റ് കോഡ് വിജയകരമായി സജീവമാക്കി'),
        ('template_code_deactivated',  'Template code deactivated successfully',    'ടെംപ്ലേറ്റ് കോഡ് വിജയകരമായി നിഷ്ക്രിയമാക്കി'),
        # Two-factor authentication
        ('two_factor_required',                 'Two-factor authentication required',           'ടു-ഫാക്ടർ പ്രാമാണീകരണം ആവശ്യമാണ്'),
        ('two_factor_setup_initiated',          'Scan the QR code with Google Authenticator',  'Google Authenticator ഉപയോഗിച്ച് QR കോഡ് സ്കാൻ ചെയ്യുക'),
        ('two_factor_enabled',                  'Two-factor authentication enabled successfully', 'ടു-ഫാക്ടർ പ്രാമാണീകരണം വിജയകരമായി പ്രവർത്തനക്ഷമമാക്കി'),
        ('two_factor_disabled',                 'Two-factor authentication disabled',           'ടു-ഫാക്ടർ പ്രാമാണീകരണം നിഷ്ക്രിയമാക്കി'),
        ('two_factor_already_enabled',          'Two-factor authentication is already enabled', 'ടു-ഫാക്ടർ പ്രാമാണീകരണം ഇതിനകം പ്രവർത്തനക്ഷമമാണ്'),
        ('two_factor_not_enabled',              'Two-factor authentication is not enabled',     'ടു-ഫാക്ടർ പ്രാമാണീകരണം പ്രവർത്തനക്ഷമമല്ല'),
        ('two_factor_not_initiated',            'Please initiate 2FA setup first',              'ആദ്യം 2FA സജ്ജീകരണം ആരംഭിക്കുക'),
        ('two_factor_invalid_code',             'Invalid or expired code',                      'അസാധുവായ അല്ലെങ്കിൽ കാലഹരണപ്പെട്ട കോഡ്'),
        ('two_factor_invalid_backup_code',      'Invalid backup code',                          'അസാധുവായ ബാക്കപ്പ് കോഡ്'),
        ('two_factor_code_required',            'Code is required',                             'കോഡ് ആവശ്യമാണ്'),
        ('two_factor_admin_only',               'Two-factor authentication is for admin accounts only', 'ടു-ഫാക്ടർ പ്രാമാണീകരണം അഡ്മിൻ അക്കൗണ്ടുകൾക്ക് മാത്രമാണ്'),
        ('two_factor_status_retrieved',         'Two-factor status retrieved successfully',     'ടു-ഫാക്ടർ സ്ഥിതി വിജയകരമായി ലഭിച്ചു'),
        ('two_factor_backup_codes_regenerated', 'Backup codes regenerated successfully',        'ബാക്കപ്പ് കോഡുകൾ വിജയകരമായി പുനർജനിച്ചു'),
        # Sub-admin management
        ('sub_admins_retrieved',            'Sub-admins retrieved successfully',            'സബ്-അഡ്മിൻമാർ വിജയകരമായി ലഭിച്ചു'),
        ('sub_admin_retrieved',             'Sub-admin retrieved successfully',             'സബ്-അഡ്മിൻ വിജയകരമായി ലഭിച്ചു'),
        ('sub_admin_created',               'Sub-admin created successfully',               'സബ്-അഡ്മിൻ വിജയകരമായി സൃഷ്ടിച്ചു'),
        ('sub_admin_updated',               'Sub-admin updated successfully',               'സബ്-അഡ്മിൻ വിജയകരമായി അപ്ഡേറ്റ് ചെയ്തു'),
        ('sub_admin_deleted',               'Sub-admin deleted successfully',               'സബ്-അഡ്മിൻ വിജയകരമായി ഇല്ലാതാക്കി'),
        ('sub_admin_activated',             'Sub-admin activated successfully',             'സബ്-അഡ്മിൻ വിജയകരമായി സജീവമാക്കി'),
        ('sub_admin_deactivated',           'Sub-admin deactivated successfully',           'സബ്-അഡ്മിൻ വിജയകരമായി നിഷ്ക്രിയമാക്കി'),
        ('sub_admin_permissions_updated',   'Sub-admin permissions updated successfully',   'സബ്-അഡ്മിൻ അനുമതികൾ വിജയകരമായി അപ്ഡേറ്റ് ചെയ്തു'),
        ('sub_admin_permissions_retrieved', 'Sub-admin permissions retrieved successfully', 'സബ്-അഡ്മിൻ അനുമതികൾ വിജയകരമായി ലഭിച്ചു'),
        # Menu item management
        ('menu_items_retrieved',       'Menu items retrieved successfully',         'മെനു ഇനങ്ങൾ വിജയകരമായി ലഭിച്ചു'),
        ('menu_item_created',          'Menu item created successfully',            'മെനു ഇനം വിജയകരമായി സൃഷ്ടിച്ചു'),
        ('menu_item_updated',          'Menu item updated successfully',            'മെനു ഇനം വിജയകരമായി അപ്ഡേറ്റ് ചെയ്തു'),
        ('menu_item_deleted',          'Menu item deleted successfully',            'മെനു ഇനം വിജയകരമായി ഇല്ലാതാക്കി'),
        ('menu_item_activated',        'Menu item activated successfully',          'മെനു ഇനം വിജയകരമായി സജീവമാക്കി'),
        ('menu_item_deactivated',      'Menu item deactivated successfully',        'മെനു ഇനം വിജയകരമായി നിഷ്ക്രിയമാക്കി'),
        # Password reset
        ('password_reset_sent',                'If the account exists, you will receive a reset link or OTP shortly', 'അക്കൗണ്ട് നിലവിലുണ്ടെങ്കിൽ, ഉടൻ ഒരു റീസെറ്റ് ലിങ്ക് അല്ലെങ്കിൽ OTP ലഭിക്കും'),
        ('otp_invalid_or_expired',             'Invalid or expired OTP. Please request a new one',                   'അസാധുവായ അല്ലെങ്കിൽ കാലഹരണപ്പെട്ട OTP. പുതിയത് അഭ്യർത്ഥിക്കുക'),
        ('otp_verified',                       'OTP verified successfully',                                           'OTP വിജയകരമായി സ്ഥിരീകരിച്ചു'),
        ('reset_token_invalid_or_expired',     'Reset link has expired or is invalid. Please request a new one',     'റീസെറ്റ് ലിങ്ക് കാലഹരണപ്പെട്ടു അല്ലെങ്കിൽ അസാധുവാണ്. പുതിയത് അഭ്യർത്ഥിക്കുക'),
        ('password_reset_success',             'Password reset successfully. Please log in with your new password',  'പാസ്‌വേഡ് വിജയകരമായി റീസെറ്റ് ചെയ്തു. പുതിയ പാസ്‌വേഡ് ഉപയോഗിച്ച് ലോഗിൻ ചെയ്യുക'),
        ('user_not_found',                     'User not found',                                                      'ഉപയോക്താവ് കണ്ടെത്തിയില്ല'),
        # Channel settings management
        ('channel_settings_retrieved', 'Channel settings retrieved successfully',   'ചാനൽ ക്രമീകരണങ്ങൾ വിജയകരമായി ലഭിച്ചു'),
        ('channel_settings_created',   'Channel setting created successfully',      'ചാനൽ ക്രമീകരണം വിജയകരമായി സൃഷ്ടിച്ചു'),
        ('channel_settings_updated',   'Channel setting updated successfully',      'ചാനൽ ക്രമീകരണം വിജയകരമായി അപ്ഡേറ്റ് ചെയ്തു'),
        ('channel_settings_deleted',   'Channel setting deleted successfully',      'ചാനൽ ക്രമീകരണം വിജയകരമായി ഇല്ലാതാക്കി'),
        ('channel_activated',          'Channel activated successfully',            'ചാനൽ വിജയകരമായി സജീവമാക്കി'),
        ('channel_deactivated',        'Channel deactivated successfully',          'ചാനൽ വിജയകരമായി നിഷ്ക്രിയമാക്കി'),
        # Notification template content management
        ('templates_retrieved',        'Templates retrieved successfully',          'ടെംപ്ലേറ്റുകൾ വിജയകരമായി ലഭിച്ചു'),
        ('template_created',           'Template created successfully',             'ടെംപ്ലേറ്റ് വിജയകരമായി സൃഷ്ടിച്ചു'),
        ('template_updated',           'Template updated successfully',             'ടെംപ്ലേറ്റ് വിജയകരമായി അപ്ഡേറ്റ് ചെയ്തു'),
        ('template_deleted',           'Template deleted successfully',             'ടെംപ്ലേറ്റ് വിജയകരമായി ഇല്ലാതാക്കി'),
        ('template_activated',         'Template activated successfully',           'ടെംപ്ലേറ്റ് വിജയകരമായി സജീവമാക്കി'),
        ('template_deactivated',       'Template deactivated successfully',         'ടെംപ്ലേറ്റ് വിജയകരമായി നിഷ്ക്രിയമാക്കി'),
        ('template_rendered',          'Template rendered successfully',            'ടെംപ്ലേറ്റ് വിജയകരമായി റെൻഡർ ചെയ്തു'),
        # FPO member role management
        ('fpo_roles_retrieved',        'FPO member roles retrieved successfully',    'FPO അംഗ റോളുകൾ വിജയകരമായി ലഭിച്ചു'),
        ('fpo_role_created',           'FPO member role created successfully',       'FPO അംഗ റോൾ വിജയകരമായി സൃഷ്ടിച്ചു'),
        ('fpo_role_updated',           'FPO member role updated successfully',       'FPO അംഗ റോൾ വിജയകരമായി അപ്ഡേറ്റ് ചെയ്തു'),
        ('fpo_role_deleted',           'FPO member role deleted successfully',       'FPO അംഗ റോൾ വിജയകരമായി ഇല്ലാതാക്കി'),
        ('fpo_role_activated',         'FPO member role activated successfully',     'FPO അംഗ റോൾ വിജയകരമായി സജീവമാക്കി'),
        ('fpo_role_deactivated',       'FPO member role deactivated successfully',   'FPO അംഗ റോൾ വിജയകരമായി നിഷ്ക്രിയമാക്കി'),
        ('fpo_role_has_members',       'Cannot delete role assigned to members',     'അംഗങ്ങൾക്ക് നൽകിയ റോൾ ഇല്ലാതാക്കാൻ കഴിയില്ല'),
        # FPO action management
        ('fpo_actions_retrieved',      'FPO actions retrieved successfully',         'FPO ആക്ഷനുകൾ വിജയകരമായി ലഭിച്ചു'),
        ('fpo_action_created',         'FPO action created successfully',            'FPO ആക്ഷൻ വിജയകരമായി സൃഷ്ടിച്ചു'),
        ('fpo_action_updated',         'FPO action updated successfully',            'FPO ആക്ഷൻ വിജയകരമായി അപ്ഡേറ്റ് ചെയ്തു'),
        ('fpo_action_deleted',         'FPO action deleted successfully',            'FPO ആക്ഷൻ വിജയകരമായി ഇല്ലാതാക്കി'),
        ('fpo_action_activated',       'FPO action activated successfully',          'FPO ആക്ഷൻ വിജയകരമായി സജീവമാക്കി'),
        ('fpo_action_deactivated',     'FPO action deactivated successfully',        'FPO ആക്ഷൻ വിജയകരമായി നിഷ്ക്രിയമാക്കി'),
        ('fpo_action_has_permissions', 'Cannot delete action assigned to permissions', 'അനുമതികൾക്ക് നൽകിയ ആക്ഷൻ ഇല്ലാതാക്കാൻ കഴിയില്ല'),
        # FPO permission matrix management
        ('fpo_permissions_retrieved',  'FPO permission matrix retrieved successfully', 'FPO അനുമതി മാട്രിക്സ് വിജയകരമായി ലഭിച്ചു'),
        ('fpo_permissions_updated',    'FPO permission matrix updated successfully',   'FPO അനുമതി മാട്രിക്സ് വിജയകരമായി അപ്ഡേറ്റ് ചെയ്തു'),
        # FPO application workflow
        ('fpo_under_review',           'Application marked as Under Review',           'അപേക്ഷ അവലോകനത്തിലേക്ക് മാറ്റി'),
        ('fpo_approved',               'FPO application approved successfully',        'FPO അപേക്ഷ വിജയകരമായി അംഗീകരിച്ചു'),
        ('fpo_rejected',               'FPO application rejected',                     'FPO അപേക്ഷ നിരസിച്ചു'),
        ('fpo_info_requested',         'Additional information requested from FPO',    'FPO-യിൽ നിന്ന് അധിക വിവരം അഭ്യർഥിച്ചു'),
        ('document_verified',          'Document verified successfully',               'രേഖ വിജയകരമായി പരിശോധിച്ചു'),
        ('user_limit_updated',         'Secondary user limit updated successfully',    'ദ്വിതീയ ഉപയോക്തൃ പരിധി വിജയകരമായി അപ്ഡേറ്റ് ചെയ്തു'),
    ]

    count = 0
    for key, en_value, ml_value in admin_messages:
        Translation.objects.get_or_create(
            category=category, key=key, language=lang_en,
            defaults={'value': en_value, 'context': 'Admin management', 'is_verified': True}
        )
        Translation.objects.get_or_create(
            category=category, key=key, language=lang_ml,
            defaults={'value': ml_value, 'context': 'Admin management', 'is_verified': True}
        )
        count += 1

    return count


def seed_ui_translations(languages):
    """
    UI label translations — exact 1:1 match with frontend strings.

    Keys follow screen.element convention.
    Frontend fetches: GET /api/translations/public/?lang=ml&screen=login
    or multiple:      GET /api/translations/public/?lang=ml&screen=login,common

    NOTE: Success toast messages (Language added, Translation created etc.)
    come from the API response directly — already seeded in admin category.
    Only frontend-generated strings (labels, placeholders, failure toasts) are here.
    """
    category = TranslationCategory.objects.get(code='ui')
    lang_en  = languages['en']
    lang_ml  = languages['ml']

    ui_keys = [

        # ── common — shared buttons, badges, actions used across all screens ─
        ('common.save_btn',             'Save',                                     'സേവ് ചെയ്യുക'),
        ('common.cancel_btn',           'Cancel',                                   'റദ്ദാക്കുക'),
        ('common.reset_btn',            'Reset',                                    'റീസെറ്റ് ചെയ്യുക'),
        ('common.delete_btn',           'Delete',                                   'ഇല്ലാതാക്കുക'),
        ('common.deleting',             'Deleting...',                              'ഇല്ലാതാക്കുന്നു...'),
        ('common.edit',                 'Edit',                                     'എഡിറ്റ് ചെയ്യുക'),
        ('common.close_btn',            'Close',                                    'അടയ്ക്കുക'),
        ('common.badge_active',         'Active',                                   'സജീവം'),
        ('common.badge_inactive',       'Inactive',                                 'നിഷ്ക്രിയം'),
        ('common.action_failed',        'Action failed',                            'പ്രവർത്തനം പരാജയപ്പെട്ടു'),
        ('common.delete_failed',        'Failed to delete',                         'ഇല്ലാതാക്കൽ പരാജയപ്പെട്ടു'),

        # ── login — /v1/login ─────────────────────────────────────────────
        ('login.username_label',        'Username',                                 'ഉപയോക്തൃനാമം'),
        ('login.username_placeholder',  'your username',                            'നിങ്ങളുടെ ഉപയോക്തൃനാമം'),
        ('login.password_label',        'Password',                                 'രഹസ്യവാക്ക്'),
        ('login.password_placeholder',  '••••••••',                                 '••••••••'),
        ('login.submit_btn',            'Sign In',                                  'സൈൻ ഇൻ ചെയ്യുക'),

        # ── admin_languages — /admin/languages page ───────────────────────
        ('admin_languages.page_title',          'Languages & Translations',         'ഭാഷകളും വിവർത്തനങ്ങളും'),
        ('admin_languages.page_description',    'Manage platform languages and translation categories', 'പ്ലാറ്റ്ഫോം ഭാഷകളും വിവർത്തന വിഭാഗങ്ങളും നിയന്ത്രിക്കുക'),
        ('admin_languages.tab_languages',       'Languages',                        'ഭാഷകൾ'),
        ('admin_languages.tab_categories',      'Categories',                       'വിഭാഗങ്ങൾ'),
        ('admin_languages.tab_translations',    'Translations',                     'വിവർത്തനങ്ങൾ'),
        ('admin_languages.add_language_btn',    'Add Language',                     'ഭാഷ ചേർക്കുക'),
        ('admin_languages.add_category_btn',    'Add Category',                     'വിഭാഗം ചേർക്കുക'),
        ('admin_languages.export_btn',          'Export',                           'എക്സ്പോർട്ട്'),
        ('admin_languages.import_btn',          'Import',                           'ഇമ്പോർട്ട്'),
        ('admin_languages.add_translation_btn', 'Add Translation',                  'വിവർത്തനം ചേർക്കുക'),

        # ── lang_dialog — Add/Edit Language dialog ────────────────────────
        ('lang_dialog.add_title',               'Add Language',                     'ഭാഷ ചേർക്കുക'),
        ('lang_dialog.edit_title',              'Edit Language',                    'ഭാഷ എഡിറ്റ് ചെയ്യുക'),
        ('lang_dialog.name_label',              'Name',                             'പേര്'),
        ('lang_dialog.code_label',              'Code',                             'കോഡ്'),
        ('lang_dialog.native_name_label',       'Native Name',                      'മാതൃഭാഷാ നാമം'),
        ('lang_dialog.locale_label',            'Locale',                           'ലൊക്കേൽ'),
        ('lang_dialog.display_order_label',     'Display Order',                    'പ്രദർശന ക്രമം'),
        ('lang_dialog.active_label',            'Active',                           'സജീവം'),
        ('lang_dialog.default_label',           'Default',                          'ഡിഫോൾട്ട്'),
        ('lang_dialog.rtl_label',               'RTL',                              'RTL'),
        ('lang_dialog.name_placeholder',        'e.g. Malayalam',                   'ഉദാ. Malayalam'),
        ('lang_dialog.code_placeholder',        'e.g. ml',                          'ഉദാ. ml'),
        ('lang_dialog.native_name_placeholder', 'e.g. മലയാളം',                     'ഉദാ. മലയാളം'),
        ('lang_dialog.locale_placeholder',      'e.g. ml_IN',                       'ഉദാ. ml_IN'),
        ('lang_dialog.toast_add_failed',        'Failed to add language',           'ഭാഷ ചേർക്കൽ പരാജയപ്പെട്ടു'),

        # ── lang_table — Language list columns & actions ──────────────────
        ('lang_table.col_name',                 'Name',                             'പേര്'),
        ('lang_table.col_code',                 'Code',                             'കോഡ്'),
        ('lang_table.col_status',               'Status',                           'സ്ഥിതി'),
        ('lang_table.col_default',              'Default',                          'ഡിഫോൾട്ട്'),
        ('lang_table.action_set_default',       'Set as Default',                   'ഡിഫോൾട്ടായി സജ്ജമാക്കുക'),
        ('lang_table.action_activate',          'Activate',                         'സജീവമാക്കുക'),
        ('lang_table.action_deactivate',        'Deactivate',                       'നിഷ്ക്രിയമാക്കുക'),
        ('lang_table.badge_default',            'Default',                          'ഡിഫോൾട്ട്'),

        # ── cat_dialog — Add/Edit Category dialog ─────────────────────────
        ('cat_dialog.add_title',                'Add Category',                     'വിഭാഗം ചേർക്കുക'),
        ('cat_dialog.edit_title',               'Edit Category',                    'വിഭാഗം എഡിറ്റ് ചെയ്യുക'),
        ('cat_dialog.name_label',               'Name',                             'പേര്'),
        ('cat_dialog.code_label',               'Code',                             'കോഡ്'),
        ('cat_dialog.description_label',        'Description',                      'വിവരണം'),
        ('cat_dialog.display_order_label',      'Display Order',                    'പ്രദർശന ക്രമം'),
        ('cat_dialog.name_placeholder',         'e.g. Authentication',              'ഉദാ. Authentication'),
        ('cat_dialog.code_placeholder',         'e.g. auth',                        'ഉദാ. auth'),
        ('cat_dialog.description_placeholder',  'Describe what translations belong here', 'ഇവിടെ ഏതൊക്കെ വിവർത്തനങ്ങൾ ഉൾപ്പെടുന്നു എന്ന് വിവരിക്കുക'),

        # ── cat_table — Category list columns & actions ───────────────────
        ('cat_table.col_name',                  'Name',                             'പേര്'),
        ('cat_table.col_code',                  'Code',                             'കോഡ്'),
        ('cat_table.col_description',           'Description',                      'വിവരണം'),
        ('cat_table.col_translations',          'Translations',                     'വിവർത്തനങ്ങൾ'),
        ('cat_table.col_order',                 'Order',                            'ക്രമം'),

        # ── trans_dialog — Add/Edit Translation dialog ────────────────────
        ('trans_dialog.add_title',              'Add Translation',                  'വിവർത്തനം ചേർക്കുക'),
        ('trans_dialog.edit_title',             'Edit Translation',                 'വിവർത്തനം എഡിറ്റ് ചെയ്യുക'),
        ('trans_dialog.language_label',         'Language',                         'ഭാഷ'),
        ('trans_dialog.category_label',         'Category',                         'വിഭാഗം'),
        ('trans_dialog.key_label',              'Key',                              'കീ'),
        ('trans_dialog.value_label',            'Value',                            'മൂല്യം'),
        ('trans_dialog.context_label',          'Context (optional)',                'സന്ദർഭം (ഐച്ഛികം)'),
        ('trans_dialog.key_placeholder',        'e.g. login_success',               'ഉദാ. login_success'),
        ('trans_dialog.value_placeholder',      'Translated text',                  'വിവർത്തനം ചെയ്ത ടെക്സ്റ്റ്'),
        ('trans_dialog.context_placeholder',    'e.g. Login page success message',  'ഉദാ. Login page success message'),
        ('trans_dialog.toast_verify_failed',    'Failed to verify',                 'സ്ഥിരീകരണം പരാജയപ്പെട്ടു'),

        # ── trans_table — Translation list columns & actions ──────────────
        ('trans_table.col_key',                 'Key',                              'കീ'),
        ('trans_table.col_language',            'Language',                         'ഭാഷ'),
        ('trans_table.col_category',            'Category',                         'വിഭാഗം'),
        ('trans_table.col_value',               'Value',                            'മൂല്യം'),
        ('trans_table.col_status',              'Status',                           'സ്ഥിതി'),
        ('trans_table.action_verify',           'Mark as Verified',                 'സ്ഥിരീകരിച്ചതായി അടയാളപ്പെടുത്തുക'),
        ('trans_table.badge_verified',          'Verified',                         'സ്ഥിരീകരിച്ചത്'),
        ('trans_table.badge_unverified',        'Unverified',                       'സ്ഥിരീകരിക്കാത്തത്'),

        # ── export_dialog — Export Translation Template dialog ────────────
        ('export_dialog.title',                 'Export Translation Template',       'വിവർത്തന ടെംപ്ലേറ്റ് എക്സ്പോർട്ട് ചെയ്യുക'),
        ('export_dialog.description',           'Downloads only keys that are missing translations for the selected language', 'തിരഞ്ഞെടുത്ത ഭാഷയ്ക്ക് വിവർത്തനം ഇല്ലാത്ത കീകൾ മാത്രം ഡൗൺലോഡ് ചെയ്യുന്നു'),
        ('export_dialog.language_label',        'Language',                         'ഭാഷ'),
        ('export_dialog.category_label',        'Category',                         'വിഭാഗം'),
        ('export_dialog.format_label',          'File Format',                      'ഫയൽ ഫോർമാറ്റ്'),
        ('export_dialog.all_categories',        'All categories',                   'എല്ലാ വിഭാഗങ്ങളും'),
        ('export_dialog.format_xlsx',           'Excel (.xlsx)',                     'Excel (.xlsx)'),
        ('export_dialog.format_csv',            'CSV (.csv)',                        'CSV (.csv)'),
        ('export_dialog.export_btn',            'Export',                           'എക്സ്പോർട്ട്'),
        ('export_dialog.downloading',           'Downloading...',                   'ഡൗൺലോഡ് ചെയ്യുന്നു...'),
        ('export_dialog.toast_select_language', 'Please select a language',         'ഒരു ഭാഷ തിരഞ്ഞെടുക്കുക'),
        ('export_dialog.toast_failed',          'Failed to export translations',    'വിവർത്തനങ്ങൾ എക്സ്പോർട്ട് ചെയ്യൽ പരാജയപ്പെട്ടു'),

        # ── import_dialog — Import Translations dialog ────────────────────
        ('import_dialog.title',                 'Import Translations',               'വിവർത്തനങ്ങൾ ഇമ്പോർട്ട് ചെയ്യുക'),
        ('import_dialog.language_label',        'Language',                         'ഭാഷ'),
        ('import_dialog.category_label',        'Category',                         'വിഭാഗം'),
        ('import_dialog.download_template_btn', 'Download Template',                'ടെംപ്ലേറ്റ് ഡൗൺലോഡ് ചെയ്യുക'),
        ('import_dialog.import_btn',            'Import',                           'ഇമ്പോർട്ട്'),
        ('import_dialog.toast_select_language', 'Please select a language',         'ഒരു ഭാഷ തിരഞ്ഞെടുക്കുക'),
        ('import_dialog.toast_select_file',     'Please select a file to upload',   'അപ്‌ലോഡ് ചെയ്യാൻ ഒരു ഫയൽ തിരഞ്ഞെടുക്കുക'),
        ('import_dialog.toast_invalid_format',  'Only .xlsx or .csv files are allowed', '.xlsx അല്ലെങ്കിൽ .csv ഫയലുകൾ മാത്രം അനുവദനീയം'),
        ('import_dialog.toast_failed',          'Failed to import translations',    'വിവർത്തനങ്ങൾ ഇമ്പോർട്ട് ചെയ്യൽ പരാജയപ്പെട്ടു'),

        # ── admin_notifications — /admin/notifications page ───────────────
        ('admin_notifications.page_title',      'Notifications',                    'അറിയിപ്പുകൾ'),
        ('admin_notifications.page_description','Manage notification template codes and language content', 'നോട്ടിഫിക്കേഷൻ ടെംപ്ലേറ്റ് കോഡുകളും ഭാഷാ ഉള്ളടക്കവും നിയന്ത്രിക്കുക'),
        ('admin_notifications.tab_codes',       'Template Codes',                   'ടെംപ്ലേറ്റ് കോഡുകൾ'),
        ('admin_notifications.tab_templates',   'Templates',                        'ടെംപ്ലേറ്റുകൾ'),
        ('admin_notifications.add_code_btn',         'Add Template Code',                'ടെംപ്ലേറ്റ് കോഡ് ചേർക്കുക'),
        ('admin_notifications.add_template_btn',     'Add Template',                     'ടെംപ്ലേറ്റ് ചേർക്കുക'),
        ('admin_notifications.tab_channel_settings', 'Channel Settings',                 'ചാനൽ ക്രമീകരണങ്ങൾ'),
        ('admin_notifications.add_channel_btn',      'Add Channel',                      'ചാനൽ ചേർക്കുക'),

        # ── tmpl_code_dialog — Add/Edit Template Code dialog ─────────────
        ('tmpl_code_dialog.add_title',          'Add Template Code',                'ടെംപ്ലേറ്റ് കോഡ് ചേർക്കുക'),
        ('tmpl_code_dialog.edit_title',         'Edit Template Code',               'ടെംപ്ലേറ്റ് കോഡ് എഡിറ്റ് ചെയ്യുക'),
        ('tmpl_code_dialog.name_label',         'Name',                             'പേര്'),
        ('tmpl_code_dialog.code_label',         'Code',                             'കോഡ്'),
        ('tmpl_code_dialog.channel_label',      'Channel',                          'ചാനൽ'),
        ('tmpl_code_dialog.variables_label',    'Variables',                        'വേരിയബിളുകൾ'),
        ('tmpl_code_dialog.description_label',  'Description',                      'വിവരണം'),
        ('tmpl_code_dialog.active_label',       'Active',                           'സജീവം'),
        ('tmpl_code_dialog.name_placeholder',   'e.g. FPO Application Approved',    'ഉദാ. FPO Application Approved'),
        ('tmpl_code_dialog.code_placeholder',   'e.g. fpo_approved',                'ഉദാ. fpo_approved'),
        ('tmpl_code_dialog.variables_placeholder','e.g. user_name, fpo_name, application_id', 'ഉദാ. user_name, fpo_name, application_id'),
        ('tmpl_code_dialog.description_placeholder','When is this notification sent?', 'ഈ അറിയിപ്പ് എപ്പോൾ അയക്കുന്നു?'),
        ('tmpl_code_dialog.variables_helper',   'Comma-separated placeholder names','കോമയാൽ വേർതിരിച്ച പ്ലേസ്‌ഹോൾഡർ നാമങ്ങൾ'),
        ('tmpl_code_dialog.channel_email',      'Email',                            'ഇ-മെയിൽ'),
        ('tmpl_code_dialog.channel_sms',        'SMS',                              'SMS'),
        ('tmpl_code_dialog.channel_in_app',     'In-App Notification',              'ആപ്പ് അറിയിപ്പ്'),
        ('tmpl_code_dialog.channel_push',       'Push Notification',                'പുഷ് അറിയിപ്പ്'),
        ('tmpl_code_dialog.toast_create_failed','Failed to create template code',   'ടെംപ്ലേറ്റ് കോഡ് സൃഷ്ടിക്കൽ പരാജയപ്പെട്ടു'),

        # ── tmpl_code_table — Template Code list columns & actions ─────────
        ('tmpl_code_table.col_name',            'Name',                             'പേര്'),
        ('tmpl_code_table.col_channel',         'Channel',                          'ചാനൽ'),
        ('tmpl_code_table.col_variables',       'Variables',                        'വേരിയബിളുകൾ'),
        ('tmpl_code_table.col_templates',       'Templates',                        'ടെംപ്ലേറ്റുകൾ'),
        ('tmpl_code_table.col_missing',         'Missing',                          'ഇല്ലാത്തത്'),
        ('tmpl_code_table.col_status',          'Status',                           'സ്ഥിതി'),
        ('tmpl_code_table.action_toggle',       'Activate / Deactivate',            'സജീവമാക്കുക / നിഷ്ക്രിയമാക്കുക'),

        # ── tmpl_dialog — Add/Edit Template dialog ────────────────────────
        ('tmpl_dialog.add_title',               'Add Template',                     'ടെംപ്ലേറ്റ് ചേർക്കുക'),
        ('tmpl_dialog.edit_title',              'Edit Template',                    'ടെംപ്ലേറ്റ് എഡിറ്റ് ചെയ്യുക'),
        ('tmpl_dialog.code_label',              'Template Code',                    'ടെംപ്ലേറ്റ് കോഡ്'),
        ('tmpl_dialog.language_label',          'Language',                         'ഭാഷ'),
        ('tmpl_dialog.subject_label',           'Subject',                          'വിഷയം'),
        ('tmpl_dialog.body_label',              'Body',                             'ഉള്ളടക്കം'),
        ('tmpl_dialog.active_label',            'Active',                           'സജീവം'),
        ('tmpl_dialog.code_placeholder',        'Select template code',             'ടെംപ്ലേറ്റ് കോഡ് തിരഞ്ഞെടുക്കുക'),
        ('tmpl_dialog.language_placeholder',    'Select language',                  'ഭാഷ തിരഞ്ഞെടുക്കുക'),
        ('tmpl_dialog.subject_placeholder',     'e.g. Your FPO application has been approved', 'ഉദാ. നിങ്ങളുടെ FPO അപേക്ഷ അംഗീകരിച്ചു'),
        ('tmpl_dialog.body_placeholder',        'Write the notification body here. Use {variable_name} for placeholders.', 'അറിയിപ്പ് ഉള്ളടക്കം ഇവിടെ എഴുതുക. {variable_name} ഉപയോഗിക്കുക.'),
        ('tmpl_dialog.toast_create_failed',     'Failed to create template',        'ടെംപ്ലേറ്റ് സൃഷ്ടിക്കൽ പരാജയപ്പെട്ടു'),

        # ── tmpl_table — Template list columns & actions ──────────────────
        ('tmpl_table.col_code',                 'Template Code',                    'ടെംപ്ലേറ്റ് കോഡ്'),
        ('tmpl_table.col_channel',              'Channel',                          'ചാനൽ'),
        ('tmpl_table.col_language',             'Language',                         'ഭാഷ'),
        ('tmpl_table.col_subject',              'Subject',                          'വിഷയം'),
        ('tmpl_table.col_status',               'Status',                           'സ്ഥിതി'),
        ('tmpl_table.action_test_render',       'Test Render',                      'ടെസ്റ്റ് റെൻഡർ'),
        ('tmpl_table.action_toggle',            'Activate / Deactivate',            'സജീവമാക്കുക / നിഷ്ക്രിയമാക്കുക'),

        # ── test_render_dialog — Test Render dialog ───────────────────────
        ('test_render_dialog.title',            'Test Render',                      'ടെസ്റ്റ് റെൻഡർ'),
        ('test_render_dialog.description',      'Enter sample values',              'സാമ്പിൾ മൂല്യങ്ങൾ നൽകുക'),
        ('test_render_dialog.rendered_output',  'Rendered Output',                  'റെൻഡർ ചെയ്ത ഔട്ട്പുട്ട്'),
        ('test_render_dialog.subject_label',    'Subject',                          'വിഷയം'),
        ('test_render_dialog.body_label',       'Body',                             'ഉള്ളടക്കം'),
        ('test_render_dialog.variable_placeholder', 'Sample value for {variable}',  '{variable}-നുള്ള സാമ്പിൾ മൂല്യം'),
        ('test_render_dialog.no_variables',     'This template has no variables.',  'ഈ ടെംപ്ലേറ്റിന് വേരിയബിളുകൾ ഇല്ല.'),
        ('test_render_dialog.render_btn',       'Render',                           'റെൻഡർ ചെയ്യുക'),
        ('test_render_dialog.rendering',        'Rendering...',                     'റെൻഡർ ചെയ്യുന്നു...'),
        ('test_render_dialog.toast_failed',     'Failed to render template',        'ടെംപ്ലേറ്റ് റെൻഡർ ചെയ്യൽ പരാജയപ്പെട്ടു'),

        # ── channel_settings_table — Channel Settings list columns ───────
        ('channel_settings_table.col_channel',       'Channel',                          'ചാനൽ'),
        ('channel_settings_table.col_config',        'Configuration',                    'ക്രമീകരണം'),
        ('channel_settings_table.col_status',        'Status',                           'സ്ഥിതി'),
        ('channel_settings_table.col_updated',       'Last Updated',                     'അവസാനം അപ്ഡേറ്റ് ചെയ്തത്'),

        # ── channel_settings_dialog — Add/Edit Channel Setting dialog ─────
        ('channel_settings_dialog.add_title',              'Add Channel Setting',              'ചാനൽ ക്രമീകരണം ചേർക്കുക'),
        ('channel_settings_dialog.edit_title',             'Edit Channel Setting',             'ചാനൽ ക്രമീകരണം എഡിറ്റ് ചെയ്യുക'),
        ('channel_settings_dialog.channel_label',          'Channel',                          'ചാനൽ'),
        ('channel_settings_dialog.active_label',           'Active',                           'സജീവം'),
        ('channel_settings_dialog.section_config',         'Configuration',                    'ക്രമീകരണം'),
        ('channel_settings_dialog.host_label',             'SMTP Host',                        'SMTP ഹോസ്റ്റ്'),
        ('channel_settings_dialog.host_placeholder',       'e.g. smtp.gmail.com',              'ഉദാ. smtp.gmail.com'),
        ('channel_settings_dialog.port_label',             'Port',                             'പോർട്ട്'),
        ('channel_settings_dialog.port_placeholder',       '587',                              '587'),
        ('channel_settings_dialog.username_label',         'Username',                         'യൂസർനെയിം'),
        ('channel_settings_dialog.username_placeholder',   'e.g. noreply@kau.in',              'ഉദാ. noreply@kau.in'),
        ('channel_settings_dialog.password_label',         'Password',                         'പാസ്‌വേഡ്'),
        ('channel_settings_dialog.password_placeholder',   'Enter new password to update',     'അപ്ഡേറ്റ് ചെയ്യാൻ പുതിയ പാസ്‌വേഡ് നൽകുക'),
        ('channel_settings_dialog.from_email_label',       'From Email',                       'അയക്കുന്ന ഇ-മെയിൽ'),
        ('channel_settings_dialog.from_email_placeholder', 'e.g. noreply@kau.in',              'ഉദാ. noreply@kau.in'),
        ('channel_settings_dialog.from_name_label',        'From Name',                        'അയക്കുന്നയാളുടെ പേര്'),
        ('channel_settings_dialog.from_name_placeholder',  'e.g. KAU-FPO Platform',            'ഉദാ. KAU-FPO Platform'),
        ('channel_settings_dialog.use_tls_label',          'Use TLS (STARTTLS on port 587)',   'TLS ഉപയോഗിക്കുക (പോർട്ട് 587-ൽ STARTTLS)'),
        ('channel_settings_dialog.api_key_label',          'API Key',                          'API കീ'),
        ('channel_settings_dialog.api_key_placeholder',    'Enter new API key to update',      'അപ്ഡേറ്റ് ചെയ്യാൻ പുതിയ API കീ നൽകുക'),
        ('channel_settings_dialog.sender_id_label',        'Sender ID',                        'അയക്കുന്നയാളുടെ ID'),
        ('channel_settings_dialog.sender_id_placeholder',  'e.g. KAUFPO (max 6 chars)',        'ഉദാ. KAUFPO (പരമാവധി 6 അക്ഷരങ്ങൾ)'),
        ('channel_settings_dialog.base_url_label',         'Base URL',                         'ബേസ് URL'),
        ('channel_settings_dialog.base_url_placeholder',   'e.g. https://api.msg91.com/api/v5/', 'ഉദാ. https://api.msg91.com/api/v5/'),
        ('channel_settings_dialog.in_app_note',            'In-app notifications write directly to the database. No configuration required.', 'ആപ്പ് അറിയിപ്പുകൾ നേരിട്ട് ഡാറ്റാബേസിൽ എഴുതുന്നു. ക്രമീകരണം ആവശ്യമില്ല.'),
        ('channel_settings_dialog.toast_create_success',   'Channel setting created successfully', 'ചാനൽ ക്രമീകരണം വിജയകരമായി സൃഷ്ടിച്ചു'),
        ('channel_settings_dialog.toast_update_success',   'Channel setting updated successfully', 'ചാനൽ ക്രമീകരണം വിജയകരമായി അപ്ഡേറ്റ് ചെയ്തു'),
        ('channel_settings_dialog.toast_create_failed',    'Failed to create channel setting',  'ചാനൽ ക്രമീകരണം സൃഷ്ടിക്കൽ പരാജയപ്പെട്ടു'),
        ('channel_settings_dialog.toast_update_failed',    'Failed to update channel setting',  'ചാനൽ ക്രമീകരണം അപ്ഡേറ്റ് ചെയ്യൽ പരാജയപ്പെട്ടു'),

        # ── channel_settings_test_dialog — Send Test Notification dialog ──
        ('channel_settings_test_dialog.title',                    'Send Test Notification',           'ടെസ്റ്റ് അറിയിപ്പ് അയക്കുക'),
        ('channel_settings_test_dialog.description',              'Send a test notification using this channel\'s current configuration.', 'ഈ ചാനലിന്റെ നിലവിലെ ക്രമീകരണം ഉപയോഗിച്ച് ഒരു ടെസ്റ്റ് അറിയിപ്പ് അയക്കുക.'),
        ('channel_settings_test_dialog.recipient_label',          'Recipient',                        'സ്വീകർത്താവ്'),
        ('channel_settings_test_dialog.recipient_placeholder_email', 'e.g. test@example.com',         'ഉദാ. test@example.com'),
        ('channel_settings_test_dialog.recipient_placeholder_sms',  'e.g. +919876543210',             'ഉദാ. +919876543210'),
        ('channel_settings_test_dialog.message_label',            'Message',                          'സന്ദേശം'),
        ('channel_settings_test_dialog.message_placeholder',      'Enter test message...',            'ടെസ്റ്റ് സന്ദേശം നൽകുക...'),
        ('channel_settings_test_dialog.send_btn',                 'Send Test',                        'ടെസ്റ്റ് അയക്കുക'),
        ('channel_settings_test_dialog.sending_btn',              'Sending...',                       'അയക്കുന്നു...'),
        ('channel_settings_test_dialog.toast_success',            'Test notification sent successfully', 'ടെസ്റ്റ് അറിയിപ്പ് വിജയകരമായി അയച്ചു'),
        ('channel_settings_test_dialog.toast_failed',             'Failed to send test notification', 'ടെസ്റ്റ് അറിയിപ്പ് അയക്കൽ പരാജയപ്പെട്ടു'),

        # ── menu_table — Menu CMS list columns & actions ─────────────────
        ('menu_table.page_title',               'Menu Items',                       'മെനു ഇനങ്ങൾ'),
        ('menu_table.add_button',               'Add Menu Item',                    'മെനു ഇനം ചേർക്കുക'),
        ('menu_table.col_label_key',            'Label Key',                        'ലേബൽ കീ'),
        ('menu_table.col_path',                 'Path',                             'പാത്ത്'),
        ('menu_table.col_icon',                 'Icon',                             'ഐക്കൺ'),
        ('menu_table.col_roles',                'Roles',                            'റോളുകൾ'),
        ('menu_table.col_parent',               'Parent',                           'പേരന്റ്'),
        ('menu_table.col_order',                'Order',                            'ക്രമം'),
        ('menu_table.col_status',               'Status',                           'സ്ഥിതി'),
        ('menu_table.col_actions',              'Actions',                          'പ്രവർത്തനങ്ങൾ'),
        ('menu_table.status_active',            'Active',                           'സജീവം'),
        ('menu_table.status_inactive',          'Inactive',                         'നിഷ്ക്രിയം'),
        ('menu_table.action_edit',              'Edit',                             'എഡിറ്റ് ചെയ്യുക'),
        ('menu_table.action_activate',          'Activate',                         'സജീവമാക്കുക'),
        ('menu_table.action_deactivate',        'Deactivate',                       'നിഷ്ക്രിയമാക്കുക'),
        ('menu_table.action_delete',            'Delete',                           'ഇല്ലാതാക്കുക'),
        ('menu_table.no_parent',                'Top Level',                        'ടോപ്പ് ലെവൽ'),

        # ── menu_dialog — Add/Edit/Delete Menu Item dialog ────────────────
        ('menu_dialog.add_title',               'Add Menu Item',                    'മെനു ഇനം ചേർക്കുക'),
        ('menu_dialog.edit_title',              'Edit Menu Item',                   'മെനു ഇനം എഡിറ്റ് ചെയ്യുക'),
        ('menu_dialog.label_key',               'Label Key',                        'ലേബൽ കീ'),
        ('menu_dialog.label_key_placeholder',   'e.g. sidebar.dashboard',           'ഉദാ. sidebar.dashboard'),
        ('menu_dialog.path',                    'Path',                             'പാത്ത്'),
        ('menu_dialog.path_placeholder',        'e.g. /admin/dashboard',            'ഉദാ. /admin/dashboard'),
        ('menu_dialog.icon',                    'Icon',                             'ഐക്കൺ'),
        ('menu_dialog.icon_placeholder',        'e.g. LayoutDashboard',             'ഉദാ. LayoutDashboard'),
        ('menu_dialog.roles',                   'Roles',                            'റോളുകൾ'),
        ('menu_dialog.roles_placeholder',       'Select roles',                     'റോളുകൾ തിരഞ്ഞെടുക്കുക'),
        ('menu_dialog.parent',                  'Parent Item',                      'പേരന്റ് ഇനം'),
        ('menu_dialog.parent_placeholder',      'Select parent (or leave empty for top-level)', 'പേരന്റ് തിരഞ്ഞെടുക്കുക (ടോപ്പ് ലെവലിന് ഒഴിച്ചിടുക)'),
        ('menu_dialog.order',                   'Order',                            'ക്രമം'),
        ('menu_dialog.order_placeholder',       'e.g. 1',                           'ഉദാ. 1'),
        ('menu_dialog.is_active',               'Active',                           'സജീവം'),
        ('menu_dialog.btn_save',                'Save',                             'സേവ് ചെയ്യുക'),
        ('menu_dialog.btn_cancel',              'Cancel',                           'റദ്ദാക്കുക'),
        ('menu_dialog.btn_reset',               'Reset',                            'റീസെറ്റ് ചെയ്യുക'),
        ('menu_dialog.delete_title',            'Delete Menu Item',                 'മെനു ഇനം ഇല്ലാതാക്കുക'),
        ('menu_dialog.delete_description',      'Are you sure you want to delete "{label_key}"? This action cannot be undone.', '"{label_key}" ഇല്ലാതാക്കണമെന്ന് ഉറപ്പാണോ? ഈ പ്രവർത്തനം പഴയപടിയാക്കാൻ കഴിയില്ല.'),
        ('menu_dialog.toast_created',           'Menu item created successfully',   'മെനു ഇനം വിജയകരമായി സൃഷ്ടിച്ചു'),
        ('menu_dialog.toast_updated',           'Menu item updated successfully',   'മെനു ഇനം വിജയകരമായി അപ്ഡേറ്റ് ചെയ്തു'),
        ('menu_dialog.toast_deleted',           'Menu item deleted successfully',   'മെനു ഇനം വിജയകരമായി ഇല്ലാതാക്കി'),
        ('menu_dialog.toast_activated',         'Menu item activated successfully', 'മെനു ഇനം വിജയകരമായി സജീവമാക്കി'),
        ('menu_dialog.toast_deactivated',       'Menu item deactivated successfully', 'മെനു ഇനം വിജയകരമായി നിഷ്ക്രിയമാക്കി'),

        # ── sub_admins_table — Sub-Admins list columns & actions ─────────
        ('sub_admins_table.page_title',         'Sub-Admins',                               'സബ്-അഡ്മിൻ'),
        ('sub_admins_table.page_description',   'Manage sub-admin accounts and their permissions', 'സബ്-അഡ്മിൻ അക്കൗണ്ടുകളും അനുമതികളും നിയന്ത്രിക്കുക'),
        ('sub_admins_table.add_button',         'Add Sub-Admin',                            'സബ്-അഡ്മിൻ ചേർക്കുക'),
        ('sub_admins_table.col_name',           'Name',                                     'പേര്'),
        ('sub_admins_table.col_email',          'Email',                                    'ഇ-മെയിൽ'),
        ('sub_admins_table.col_permissions',    'Permissions',                              'അനുമതികൾ'),
        ('sub_admins_table.col_status',         'Status',                                   'സ്ഥിതി'),
        ('sub_admins_table.col_joined',         'Joined',                                   'ചേർന്ന തീയതി'),
        ('sub_admins_table.status_active',      'Active',                                   'സജീവം'),
        ('sub_admins_table.status_inactive',    'Inactive',                                 'നിഷ്ക്രിയം'),
        ('sub_admins_table.no_permissions',     'None',                                     'ഒന്നുമില്ല'),
        ('sub_admins_table.activate',           'Activate',                                 'സജീവമാക്കുക'),
        ('sub_admins_table.deactivate',         'Deactivate',                               'നിഷ്ക്രിയമാക്കുക'),
        ('sub_admins_table.toast_activated',    'Sub-admin activated',                      'സബ്-അഡ്മിൻ സജീവമാക്കി'),
        ('sub_admins_table.toast_deactivated',  'Sub-admin deactivated',                    'സബ്-അഡ്മിൻ നിഷ്ക്രിയമാക്കി'),
        ('sub_admins_table.toast_deleted',      'Sub-admin deleted',                        'സബ്-അഡ്മിൻ ഇല്ലാതാക്കി'),
        ('sub_admins_table.delete_description', 'Are you sure you want to delete "{name}"? This action cannot be undone.', '"{name}" ഇല്ലാതാക്കണമെന്ന് ഉറപ്പാണോ? ഈ പ്രവർത്തനം പഴയപടിയാക്കാൻ കഴിയില്ല.'),

        # ── sub_admins_dialog — Add/Edit Sub-Admin dialog ─────────────────
        ('sub_admins_dialog.add_title',                     'Add Sub-Admin',                'സബ്-അഡ്മിൻ ചേർക്കുക'),
        ('sub_admins_dialog.edit_title',                    'Edit Sub-Admin',               'സബ്-അഡ്മിൻ എഡിറ്റ് ചെയ്യുക'),
        ('sub_admins_dialog.first_name_label',              'First Name',                   'പേരിന്റെ ആദ്യഭാഗം'),
        ('sub_admins_dialog.last_name_label',               'Last Name',                    'പേരിന്റെ അവസാനഭാഗം'),
        ('sub_admins_dialog.email_label',                   'Email',                        'ഇ-മെയിൽ'),
        ('sub_admins_dialog.password_label',                'Password',                     'പാസ്‌വേഡ്'),
        ('sub_admins_dialog.password_hint',                 '(leave blank to keep current)', '(നിലവിലുള്ളത് നിലനിർത്താൻ ഒഴിച്ചിടുക)'),
        ('sub_admins_dialog.permissions_label',             'Permissions',                  'അനുമതികൾ'),
        ('sub_admins_dialog.permissions_search_placeholder','Search permissions...',        'അനുമതികൾ തിരയുക...'),
        ('sub_admins_dialog.permissions_loading',           'Loading permissions...',       'അനുമതികൾ ലോഡ് ചെയ്യുന്നു...'),
        ('sub_admins_dialog.permissions_no_results',        'No permissions found',         'അനുമതികൾ കണ്ടെത്തിയില്ല'),
        ('sub_admins_dialog.toast_created',                 'Sub-admin created successfully', 'സബ്-അഡ്മിൻ വിജയകരമായി സൃഷ്ടിച്ചു'),
        ('sub_admins_dialog.toast_updated',                 'Sub-admin updated successfully', 'സബ്-അഡ്മിൻ വിജയകരമായി അപ്ഡേറ്റ് ചെയ്തു'),

        # ── confirm_dialog — Global delete confirmation dialog ────────────
        ('confirm_dialog.delete_language',      'Delete Language',                  'ഭാഷ ഇല്ലാതാക്കുക'),
        ('confirm_dialog.delete_category',      'Delete Category',                  'വിഭാഗം ഇല്ലാതാക്കുക'),
        ('confirm_dialog.delete_translation',   'Delete Translation',               'വിവർത്തനം ഇല്ലാതാക്കുക'),
        ('confirm_dialog.delete_tmpl_code',     'Delete Template Code',             'ടെംപ്ലേറ്റ് കോഡ് ഇല്ലാതാക്കുക'),
        ('confirm_dialog.delete_template',         'Delete Template',                  'ടെംപ്ലേറ്റ് ഇല്ലാതാക്കുക'),
        ('confirm_dialog.delete_channel_setting',  'Delete Channel Setting',           'ചാനൽ ക്രമീകരണം ഇല്ലാതാക്കുക'),
        ('confirm_dialog.delete_menu_item',        'Delete Menu Item',                 'മെനു ഇനം ഇല്ലാതാക്കുക'),
        ('confirm_dialog.delete_sub_admin',        'Delete Sub-Admin',                 'സബ്-അഡ്മിൻ ഇല്ലാതാക്കുക'),
        ('confirm_dialog.deleting',                'Deleting...',                      'ഇല്ലാതാക്കുന്നു...'),

        # ── fpo_actions_table ─────────────────────────────────────────────────
        ('fpo_actions_table.page_title',           'FPO Actions',                      'FPO ആക്ഷനുകൾ'),
        ('fpo_actions_table.page_description',     'Manage actions that can be performed within an FPO', 'FPO-നുള്ളിൽ നടത്താവുന്ന ആക്ഷനുകൾ നിയന്ത്രിക്കുക'),
        ('fpo_actions_table.add_action_btn',       'Add Action',                       'ആക്ഷൻ ചേർക്കുക'),
        ('fpo_actions_table.col_code',             'Code',                             'കോഡ്'),
        ('fpo_actions_table.col_translations',     'Languages',                        'ഭാഷകൾ'),
        ('fpo_actions_table.col_description',      'Description',                      'വിവരണം'),
        ('fpo_actions_table.col_status',           'Status',                           'സ്ഥിതി'),
        ('fpo_actions_table.view_title',           'Action Details',                   'ആക്ഷൻ വിശദാംശങ്ങൾ'),
        ('fpo_actions_table.action_activate',      'Activate',                         'സജീവമാക്കുക'),
        ('fpo_actions_table.action_deactivate',    'Deactivate',                       'നിഷ്ക്രിയമാക്കുക'),
        ('fpo_actions_table.toast_activated',      'Action activated',                 'ആക്ഷൻ സജീവമാക്കി'),
        ('fpo_actions_table.toast_deactivated',    'Action deactivated',               'ആക്ഷൻ നിഷ്ക്രിയമാക്കി'),
        ('fpo_actions_table.deleted',              'Action deleted',                   'ആക്ഷൻ ഇല്ലാതാക്കി'),
        ('fpo_actions_table.delete_title',         'Delete Action',                    'ആക്ഷൻ ഇല്ലാതാക്കുക'),
        ('fpo_actions_table.delete_description',   'Are you sure you want to delete "{name}"? This action cannot be undone.', '"{name}" ഇല്ലാതാക്കണമോ? ഇത് പഴയപടിയാക്കാൻ കഴിയില്ല.'),

        # ── fpo_actions_dialog ────────────────────────────────────────────────
        ('fpo_actions_dialog.add_title',               'Add Action',                       'ആക്ഷൻ ചേർക്കുക'),
        ('fpo_actions_dialog.edit_title',              'Edit Action',                      'ആക്ഷൻ എഡിറ്റ് ചെയ്യുക'),
        ('fpo_actions_dialog.code_label',              'Code',                             'കോഡ്'),
        ('fpo_actions_dialog.code_placeholder',        'e.g. can_view_financials',         'ഉദാ. can_view_financials'),
        ('fpo_actions_dialog.description_label',       'Description',                      'വിവരണം'),
        ('fpo_actions_dialog.description_placeholder', 'Briefly describe what this action allows', 'ഈ ആക്ഷൻ അനുവദിക്കുന്നത് സംക്ഷിപ്തമായി വിവരിക്കുക'),
        ('fpo_actions_dialog.label_en_placeholder',    'e.g. View Financial Reports',      'ഉദാ. View Financial Reports'),
        ('fpo_actions_dialog.label_other_placeholder', 'Translation (optional)',            'വിവർത്തനം (ഓപ്ഷണൽ)'),
        ('fpo_actions_dialog.toast_created',           'Action created',                   'ആക്ഷൻ സൃഷ്ടിച്ചു'),
        ('fpo_actions_dialog.toast_updated',           'Action updated',                   'ആക്ഷൻ അപ്ഡേറ്റ് ചെയ്തു'),
        ('fpo_actions_dialog.toast_failed',            'Failed to save action',            'ആക്ഷൻ സേവ് ചെയ്യൽ പരാജയപ്പെട്ടു'),

        # ── fpo_roles_table ───────────────────────────────────────────────────
        ('fpo_roles_table.add_role_btn',           'Add Member Role',                  'അംഗ റോൾ ചേർക്കുക'),
        ('fpo_roles_table.col_code',               'Code',                             'കോഡ്'),
        ('fpo_roles_table.col_name_en',            'English Name',                     'ഇംഗ്ലീഷ് പേര്'),
        ('fpo_roles_table.col_name_ml',            'Malayalam Name',                   'മലയാളം പേര്'),
        ('fpo_roles_table.col_status',             'Status',                           'സ്ഥിതി'),
        ('fpo_roles_table.view_title',             'Role Details',                     'റോൾ വിശദാംശങ്ങൾ'),
        ('fpo_roles_table.action_activate',        'Activate',                         'സജീവമാക്കുക'),
        ('fpo_roles_table.action_deactivate',      'Deactivate',                       'നിഷ്ക്രിയമാക്കുക'),
        ('fpo_roles_table.deleted',                'Role deleted',                     'റോൾ ഇല്ലാതാക്കി'),
        ('fpo_roles_table.delete_title',           'Delete Role',                      'റോൾ ഇല്ലാതാക്കുക'),
        ('fpo_roles_table.delete_description',     'Are you sure you want to delete "{name}"? This action cannot be undone.', '"{name}" ഇല്ലാതാക്കണമോ? ഇത് പഴയപടിയാക്കാൻ കഴിയില്ല.'),
        ('fpo_roles_table.toast_activated',        'Role activated',                   'റോൾ സജീവമാക്കി'),
        ('fpo_roles_table.toast_deactivated',      'Role deactivated',                 'റോൾ നിഷ്ക്രിയമാക്കി'),

        # ── fpo_roles_dialog ──────────────────────────────────────────────────
        ('fpo_roles_dialog.add_title',             'Add Member Role',                  'അംഗ റോൾ ചേർക്കുക'),
        ('fpo_roles_dialog.edit_title',            'Edit Member Role',                 'അംഗ റോൾ എഡിറ്റ് ചെയ്യുക'),
        ('fpo_roles_dialog.code_label',            'Code',                             'കോഡ്'),
        ('fpo_roles_dialog.code_placeholder',      'e.g. secretary',                   'ഉദാ. secretary'),
        ('fpo_roles_dialog.name_en_label',         'English Name',                     'ഇംഗ്ലീഷ് പേര്'),
        ('fpo_roles_dialog.name_en_placeholder',   'e.g. Secretary',                   'ഉദാ. Secretary'),
        ('fpo_roles_dialog.name_ml_label',         'Malayalam Name',                   'മലയാളം പേര്'),
        ('fpo_roles_dialog.name_ml_placeholder',   'e.g. സെക്രട്ടറി',                 'ഉദാ. സെക്രട്ടറി'),
        ('fpo_roles_dialog.active_label',          'Active',                           'സജീവം'),
        ('fpo_roles_dialog.toast_created',         'Role created',                     'റോൾ സൃഷ്ടിച്ചു'),
        ('fpo_roles_dialog.toast_updated',         'Role updated',                     'റോൾ അപ്ഡേറ്റ് ചെയ്തു'),
        ('fpo_roles_dialog.toast_failed',          'Failed to save role',              'റോൾ സേവ് ചെയ്യൽ പരാജയപ്പെട്ടു'),

        # ── fpo_permissions ───────────────────────────────────────────────────
        ('fpo_permissions.page_title',             'FPO Permissions',                  'FPO അനുമതികൾ'),
        ('fpo_permissions.page_description',       'Manage FPO actions, member roles and their permission matrix', 'FPO ആക്ഷനുകളും അംഗ റോളുകളും അനുമതി മാട്രിക്സും നിയന്ത്രിക്കുക'),
        ('fpo_permissions.tab_actions',            'FPO Actions',                      'FPO ആക്ഷനുകൾ'),
        ('fpo_permissions.tab_roles',              'Member Roles',                     'അംഗ റോളുകൾ'),
        ('fpo_permissions.tab_matrix',             'Permissions Matrix',               'അനുമതി മാട്രിക്സ്'),
        ('fpo_permissions.matrix_empty',           'No roles found. Add member roles first.', 'റോളുകൾ കണ്ടെത്തിയില്ല. ആദ്യം അംഗ റോളുകൾ ചേർക്കുക.'),
        ('fpo_permissions.matrix_save_btn',        'Save Changes',                     'മാറ്റങ്ങൾ സേവ് ചെയ്യുക'),
        ('fpo_permissions.matrix_saving',          'Saving...',                        'സേവ് ചെയ്യുന്നു...'),
        ('fpo_permissions.matrix_saved',           'Permissions saved',                'അനുമതികൾ സേവ് ചെയ്തു'),
        ('fpo_permissions.matrix_save_failed',     'Failed to save permissions',       'അനുമതികൾ സേവ് ചെയ്യൽ പരാജയപ്പെട്ടു'),
        # ── applications_table ────────────────────────────────────────────────
        ('applications_table.page_title',                   'FPO Applications',                         'FPO അപേക്ഷകൾ'),
        ('applications_table.page_description',             'Review and manage FPO registration applications', 'FPO രജിസ്ട്രേഷൻ അപേക്ഷകൾ അവലോകനം ചെയ്യുകയും നിയന്ത്രിക്കുകയും ചെയ്യുക'),
        ('applications_table.filter_status',                'Status',                                   'നില'),
        ('applications_table.filter_district',              'District',                                 'ജില്ല'),
        ('applications_table.filter_tier',                  'Tier',                                     'ടയർ'),
        ('applications_table.col_application_id',           'Application ID',                           'അപേക്ഷ ഐഡി'),
        ('applications_table.col_fpo_name',                 'FPO Name',                                 'FPO പേര്'),
        ('applications_table.col_district',                 'District',                                 'ജില്ല'),
        ('applications_table.col_status',                   'Status',                                   'നില'),
        ('applications_table.col_tier',                     'Tier',                                     'ടയർ'),
        ('applications_table.col_members',                  'Members',                                  'അംഗങ്ങൾ'),
        ('applications_table.col_last_updated',             'Last Updated',                             'അവസാനം അപ്ഡേറ്റ് ചെയ്തത്'),
        ('applications_table.action_view',                  'View',                                     'കാണുക'),
        ('applications_table.action_mark_under_review',     'Mark Under Review',                        'അവലോകനത്തിലാക്കുക'),
        ('applications_table.section_basic_info',           'Basic Information',                        'അടിസ്ഥാന വിവരങ്ങൾ'),
        ('applications_table.section_contact',              'Contact & Location',                       'ബന്ധപ്പെടൽ & സ്ഥാനം'),
        ('applications_table.section_signatory',            'Signatory & Members',                      'ഒപ്പിടുന്നയാൾ & അംഗങ്ങൾ'),
        ('applications_table.section_business',             'Business & Bank',                          'ബിസിനസ് & ബാങ്ക്'),
        ('applications_table.section_documents',            'Documents',                                'രേഖകൾ'),
        ('applications_table.section_timeline',             'Status Timeline',                          'നില ടൈംലൈൻ'),
        ('applications_table.btn_start_review',             'Start Review',                             'അവലോകനം ആരംഭിക്കുക'),
        ('applications_table.btn_approve',                  'Approve',                                  'അംഗീകരിക്കുക'),
        ('applications_table.btn_approving',                'Approving…',                               'അംഗീകരിക്കുന്നു…'),
        ('applications_table.btn_reject',                   'Reject',                                   'നിരസിക്കുക'),
        ('applications_table.btn_request_info',             'Request Info',                             'വിവരം അഭ്യർഥിക്കുക'),
        ('applications_table.btn_user_limit',               'User Limit',                               'ഉപയോക്തൃ പരിധി'),
        ('applications_table.submission_issues',            'Submission Issues',                        'സമർപ്പണ പ്രശ്നങ്ങൾ'),
        ('applications_table.doc_no_uploads',               'No documents uploaded yet.',               'ഇതുവരെ രേഖകൾ അപ്‌ലോഡ് ചെയ്തിട്ടില്ല.'),
        ('applications_table.doc_required_badge',           'Required',                                 'ആവശ്യമാണ്'),
        ('applications_table.doc_view_link',                'View',                                     'കാണുക'),
        ('applications_table.doc_verified',                 'Verified',                                 'പരിശോധിച്ചു'),
        ('applications_table.doc_verify_btn',               'Verify',                                   'പരിശോധിക്കുക'),
        ('applications_table.timeline_empty',               'No status changes recorded yet.',          'ഇതുവരെ നില മാറ്റങ്ങൾ രേഖപ്പെടുത്തിയിട്ടില്ല.'),
        ('applications_table.field_name_en',                'FPO Name (English)',                       'FPO പേര് (ഇംഗ്ലീഷ്)'),
        ('applications_table.field_name_ml',                'FPO Name (Malayalam)',                     'FPO പേര് (മലയാളം)'),
        ('applications_table.field_registered_under',       'Registered Under',                         'രജിസ്ട്രേഷൻ നിയമം'),
        ('applications_table.field_reg_number',             'Registration Number',                      'രജിസ്ട്രേഷൻ നമ്പർ'),
        ('applications_table.field_cin',                    'CIN Number',                               'CIN നമ്പർ'),
        ('applications_table.field_reg_date',               'Date of Registration',                     'രജിസ്ട്രേഷൻ തീയതി'),
        ('applications_table.field_pan',                    'PAN Number',                               'PAN നമ്പർ'),
        ('applications_table.field_gst',                    'GST Number',                               'GST നമ്പർ'),
        ('applications_table.field_district',               'District',                                 'ജില്ല'),
        ('applications_table.field_block_taluk',            'Block / Taluk',                            'ബ്ലോക്ക് / താലൂക്ക്'),
        ('applications_table.field_village_town',           'Village / Town',                           'ഗ്രാമം / പട്ടണം'),
        ('applications_table.field_pincode',                'Pincode',                                  'പിൻകോഡ്'),
        ('applications_table.field_address',                'Address',                                  'വിലാസം'),
        ('applications_table.field_office_phone',           'Office Phone',                             'ഓഫീസ് ഫോൺ'),
        ('applications_table.field_office_email',           'Office Email',                             'ഓഫീസ് ഇമെയിൽ'),
        ('applications_table.field_website',                'Website',                                  'വെബ്സൈറ്റ്'),
        ('applications_table.field_signatory_name',         'Signatory Name',                           'ഒപ്പിടുന്നയാളുടെ പേര്'),
        ('applications_table.field_designation',            'Designation',                              'പദവി'),
        ('applications_table.field_signatory_phone',        'Signatory Phone',                          'ഒപ്പിടുന്നയാളുടെ ഫോൺ'),
        ('applications_table.field_signatory_email',        'Signatory Email',                          'ഒപ്പിടുന്നയാളുടെ ഇമെയിൽ'),
        ('applications_table.field_aadhaar_last4',          'Aadhaar Last 4 Digits',                    'ആധാർ അവസാന 4 അക്കങ്ങൾ'),
        ('applications_table.field_total_members',          'Total',                                    'ആകെ'),
        ('applications_table.field_male_members',           'Male',                                     'പുരുഷൻ'),
        ('applications_table.field_female_members',         'Female',                                   'സ്ത്രീ'),
        ('applications_table.field_sc_st_members',          'SC / ST',                                  'SC / ST'),
        ('applications_table.field_primary_commodities',    'Primary Commodities',                      'പ്രാഥമിക ചരക്കുകൾ'),
        ('applications_table.field_secondary_commodities',  'Secondary Commodities',                    'ദ്വിതീയ ചരക്കുകൾ'),
        ('applications_table.field_annual_turnover',        'Annual Turnover (₹)',                      'വാർഷിക വിറ്റുവരവ് (₹)'),
        ('applications_table.field_bank_name',              'Bank Name',                                'ബാങ്കിന്റെ പേര്'),
        ('applications_table.field_bank_branch',            'Branch',                                   'ശാഖ'),
        ('applications_table.field_account_number',         'Account Number',                           'അക്കൗണ്ട് നമ്പർ'),
        ('applications_table.field_ifsc',                   'IFSC Code',                                'IFSC കോഡ്'),
        ('applications_table.field_description',            'About FPO',                                'FPO-യെ കുറിച്ച്'),
        ('applications_table.reject_dialog_title',          'Reject Application',                       'അപേക്ഷ നിരസിക്കുക'),
        ('applications_table.reject_reason_label',          'Rejection Reason',                         'നിരസിക്കാനുള്ള കാരണം'),
        ('applications_table.reject_reason_hint',           'Minimum 20 characters — explain why the application is being rejected', 'കുറഞ്ഞത് 20 അക്ഷരങ്ങൾ — അപേക്ഷ നിരസിക്കുന്നതിന്റെ കാരണം വിശദീകരിക്കുക'),
        ('applications_table.reject_btn_submit',            'Reject Application',                       'അപേക്ഷ നിരസിക്കുക'),
        ('applications_table.reject_btn_submitting',        'Rejecting…',                               'നിരസിക്കുന്നു…'),
        ('applications_table.req_info_dialog_title',        'Request Additional Information',            'അധിക വിവരം അഭ്യർഥിക്കുക'),
        ('applications_table.req_info_notes_label',         'Notes for FPO',                            'FPO-യ്ക്കുള്ള കുറിപ്പുകൾ'),
        ('applications_table.req_info_notes_hint',          'Describe what additional information or corrections are needed', 'എന്ത് അധിക വിവരമോ തിരുത്തലോ ആവശ്യമാണെന്ന് വിവരിക്കുക'),
        ('applications_table.req_info_btn_submit',          'Send Request',                             'അഭ്യർഥന അയക്കുക'),
        ('applications_table.req_info_btn_submitting',      'Sending…',                                 'അയക്കുന്നു…'),
        ('applications_table.user_limit_dialog_title',      'Set Secondary User Limit',                 'ദ്വിതീയ ഉപയോക്തൃ പരിധി നിശ്ചയിക്കുക'),
        ('applications_table.user_limit_field_label',       'Max Secondary Users',                      'പരമാവധി ദ്വിതീയ ഉപയോക്താക്കൾ'),
    ]

    count = 0
    for key, en_value, ml_value in ui_keys:
        Translation.objects.get_or_create(
            category=category, key=key, language=lang_en,
            defaults={'value': en_value, 'context': 'Frontend UI label', 'is_verified': True}
        )
        Translation.objects.get_or_create(
            category=category, key=key, language=lang_ml,
            defaults={'value': ml_value, 'context': 'Frontend UI label', 'is_verified': True}
        )
        count += 1

    return count


def seed_menu_translations(languages):
    """Seed sidebar navigation menu label translations (category: menu)."""
    category = TranslationCategory.objects.get(code='menu')
    lang_en  = languages['en']
    lang_ml  = languages['ml']

    menu_keys = [
        ('dashboard',              'Dashboard',                'ഡാഷ്ബോർഡ്'),
        ('languages_translations', 'Languages & Translations', 'ഭാഷകളും വിവർത്തനങ്ങളും'),
        ('notifications',          'Notifications',            'അറിയിപ്പുകൾ'),
        ('menu_cms',               'Menu CMS',                 'മെനു CMS'),
        ('roles',                  'Roles',                    'റോളുകൾ'),
        ('sub_admins',             'Sub-Admins',               'സബ്-അഡ്മിൻ'),
        ('fpo_actions',            'FPO Actions',              'FPO ആക്ഷനുകൾ'),
        ('fpo_member_roles',       'Member Roles',             'അംഗ റോളുകൾ'),
        ('fpo_permissions',        'FPO Permissions',          'FPO അനുമതികൾ'),
        ('fpo_applications',       'FPO Applications',         'FPO അപേക്ഷകൾ'),
    ]

    count = 0
    for key, en_value, ml_value in menu_keys:
        Translation.objects.get_or_create(
            category=category, key=key, language=lang_en,
            defaults={'value': en_value, 'context': 'Sidebar navigation menu label', 'is_verified': True}
        )
        Translation.objects.get_or_create(
            category=category, key=key, language=lang_ml,
            defaults={'value': ml_value, 'context': 'Sidebar navigation menu label', 'is_verified': True}
        )
        count += 1

    return count


def seed_translations():
    """Main seed function"""
    print("=" * 60)
    print("SEEDING TRANSLATION DATA")
    print("=" * 60)

    # Step 1: Create languages
    languages_qs = create_languages()
    languages = {lang.code: lang for lang in languages_qs}

    # Step 2: Create categories
    create_categories()

    # Step 3: Migrate messages from messages.py
    print("\nMigrating translations from messages.py...")

    migrations = [
        ('auth', AuthMessages),
        ('fpo', FPOMessages),
        ('validation', ValidationMessages),
        ('common', CommonMessages),
        ('role', RoleMessages),
    ]

    total_count = 0
    for category_code, message_class in migrations:
        count = migrate_message_class(category_code, message_class, languages)
        print(f"✅ Migrated {count} messages from {message_class.__name__}")
        total_count += count

    # Step 4: Seed admin messages
    print("\nSeeding admin management translations...")
    admin_count = seed_admin_translations(languages)
    print(f"✅ Seeded {admin_count} admin translations")
    total_count += admin_count

    # Step 5: Seed UI labels (frontend field labels, buttons, page titles)
    print("\nSeeding UI label translations...")
    ui_count = seed_ui_translations(languages)
    print(f"✅ Seeded {ui_count} UI label translations")
    total_count += ui_count

    # Step 6: Seed menu labels (sidebar navigation)
    print("\nSeeding menu label translations...")
    menu_count = seed_menu_translations(languages)
    print(f"✅ Seeded {menu_count} menu label translations")
    total_count += menu_count

    print("\n" + "=" * 60)
    print(f"✅ SUCCESS! Migrated {total_count} translations")
    print("=" * 60)

    # Summary
    print("\nDatabase Summary:")
    print(f"  Languages: {Language.objects.count()}")
    print(f"  Categories: {TranslationCategory.objects.count()}")
    print(f"  Translations: {Translation.objects.count()}")

    # Show sample translations
    print("\nSample translations (auth category):")
    for trans in Translation.objects.filter(category__code='auth')[:5]:
        print(f"  {trans.full_key} ({trans.language.code}): {trans.value[:50]}...")


if __name__ == '__main__':
    try:
        seed_translations()
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
