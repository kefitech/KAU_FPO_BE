"""
Sub-admin permission: view CBBOs and government officials in every district.

Without it a sub-admin sees only their own district's CBBOs / officials plus
state-wide ones (apps/core/permissions/cbbo_govt_scope.py). Mirrors the
pattern in 0003_new_sub_admin_permissions.
"""

from django.db import migrations


NEW_PERMISSIONS = [
    ('can_view_all_cbbo_govt', 'Can view CBBOs and government officials in every district (read-only outside own district)'),
]


def create_new_permissions(apps, schema_editor):
    Permission  = apps.get_model('auth', 'Permission')
    ContentType = apps.get_model('contenttypes', 'ContentType')

    ct, _ = ContentType.objects.get_or_create(app_label='accounts', model='subadmin')

    for codename, name in NEW_PERMISSIONS:
        Permission.objects.get_or_create(
            codename=codename,
            content_type=ct,
            defaults={'name': name},
        )


def remove_new_permissions(apps, schema_editor):
    Permission  = apps.get_model('auth', 'Permission')
    ContentType = apps.get_model('contenttypes', 'ContentType')
    try:
        ct = ContentType.objects.get(app_label='accounts', model='subadmin')
        Permission.objects.filter(
            content_type=ct,
            codename__in=[c for c, _ in NEW_PERMISSIONS],
        ).delete()
    except ContentType.DoesNotExist:
        pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_new_sub_admin_permissions'),
    ]

    operations = [
        migrations.RunPython(create_new_permissions, reverse_code=remove_new_permissions),
    ]
