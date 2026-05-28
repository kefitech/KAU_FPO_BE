"""
Seed FPO Permission Matrix
==========================

Seeds:
  1. TranslationCategory rows — fpo_member_role, fpo_action
  2. FPO member roles into MasterLookup (category='fpo_member_role')
  3. FPO actions into FPOAction
  4. Translation rows for roles and actions (EN + ML)
  5. Default permission matrix (role x action)

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/seed_fpo_permissions.py').read())
    seed_fpo_permissions()
    "

Idempotent — safe to re-run. Uses update_or_create throughout.
"""


def seed_fpo_permissions():
    from apps.core.models.generic import MasterLookup
    from apps.database.models import Language, TranslationCategory, Translation
    from apps.database.models.fpo import FPOAction, FPOMemberPermission

    lang_en = Language.objects.get(code='en')
    lang_ml = Language.objects.get(code='ml')

    # ------------------------------------------------------------------
    # 1. Translation Categories
    # ------------------------------------------------------------------
    cat_roles, _ = TranslationCategory.objects.get_or_create(
        code='fpo_member_role',
        defaults={'name': 'FPO Member Roles', 'description': 'Display names for FPO membership roles'},
    )
    cat_actions, _ = TranslationCategory.objects.get_or_create(
        code='fpo_action',
        defaults={'name': 'FPO Actions', 'description': 'Display labels for FPO permission actions'},
    )
    print("  TranslationCategories ready: fpo_member_role, fpo_action")

    # ------------------------------------------------------------------
    # 2. FPO Member Roles + Translations
    # ------------------------------------------------------------------
    ROLES = [
        {'code': 'primary',   'en': 'Primary User',   'ml': 'പ്രാഥമിക ഉപയോക്താവ്'},
        {'code': 'secondary', 'en': 'Secondary User', 'ml': 'ദ്വിതീയ ഉപയോക്താവ്'},
    ]

    role_objects = {}
    for role in ROLES:
        obj, created = MasterLookup.objects.update_or_create(
            category='fpo_member_role',
            code=role['code'],
            defaults={'is_active': True},
        )
        role_objects[role['code']] = obj

        Translation.objects.update_or_create(
            category=cat_roles, key=role['code'], language=lang_en,
            defaults={'value': role['en']},
        )
        Translation.objects.update_or_create(
            category=cat_roles, key=role['code'], language=lang_ml,
            defaults={'value': role['ml']},
        )
        print(f"  Role {'created' if created else 'updated'}: {role['code']}")

    # ------------------------------------------------------------------
    # 3. FPO Actions + Translations
    # ------------------------------------------------------------------
    ACTIONS = [
        {
            'code':        'can_submit',
            'en':          'Submit Application',
            'ml':          'അപേക്ഷ സമർപ്പിക്കുക',
            'description': 'Submit the FPO registration application to KAU Admin',
        },
        {
            'code':        'can_upload_docs',
            'en':          'Upload Documents',
            'ml':          'രേഖകൾ അപ്‌ലോഡ് ചെയ്യുക',
            'description': 'Upload and manage FPO registration documents',
        },
        {
            'code':        'can_delete_docs',
            'en':          'Delete Documents',
            'ml':          'രേഖകൾ ഇല്ലാതാക്കുക',
            'description': 'Delete uploaded documents (DRAFT status only)',
        },
        {
            'code':        'can_invite_team',
            'en':          'Invite Team Members',
            'ml':          'ടീം അംഗങ്ങളെ ക്ഷണിക്കുക',
            'description': 'Invite secondary users to join the FPO',
        },
        {
            'code':        'can_manage_team',
            'en':          'Manage Team Members',
            'ml':          'ടീം അംഗങ്ങളെ നിയന്ത്രിക്കുക',
            'description': 'Approve, deactivate, or manage secondary user permissions',
        },
        {
            'code':        'can_view_docs',
            'en':          'View Documents',
            'ml':          'രേഖകൾ കാണുക',
            'description': 'View all uploaded FPO documents',
        },
        {
            'code':        'can_edit_profile',
            'en':          'Edit FPO Profile',
            'ml':          'FPO പ്രൊഫൈൽ എഡിറ്റ് ചെയ്യുക',
            'description': 'Edit FPO registration wizard fields',
        },
        {
            'code':        'can_view_dashboard',
            'en':          'View Dashboard',
            'ml':          'ഡാഷ്ബോർഡ് കാണുക',
            'description': 'View FPO dashboard — tier, status, quick stats',
        },
        {
            'code':        'can_submit_claim',
            'en':          'Submit Ownership Claim',
            'ml':          'ഉടമസ്ഥാവകാശ അവകാശവാദം സമർപ്പിക്കുക',
            'description': 'Submit a claim for an existing FPO',
        },
    ]

    action_objects = {}
    for action in ACTIONS:
        obj, created = FPOAction.objects.update_or_create(
            code=action['code'],
            defaults={
                'description': action['description'],
                'is_active':   True,
            },
        )
        action_objects[action['code']] = obj

        Translation.objects.update_or_create(
            category=cat_actions, key=action['code'], language=lang_en,
            defaults={'value': action['en']},
        )
        Translation.objects.update_or_create(
            category=cat_actions, key=action['code'], language=lang_ml,
            defaults={'value': action['ml']},
        )
        print(f"  Action {'created' if created else 'updated'}: {action['code']}")

    # ------------------------------------------------------------------
    # 4. Default Permission Matrix
    # ------------------------------------------------------------------
    MATRIX = {
        'primary': {
            'can_submit':         True,
            'can_upload_docs':    True,
            'can_delete_docs':    True,
            'can_invite_team':    True,
            'can_manage_team':    True,
            'can_view_docs':      True,
            'can_edit_profile':   True,
            'can_view_dashboard': True,
            'can_submit_claim':   True,
        },
        'secondary': {
            'can_submit':         False,
            'can_upload_docs':    True,
            'can_delete_docs':    False,
            'can_invite_team':    False,
            'can_manage_team':    False,
            'can_view_docs':      True,
            'can_edit_profile':   False,
            'can_view_dashboard': True,
            'can_submit_claim':   False,
        },
    }

    created_count = 0
    updated_count = 0
    for role_code, permissions in MATRIX.items():
        role = role_objects[role_code]
        for action_code, is_allowed in permissions.items():
            action = action_objects[action_code]
            _, created = FPOMemberPermission.objects.update_or_create(
                role=role, action=action,
                defaults={'is_allowed': is_allowed},
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

    print(f"\nPermission matrix: {created_count} created, {updated_count} updated")
    print("Done. FPO permission matrix seeded successfully.")
