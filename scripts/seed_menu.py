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

    # ── Groups ────────────────────────────────────────────────────────────────
    super_admin_group, _ = Group.objects.get_or_create(name='super_admin')
    sub_admin_group, _   = Group.objects.get_or_create(name='sub_admin')
    primary_group, _     = Group.objects.get_or_create(name='primary')
    secondary_group, _   = Group.objects.get_or_create(name='secondary')

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

    # ── FPO portal pages (all roles — adjustable via Page Access UI) ─────────

    fpo_roles = [primary_group, secondary_group]

    seed_item(
        label_key = 'menu.fpo_dashboard',
        path      = '/fpo/dashboard',
        icon      = 'layout-dashboard',
        roles     = fpo_roles,
        order     = 1,
    )
    seed_item(
        label_key = 'menu.fpo_register',
        path      = '/fpo/register',
        icon      = 'file-plus',
        roles     = fpo_roles,
        order     = 2,
    )
    seed_item(
        label_key = 'menu.fpo_status',
        path      = '/fpo/status',
        icon      = 'activity',
        roles     = fpo_roles,
        order     = 3,
    )
    seed_item(
        label_key = 'menu.fpo_profile',
        path      = '/fpo/profile',
        icon      = 'building',
        roles     = fpo_roles,
        order     = 4,
    )
    seed_item(
        label_key = 'menu.fpo_applications',
        path      = '/fpo/applications',
        icon      = 'folder',
        roles     = fpo_roles,
        order     = 5,
    )
    seed_item(
        label_key = 'menu.fpo_recommendations',
        path      = '/fpo/recommendations',
        icon      = 'sparkles',
        roles     = fpo_roles,
        order     = 6,
    )
    seed_item(
        label_key = 'menu.fpo_products',
        path      = '/fpo/products',
        icon      = 'package',
        roles     = fpo_roles,
        order     = 7,
    )
    seed_item(
        label_key = 'menu.fpo_market',
        path      = '/fpo/market',
        icon      = 'trending-up',
        roles     = fpo_roles,
        order     = 8,
    )
    seed_item(
        label_key = 'menu.fpo_dpr',
        path      = '/fpo/dpr',
        icon      = 'file-bar-chart',
        roles     = fpo_roles,
        order     = 9,
    )
    seed_item(
        label_key = 'menu.fpo_settings',
        path      = '/fpo/settings',
        icon      = 'settings',
        roles     = fpo_roles,
        order     = 10,
    )

    print("\n" + "=" * 60)
    print(f"✅ Done. Total menu items: {MenuItem.objects.count()}")
    print("=" * 60)
