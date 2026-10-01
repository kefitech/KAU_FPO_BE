"""
Seed default values for SubAdminConfig — KAU suggestion #1.

Idempotent: uses update_or_create so re-running does nothing.
Per-district cap overrides are NOT seeded; only the global default.
"""

from django.db import migrations


DEFAULTS = [
    ('global_cap',           30, 'Default maximum sub-admins per district (overridable per-district).'),
    ('scheme_expiry_days',    5, 'Days past deadline before a scheme is auto-hidden from FPO portal.'),
    ('training_expiry_days',  5, 'Days past deadline before a training is auto-hidden from FPO portal.'),
]


def seed_defaults(apps, schema_editor):
    SubAdminConfig = apps.get_model('database', 'SubAdminConfig')
    for key, value, description in DEFAULTS:
        SubAdminConfig.objects.update_or_create(
            key=key,
            defaults={'value': value, 'description': description},
        )


def unseed_defaults(apps, schema_editor):
    SubAdminConfig = apps.get_model('database', 'SubAdminConfig')
    SubAdminConfig.objects.filter(key__in=[k for k, _, _ in DEFAULTS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('database', '0115_subadminconfig_subadmindistricttransfer_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_defaults, reverse_code=unseed_defaults),
    ]
