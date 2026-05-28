"""
Seed initial menu items with role assignments.

Run: python manage.py shell < scripts/seed_menu.py

Only seeds if not already present (idempotent).
Add new menu items here as new pages are built.
"""

import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

from django.contrib.auth.models import Group
from apps.database.models import MenuItem

print("=" * 60)
print("SEEDING MENU ITEMS")
print("=" * 60)

# Ensure roles (Groups) exist
super_admin_group, _ = Group.objects.get_or_create(name='super_admin')
sub_admin_group, _   = Group.objects.get_or_create(name='sub_admin')
fpo_manager_group, _ = Group.objects.get_or_create(name='fpo_manager')
government_group, _  = Group.objects.get_or_create(name='government')
cbbo_group, _        = Group.objects.get_or_create(name='cbbo')
expert_group, _      = Group.objects.get_or_create(name='expert')
viewer_group, _      = Group.objects.get_or_create(name='viewer')

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


# ── Top-level menu items ──────────────────────────────────────────────────────

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

# ── Add more items here as new pages are built ────────────────────────────────
# Example (FPO Management — uncomment when /admin/fpo is ready):
# seed_item(
#     label_key = 'menu.fpo_management',
#     path      = '/admin/fpo',
#     icon      = 'building',
#     roles     = [super_admin_group, sub_admin_group],
#     order     = 3,
# )

print("\n" + "=" * 60)
print(f"✅ Done. Total menu items: {MenuItem.objects.count()}")
print("=" * 60)
