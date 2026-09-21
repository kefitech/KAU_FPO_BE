"""
Seed initial menu items with role assignments.

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/seed_menu.py').read())
    seed_menu()
    "

Only seeds if not already present (idempotent).
Add new menu items here as new pages are built.
"""

from django.contrib.auth.models import Group
from apps.database.models import MenuItem


def seed_menu():
    print("=" * 60)
    print("SEEDING MENU ITEMS")
    print("=" * 60)

    # ── Retire stale FPO menu items ──────────────────────────────────────────
    # register/status are onboarding-wizard steps under (wizard)/, not portal nav.
    stale_keys = ['menu.fpo_register', 'menu.fpo_status']
    deleted, _ = MenuItem.objects.filter(label_key__in=stale_keys).delete()
    if deleted:
        print(f"🗑️  Removed {deleted} stale menu item(s): {', '.join(stale_keys)}")

    # ── Groups ────────────────────────────────────────────────────────────────
    super_admin_group, _ = Group.objects.get_or_create(name='super_admin')
    sub_admin_group, _   = Group.objects.get_or_create(name='sub_admin')
    government_group, _  = Group.objects.get_or_create(name='government')
    cbbo_group, _        = Group.objects.get_or_create(name='cbbo')
    external_buyer_group, _ = Group.objects.get_or_create(name='external_buyer')

    def seed_item(label_key, path, icon, roles, parent=None, order=0):
        item, created = MenuItem.objects.get_or_create(
            label_key=label_key,
            path=path,
            defaults={
                'icon':      icon,
                'parent':    parent,
                'order':     order,
                'is_active': True,
            }
        )
        item.roles.set(roles)
        status = '✅ Created' if created else '⏭️  Exists '
        print(f"{status}  {label_key}  →  {path}")
        return item

    # ── Admin portal pages ────────────────────────────────────────────────────

    seed_item(
        label_key = 'menu.languages_translations',
        path      = '/admin/languages',
        icon      = 'globe',
        roles     = [super_admin_group],
        order     = 1,
    )
    seed_item(
        label_key = 'menu.notifications',
        path      = '/admin/notifications',
        icon      = 'bell',
        roles     = [super_admin_group],
        order     = 2,
    )
    seed_item(
        label_key = 'menu.roles',
        path      = '/admin/roles',
        icon      = 'shield',
        roles     = [super_admin_group],
        order     = 3,
    )
    seed_item(
        label_key = 'menu.sub_admins',
        path      = '/admin/sub-admins',
        icon      = 'shield-check',
        roles     = [super_admin_group],
        order     = 4,
    )
    seed_item(
        label_key = 'menu.fpo_actions',
        path      = '/admin/fpo-permissions?tab=actions',
        icon      = 'zap',
        roles     = [super_admin_group],
        order     = 5,
    )
    seed_item(
        label_key = 'menu.fpo_member_roles',
        path      = '/admin/fpo-permissions?tab=roles',
        icon      = 'users',
        roles     = [super_admin_group],
        order     = 6,
    )
    seed_item(
        label_key = 'menu.fpo_permissions',
        path      = '/admin/fpo-permissions?tab=matrix',
        icon      = 'shield-check',
        roles     = [super_admin_group],
        order     = 7,
    )
    seed_item(
        label_key = 'menu.fpo_applications',
        path      = '/admin/applications',
        icon      = 'file-text',
        roles     = [super_admin_group, sub_admin_group],
        order     = 8,
    )
    seed_item(
        label_key = 'menu.external_apis',
        path      = '/admin/external-apis',
        icon      = 'plug',
        roles     = [super_admin_group],
        order     = 9,
    )
    seed_item(
        label_key = 'menu.site_content',
        path      = '/admin/site-content',
        icon      = 'layout',
        roles     = [super_admin_group],
        order     = 10,
    )
    seed_item(
        label_key = 'menu.announcements',
        path      = '/admin/announcements',
        icon      = 'megaphone',
        roles     = [super_admin_group, sub_admin_group],
        order     = 11,
    )
    seed_item(
        label_key = 'menu.faqs',
        path      = '/admin/faqs',
        icon      = 'help-circle',
        roles     = [super_admin_group, sub_admin_group],
        order     = 12,
    )
    seed_item(
        label_key = 'menu.dashboard',
        path      = '/admin/dashboard',
        icon      = 'bar-chart-2',
        roles     = [super_admin_group, sub_admin_group],
        order     = 13,
    )
    seed_item(
        label_key = 'menu.ownership_claims',
        path      = '/admin/ownership-claims',
        icon      = 'briefcase',
        roles     = [super_admin_group, sub_admin_group],
        order     = 14,
    )
    seed_item(
        label_key = 'menu.audit_logs',
        path      = '/admin/audit-logs',
        icon      = 'clipboard-list',
        roles     = [super_admin_group],
        order     = 15,
    )
    seed_item(
        label_key = 'menu.experts',
        path      = '/admin/experts',
        icon      = 'user-check',
        roles     = [super_admin_group, sub_admin_group],
        order     = 16,
    )
    seed_item(
        label_key = 'menu.schemes',
        path      = '/admin/schemes',
        icon      = 'book-open',
        roles     = [super_admin_group, sub_admin_group],
        order     = 17,
    )
    seed_item(
        label_key = 'menu.dpr_projects',
        path      = '/admin/dpr',
        icon      = 'file-bar-chart',
        roles     = [super_admin_group, sub_admin_group],
        order     = 18,
    )
    seed_item(
        label_key = 'menu.dpr_config',
        path      = '/admin/dpr-config',
        icon      = 'sliders-horizontal',
        roles     = [super_admin_group],
        order     = 19,
    )
    # DPR admin surfaces — 2026-09-19 sweep.
    # These pages have existed on the FE for a while; the menu entries
    # were missing so super_admin had to type the URL. Placed at the end
    # of the super_admin block (order 30-34); MenuItem.order is a
    # PositiveIntegerField so decimals aren't allowed.
    seed_item(
        label_key = 'menu.dpr_master_data',
        path      = '/admin/dpr/master-data',
        icon      = 'database',
        roles     = [super_admin_group],
        order     = 30,
    )
    seed_item(
        label_key = 'menu.dpr_applicability',
        path      = '/admin/dpr-applicability',
        icon      = 'grid-3x3',
        roles     = [super_admin_group],
        order     = 31,
    )
    seed_item(
        label_key = 'menu.dpr_field_rules',
        path      = '/admin/dpr-field-rules',
        icon      = 'git-branch',
        roles     = [super_admin_group],
        order     = 32,
    )
    seed_item(
        label_key = 'menu.dpr_knowledge',
        path      = '/admin/dpr-knowledge',
        icon      = 'book-open',
        roles     = [super_admin_group],
        order     = 33,
    )
    seed_item(
        label_key = 'menu.dpr_risk_matrix',
        path      = '/admin/dpr-risk-matrix',
        icon      = 'shield-alert',
        roles     = [super_admin_group],
        order     = 34,
    )
    seed_item(
        label_key = 'menu.ai_services',
        path      = '/admin/ai-services',
        icon      = 'bot',
        roles     = [super_admin_group],
        order     = 20,
    )

    seed_item(
        label_key = 'menu.ml_models',
        path      = '/admin/ml-models',
        icon      = 'brain-circuit',
        roles     = [super_admin_group],
        order     = 21,
    )
    seed_item(
        label_key = 'menu.gis_zones',
        path      = '/admin/gis-zones',
        icon      = 'map',
        roles     = [super_admin_group],
        order     = 22,
    )
    seed_item(
        label_key = 'menu.soil_regions',
        path      = '/admin/soil-regions',
        icon      = 'layers',
        roles     = [super_admin_group],
        order     = 23,
    )
    # Marketplace admin (Arunima — P2-11)
    seed_item(
        label_key = 'menu.market_linkage',
        path      = '/admin/market-linkage',
        icon      = 'link',
        roles     = [super_admin_group],
        order     = 24,
    )
    seed_item(
        label_key = 'menu.buyer_directory',
        path      = '/admin/buyers',
        icon      = 'shopping-cart',
        roles     = [super_admin_group],
        order     = 25,
    )
    # Crop knowledge base admin (Aravind — P2-06)
    seed_item(
        label_key = 'menu.crop_zone_profiles',
        path      = '/admin/crop-zone-profiles',
        icon      = 'sprout',
        roles     = [super_admin_group],
        order     = 26,
    )
    seed_item(
        label_key = 'menu.crop_package_of_practices',
        path      = '/admin/crop-package-of-practices',
        icon      = 'book-open',
        roles     = [super_admin_group],
        order     = 27,
    )

    # ── FPO portal pages (all roles — adjustable via Page Access UI) ─────────

    fpo_manager_group, _ = Group.objects.get_or_create(name='fpo_manager')
    fpo_roles = [fpo_manager_group]

    seed_item(
        label_key = 'menu.fpo_dashboard',
        path      = '/fpo/dashboard',
        icon      = 'layout-dashboard',
        roles     = fpo_roles,
        order     = 1,
    )
    seed_item(
        label_key = 'menu.fpo_profile',
        path      = '/fpo/profile',
        icon      = 'building',
        roles     = fpo_roles,
        order     = 2,
    )
    seed_item(
        label_key = 'menu.fpo_applications',
        path      = '/fpo/applications',
        icon      = 'folder',
        roles     = fpo_roles,
        order     = 3,
    )
    seed_item(
        label_key = 'menu.fpo_dpr',
        path      = '/fpo/dpr',
        icon      = 'file-text',
        roles     = fpo_roles,
        order     = 4,
    )
    seed_item(
        label_key = 'menu.fpo_recommendations',
        path      = '/fpo/recommendations',
        icon      = 'sparkles',
        roles     = fpo_roles,
        order     = 5,
    )
    seed_item(
        label_key = 'menu.fpo_products',
        path      = '/fpo/products',
        icon      = 'package',
        roles     = fpo_roles,
        order     = 6,
    )
    seed_item(
        label_key = 'menu.fpo_market',
        path      = '/fpo/market',
        icon      = 'trending-up',
        roles     = fpo_roles,
        order     = 7,
    )
    seed_item(
        label_key = 'menu.fpo_schemes',
        path      = '/fpo/schemes',
        icon      = 'book-open',
        roles     = fpo_roles,
        order     = 8,
    )
    seed_item(
        label_key = 'menu.fpo_experts',
        path      = '/fpo/experts',
        icon      = 'user-check',
        roles     = fpo_roles,
        order     = 9,
    )
    seed_item(
        label_key = 'menu.fpo_tier_assessment',
        path      = '/fpo/tier-assessment',
        icon      = 'bar-chart-2',
        roles     = fpo_roles,
        order     = 10,
    )
    seed_item(
        label_key = 'menu.fpo_team',
        path      = '/fpo/team',
        icon      = 'users',
        roles     = fpo_roles,
        order     = 11,
    )
    seed_item(
        label_key = 'menu.fpo_inbox',
        path      = '/fpo/inbox',
        icon      = 'inbox',
        roles     = fpo_roles,
        order     = 12,
    )
    seed_item(
        label_key = 'menu.fpo_settings',
        path      = '/fpo/settings',
        icon      = 'settings',
        roles     = fpo_roles,
        order     = 13,
    )
    # FPO-as-buyer entry (Arunima — P2-11)
    seed_item(
        label_key = 'menu.fpo_buyer_directory',
        path      = '/fpo/buyer-directory',
        icon      = 'shopping-cart',
        roles     = fpo_roles,
        order     = 13,
    )

    # ── External Buyer portal (Arunima — P2-11) ─────────────────────────────
    buyer_roles = [external_buyer_group]

    seed_item(
        label_key = 'menu.buyer_dashboard',
        path      = '/buyer/dashboard',
        icon      = 'layout-dashboard',
        roles     = buyer_roles,
        order     = 1,
    )
    seed_item(
        label_key = 'menu.buyer_products',
        path      = '/buyer/products',
        icon      = 'package',
        roles     = buyer_roles,
        order     = 2,
    )

    # ── CBBO portal pages (Jobin) ─────────────────────────────────────────────

    # Fix: earlier record pointed at the nonexistent /cbbo/settings path
    MenuItem.objects.filter(label_key='menu.cbbo_settings').update(label_key='menu.cbbo_profile', path='/cbbo/profile')

    seed_item(
        label_key = 'menu.cbbo_dashboard',
        path      = '/cbbo/dashboard',
        icon      = 'layout-dashboard',
        roles     = [cbbo_group],
        order     = 1,
    )
    seed_item(
        label_key = 'menu.cbbo_verifications',
        path      = '/cbbo/verifications',
        icon      = 'check-circle',
        roles     = [cbbo_group],
        order     = 2,
    )
    seed_item(
        label_key = 'menu.cbbo_reports',
        path      = '/cbbo/reports',
        icon      = 'clipboard-list',
        roles     = [cbbo_group],
        order     = 3,
    )
    seed_item(
        label_key = 'menu.cbbo_profile',
        path      = '/cbbo/profile',
        icon      = 'user',
        roles     = [cbbo_group],
        order     = 4,
    )

    # ── Government portal pages (Jobin) ───────────────────────────────────────

    seed_item(
        label_key = 'menu.government_dashboard',
        path      = '/government/dashboard',
        icon      = 'layout-dashboard',
        roles     = [government_group],
        order     = 1,
    )
    seed_item(
        label_key = 'menu.government_profile',
        path      = '/government/profile',
        icon      = 'user',
        roles     = [government_group],
        order     = 2,
    )
    seed_item(
        label_key = 'menu.government_fpos',
        path      = '/government/fpos',
        icon      = 'building',
        roles     = [government_group],
        order     = 3,
    )
    seed_item(
        label_key = 'menu.government_schemes',
        path      = '/government/schemes',
        icon      = 'file-text',
        roles     = [government_group],
        order     = 4,
    )
    seed_item(
        label_key = 'menu.government_training',
        path      = '/government/training',
        icon      = 'graduation-cap',
        roles     = [government_group],
        order     = 5,
    )

    # ── Expert portal pages (Jobin) ───────────────────────────────────────────

    expert_group, _ = Group.objects.get_or_create(name='expert')

    seed_item(
        label_key = 'menu.expert_dashboard',
        path      = '/expert/dashboard',
        icon      = 'layout-dashboard',
        roles     = [expert_group],
        order     = 1,
    )
    seed_item(
        label_key = 'menu.expert_availability',
        path      = '/expert/availability',
        icon      = 'calendar-days',
        roles     = [expert_group],
        order     = 2,
    )
    seed_item(
        label_key = 'menu.expert_profile',
        path      = '/expert/profile',
        icon      = 'user',
        roles     = [expert_group],
        order     = 3,
    )

    print("\n" + "=" * 60)
    print(f"✅ Done. Total menu items: {MenuItem.objects.count()}")
    print("=" * 60)
