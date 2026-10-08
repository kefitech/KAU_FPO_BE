"""
Seed FPO Permission Matrix
==========================

Seeds:
  1. TranslationCategory rows — fpo_member_role, fpo_action
  2. FPO member role Groups (primary, secondary) in auth.Group
  3. FPO actions into FPOAction
  4. Translation rows for roles and actions (EN + ML)
  5. Default permission matrix (role x action) into RoleActionPermission

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/seed_fpo_permissions.py').read())
    seed_fpo_permissions()
    "

Idempotent — safe to re-run. Uses update_or_create throughout.
"""


def seed_fpo_permissions():
    from django.contrib.auth.models import Group
    from apps.database.models import Language, TranslationCategory, Translation
    from apps.database.models.fpo import FPOAction, RoleActionPermission

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
    # 2. FPO Member Role Groups + Translations
    # ------------------------------------------------------------------
    ROLES = [
        {'name': 'primary',   'en': 'Primary User',   'ml': 'പ്രാഥമിക ഉപയോക്താവ്'},
        {'name': 'secondary', 'en': 'Secondary User', 'ml': 'ദ്വിതീയ ഉപയോക്താവ്'},
    ]

    role_groups = {}
    for role in ROLES:
        group, created = Group.objects.get_or_create(name=role['name'])
        role_groups[role['name']] = group

        Translation.objects.update_or_create(
            category=cat_roles, key=role['name'], language=lang_en,
            defaults={'value': role['en']},
        )
        Translation.objects.update_or_create(
            category=cat_roles, key=role['name'], language=lang_ml,
            defaults={'value': role['ml']},
        )
        print(f"  Role Group {'created' if created else 'exists'}: {role['name']}")

    # ------------------------------------------------------------------
    # 3. FPO Actions + Translations
    # ------------------------------------------------------------------
    ACTIONS = [
        {
            'code':        'can_submit',
            'en':          'Submit Application',
            'ml':          'അപേക്ഷ സമർപ്പിക്കുക',
            'description': 'Submit the FPO registration application to KAU Admin',
            'ml_description': 'FPO രജിസ്ട്രേഷൻ അപേക്ഷ KAU അഡ്മിന് സമർപ്പിക്കുക',
        },
        {
            'code':        'can_upload_docs',
            'en':          'Upload Documents',
            'ml':          'രേഖകൾ അപ്‌ലോഡ് ചെയ്യുക',
            'description': 'Upload and manage FPO registration documents',
            'ml_description': 'FPO രജിസ്ട്രേഷൻ രേഖകൾ അപ്‌ലോഡ് ചെയ്യുകയും നിയന്ത്രിക്കുകയും ചെയ്യുക',
        },
        {
            'code':        'can_delete_docs',
            'en':          'Delete Documents',
            'ml':          'രേഖകൾ ഇല്ലാതാക്കുക',
            'description': 'Delete uploaded documents (DRAFT status only)',
            'ml_description': 'അപ്‌ലോഡ് ചെയ്ത രേഖകൾ ഇല്ലാതാക്കുക (ഡ്രാഫ്റ്റ് നിലയിൽ മാത്രം)',
        },
        {
            'code':        'can_invite_team',
            'en':          'Invite Team Members',
            'ml':          'ടീം അംഗങ്ങളെ ക്ഷണിക്കുക',
            'description': 'Invite secondary users to join the FPO',
            'ml_description': 'FPO-യിൽ ചേരാൻ ദ്വിതീയ ഉപയോക്താക്കളെ ക്ഷണിക്കുക',
        },
        {
            'code':        'can_manage_team',
            'en':          'Manage Team Members',
            'ml':          'ടീം അംഗങ്ങളെ നിയന്ത്രിക്കുക',
            'description': 'Approve, deactivate, or manage secondary user permissions',
            'ml_description': 'ദ്വിതീയ ഉപയോക്താക്കളെ അംഗീകരിക്കുക, നിഷ്ക്രിയമാക്കുക, അവരുടെ അനുമതികൾ നിയന്ത്രിക്കുക',
        },
        {
            'code':        'can_view_docs',
            'en':          'View Documents',
            'ml':          'രേഖകൾ കാണുക',
            'description': 'View all uploaded FPO documents',
            'ml_description': 'അപ്‌ലോഡ് ചെയ്ത എല്ലാ FPO രേഖകളും കാണുക',
        },
        {
            'code':        'can_edit_profile',
            'en':          'Edit FPO Profile',
            'ml':          'FPO പ്രൊഫൈൽ എഡിറ്റ് ചെയ്യുക',
            'description': 'Edit FPO registration wizard fields',
            'ml_description': 'FPO രജിസ്ട്രേഷൻ വിസാർഡിലെ വിവരങ്ങൾ എഡിറ്റ് ചെയ്യുക',
        },
        {
            'code':        'can_view_dashboard',
            'en':          'View Dashboard',
            'ml':          'ഡാഷ്ബോർഡ് കാണുക',
            'description': 'View FPO dashboard — tier, status, quick stats',
            'ml_description': 'FPO ഡാഷ്ബോർഡ് കാണുക — ടയർ, സ്ഥിതി, ചുരുക്ക കണക്കുകൾ',
        },
        {
            'code':        'can_edit_tier_assessment',
            'en':          'Edit Tier Assessment',
            'ml':          'ടയർ വിലയിരുത്തൽ എഡിറ്റ് ചെയ്യുക',
            'description': 'Answer, submit and reopen the tier assessment (view-only without this)',
            'ml_description': 'ടയർ വിലയിരുത്തലിന് ഉത്തരം നൽകുക, സമർപ്പിക്കുക, വീണ്ടും തുറക്കുക (ഇതില്ലെങ്കിൽ കാണാൻ മാത്രം)',
        },
        {
            'code':        'can_submit_claim',
            'en':          'Submit Ownership Claim',
            'ml':          'ഉടമസ്ഥാവകാശ അവകാശവാദം സമർപ്പിക്കുക',
            'description': 'Submit a claim for an existing FPO',
            'ml_description': 'നിലവിലുള്ള ഒരു FPO-യ്ക്കായി അവകാശവാദം സമർപ്പിക്കുക',
        },
        {
            'code':        'can_manage_products',
            'en':          'Manage Products',
            'ml':          'ഉൽപ്പന്നങ്ങൾ കൈകാര്യം ചെയ്യുക',
            'description': 'Add, edit, publish and delete marketplace products (view-only without this)',
            'ml_description': 'മാർക്കറ്റ്‌പ്ലേസ് ഉൽപ്പന്നങ്ങൾ ചേർക്കുക, എഡിറ്റ് ചെയ്യുക, പ്രസിദ്ധീകരിക്കുക, ഇല്ലാതാക്കുക (ഇതില്ലെങ്കിൽ കാണാൻ മാത്രം)',
        },
        {
            'code':        'can_book_experts',
            'en':          'Book Experts',
            'ml':          'വിദഗ്ധരെ ബുക്ക് ചെയ്യുക',
            'description': 'Request and cancel expert consultation bookings',
            'ml_description': 'വിദഗ്ധ കൺസൾട്ടേഷൻ ബുക്കിംഗുകൾ അഭ്യർത്ഥിക്കുകയും റദ്ദാക്കുകയും ചെയ്യുക',
        },
        {
            'code':        'can_generate_recommendations',
            'en':          'Generate AI Recommendations',
            'ml':          'AI ശുപാർശകൾ സൃഷ്ടിക്കുക',
            'description': 'Request new AI crop recommendations (view-only without this)',
            'ml_description': 'പുതിയ AI വിള ശുപാർശകൾ ആവശ്യപ്പെടുക (ഇതില്ലെങ്കിൽ കാണാൻ മാത്രം)',
        },
        {
            'code':        'can_generate_business_plan',
            'en':          'Generate Business Plan',
            'ml':          'ബിസിനസ് പ്ലാൻ സൃഷ്ടിക്കുക',
            'description': 'Generate or regenerate the AI business plan (view-only without this)',
            'ml_description': 'AI ബിസിനസ് പ്ലാൻ സൃഷ്ടിക്കുക അല്ലെങ്കിൽ വീണ്ടും സൃഷ്ടിക്കുക (ഇതില്ലെങ്കിൽ കാണാൻ മാത്രം)',
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
        # Description shown under the permission in the team invite / permissions dialogs
        for lang, value in ((lang_en, action['description']), (lang_ml, action['ml_description'])):
            Translation.objects.update_or_create(
                category=cat_actions, key=f"{action['code']}_description", language=lang,
                defaults={'value': value},
            )
        print(f"  Action {'created' if created else 'updated'}: {action['code']}")

    # ------------------------------------------------------------------
    # 4. Default Permission Matrix (primary x secondary only)
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
            'can_edit_tier_assessment': True,
            'can_manage_products':      True,
            'can_book_experts':         True,
            'can_generate_recommendations': True,
            'can_generate_business_plan':   True,
        },
        # Secondary ceiling = what the primary user can grant a team member.
        # The application (submit/documents) and the team stay primary-only.
        'secondary': {
            'can_submit':         False,
            'can_upload_docs':    False,
            'can_delete_docs':    False,
            'can_invite_team':    False,
            'can_manage_team':    False,
            'can_view_docs':      False,
            'can_edit_profile':   True,   # own personal profile — always on
            'can_view_dashboard': True,   # always on
            'can_submit_claim':   False,
            # KAU §8.1 — secondary users must NOT take the Tier Classification
            # assessment. View stays open; editing is gated by this permission
            # in apps/fpo/api/tier_assessment.py.
            'can_edit_tier_assessment': False,
            'can_manage_products':      True,
            'can_book_experts':         True,
            'can_generate_recommendations': True,
            'can_generate_business_plan':   True,
        },
    }

    created_count = 0
    updated_count = 0
    for role_name, permissions in MATRIX.items():
        group = role_groups[role_name]
        for action_code, is_allowed in permissions.items():
            action_obj = action_objects[action_code]
            _, created = RoleActionPermission.objects.update_or_create(
                role=group, action=action_obj,
                defaults={'is_allowed': is_allowed},
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

    print(f"\nPermission matrix: {created_count} created, {updated_count} updated")

    # ------------------------------------------------------------------
    # 5. Link FPOActions to their pages via menu_item FK
    # ------------------------------------------------------------------
    from apps.database.models import MenuItem

    ACTION_PAGE_MAP = {
        'can_view_dashboard': '/fpo/dashboard',
        'can_submit':         '/fpo/register',
        'can_upload_docs':    '/fpo/register',
        'can_delete_docs':    '/fpo/register',
        'can_view_docs':      '/fpo/register',
        'can_edit_profile':   '/fpo/profile',
        'can_invite_team':    '/fpo/team',
        'can_manage_team':    '/fpo/settings',
        'can_submit_claim':   '/fpo/applications',
        'can_edit_tier_assessment': '/fpo/tier-assessment',
        'can_manage_products':      '/fpo/products',
        'can_book_experts':         '/fpo/experts',
        'can_generate_recommendations': '/fpo/recommendations',
        'can_generate_business_plan':   '/fpo/recommendations',
    }

    page_cache = {}
    linked = 0
    for action_code, page_path in ACTION_PAGE_MAP.items():
        if page_path not in page_cache:
            page_cache[page_path] = MenuItem.objects.filter(path=page_path, is_active=True).first()
        page = page_cache[page_path]
        if page:
            FPOAction.objects.filter(code=action_code).update(menu_item=page)
            print(f"  Linked: {action_code}  →  {page_path}")
            linked += 1
        else:
            print(f"  ⚠️  Page not found for {action_code}: {page_path} — run seed_menu first")

    print(f"\nActions linked to pages: {linked}/{len(ACTION_PAGE_MAP)}")
    print("Done. FPO permission matrix seeded successfully.")
