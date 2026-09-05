from django.db import migrations

CBBO_PERMISSIONS = [
    ('can_verify_fpo',        'Can verify or reject FPO applications'),
    ('can_view_assigned_fpos', 'Can view FPOs assigned to their district'),
    ('can_request_documents', 'Can request additional documents from FPO'),
    ('can_submit_reports',    'Can submit capacity building reports'),
    ('can_view_training',     'Can view and manage training records'),
]

def create_cbbo_permissions(apps, schema_editor):
    Permission  = apps.get_model('auth', 'Permission')
    ContentType = apps.get_model('contenttypes', 'ContentType')
    ct, _ = ContentType.objects.get_or_create(app_label='accounts', model='cbbouser')
    for codename, name in CBBO_PERMISSIONS:
        Permission.objects.get_or_create(codename=codename, content_type=ct, defaults={'name': name})

def remove_cbbo_permissions(apps, schema_editor):
    Permission  = apps.get_model('auth', 'Permission')
    ContentType = apps.get_model('contenttypes', 'ContentType')
    try:
        ct = ContentType.objects.get(app_label='accounts', model='cbbouser')
        Permission.objects.filter(content_type=ct, codename__in=[c for c, _ in CBBO_PERMISSIONS]).delete()
    except ContentType.DoesNotExist:
        pass

class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0002_sub_admin_permissions'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]
    operations = [
        migrations.RunPython(create_cbbo_permissions, reverse_code=remove_cbbo_permissions),
    ]