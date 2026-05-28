"""
Data migration: create sub-admin configurable permissions in Django's permission system.

These permissions are assigned per sub-admin user by super admin via API.
Add new entries to SUB_ADMIN_PERMISSIONS in constants.py when new features are built.
"""

from django.db import migrations


SUB_ADMIN_PERMISSIONS = [
    ('can_approve_fpo',      'Can approve or reject FPO applications'),
    ('can_view_all_fpos',    'Can view all FPO profiles'),
    ('can_request_info',     'Can request additional info from FPO'),
    ('can_verify_documents', 'Can mark FPO documents as verified'),
    ('can_generate_reports', 'Can export FPO summary reports'),
]


def create_sub_admin_permissions(apps, schema_editor):
    Permission    = apps.get_model('auth', 'Permission')
    ContentType   = apps.get_model('contenttypes', 'ContentType')

    # Use the accounts app's content type as the anchor for these permissions
    ct, _ = ContentType.objects.get_or_create(app_label='accounts', model='subadmin')

    for codename, name in SUB_ADMIN_PERMISSIONS:
        Permission.objects.get_or_create(
            codename=codename,
            content_type=ct,
            defaults={'name': name},
        )


def remove_sub_admin_permissions(apps, schema_editor):
    Permission  = apps.get_model('auth', 'Permission')
    ContentType = apps.get_model('contenttypes', 'ContentType')

    try:
        ct = ContentType.objects.get(app_label='accounts', model='subadmin')
        Permission.objects.filter(
            content_type=ct,
            codename__in=[c for c, _ in SUB_ADMIN_PERMISSIONS],
        ).delete()
    except ContentType.DoesNotExist:
        pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial_roles'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.RunPython(
            create_sub_admin_permissions,
            reverse_code=remove_sub_admin_permissions,
        ),
    ]
