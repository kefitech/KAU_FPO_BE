"""
KAU suggestion #1 — 5 new sub-admin permission codenames.

Mirrors the pattern in 0002_sub_admin_permissions: creates Permission
rows anchored to the synthetic (accounts, subadmin) ContentType so super
admin can tick them in the existing permission checkbox UI.
"""

from django.db import migrations


NEW_PERMISSIONS = [
    ('can_use_dpr_facilities',           'Can access the DPR generation module'),
    ('can_approve_govt_official_logins', 'Can approve or reject government official applications'),
    ('can_approve_cbbo_logins',          'Can approve or reject CBBO officer applications'),
    ('can_manage_schemes',               'Can create/edit/delete own schemes (read-only otherwise)'),
    ('can_manage_trainings',             'Can create/edit/delete own trainings (read-only otherwise)'),
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
        ('accounts', '0002_sub_admin_permissions'),
    ]

    operations = [
        migrations.RunPython(create_new_permissions, reverse_code=remove_new_permissions),
    ]
