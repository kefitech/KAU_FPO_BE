"""
Data migration to create predefined roles (Groups).

Creates 7 default roles for the KAU-FPO platform from UserRole constants:
1. super_admin - Full system access
2. admin - System administration
3. fpo_manager - FPO management
4. government - Government portal access
5. cbbo - CBBO/NGO portal access
6. expert - Expert services
7. viewer - Read-only access

Author: Athul Gopan
Created: 22-04-2026
"""

from django.db import migrations


def create_roles(apps, schema_editor):
    """Create predefined roles from UserRole constants."""
    from apps.core.utils.constants import UserRole

    Group = apps.get_model('auth', 'Group')

    # Use UserRole enum values to ensure consistency
    roles = [
        UserRole.SUPER_ADMIN,
        UserRole.ADMIN,
        UserRole.FPO_MANAGER,
        UserRole.GOVERNMENT,
        UserRole.CBBO,
        UserRole.EXPERT,
        UserRole.VIEWER,
    ]

    for role_name in roles:
        Group.objects.get_or_create(name=role_name)


def delete_roles(apps, schema_editor):
    """Reverse migration - delete predefined roles."""
    from apps.core.utils.constants import UserRole

    Group = apps.get_model('auth', 'Group')

    roles = [
        UserRole.SUPER_ADMIN,
        UserRole.ADMIN,
        UserRole.FPO_MANAGER,
        UserRole.GOVERNMENT,
        UserRole.CBBO,
        UserRole.EXPERT,
        UserRole.VIEWER,
    ]

    Group.objects.filter(name__in=roles).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_roles, delete_roles),
    ]
