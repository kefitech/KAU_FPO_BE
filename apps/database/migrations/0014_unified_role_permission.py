"""
Migration 0014 — Unified Role Permission Matrix

Changes:
1. Data: create 'primary' and 'secondary' Django Groups
2. Data: clear old MasterLookup-based FPOMemberPermission rows (incompatible FKs)
3. Rename FPOMemberPermission → RoleActionPermission (table rename)
4. Alter RoleActionPermission.role: core.MasterLookup → auth.Group
5. Add FPOAction.menu_item FK → MenuItem
6. Alter FPOUserMembership.role: core.MasterLookup → auth.Group
7. Create RolePageAccess model (Group × MenuItem)
"""

import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def create_fpo_member_groups(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    for name in ('primary', 'secondary'):
        Group.objects.get_or_create(name=name)


def remove_fpo_member_groups(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.filter(name__in=('primary', 'secondary')).delete()


def clear_old_role_data(apps, schema_editor):
    """
    RoleActionPermission rows reference MasterLookup IDs incompatible with
    auth_group IDs. Clear them so the FK alter can proceed cleanly.
    FPOUserMembership.role is nullable — set to NULL.
    """
    FPOMemberPermission = apps.get_model('database', 'FPOMemberPermission')
    FPOUserMembership   = apps.get_model('database', 'FPOUserMembership')
    FPOMemberPermission.objects.all().delete()
    FPOUserMembership.objects.update(role_id=None)


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '__first__'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('database', '0013_add_phone_verified_external_api_settings'),
    ]

    operations = [
        # ── 1. Create primary / secondary Groups ─────────────────────────────
        migrations.RunPython(
            create_fpo_member_groups,
            reverse_code=remove_fpo_member_groups,
        ),

        # ── 2. Clear incompatible FK data ─────────────────────────────────────
        migrations.RunPython(
            clear_old_role_data,
            reverse_code=migrations.RunPython.noop,
        ),

        # ── 3. Rename FPOMemberPermission → RoleActionPermission ──────────────
        migrations.RenameModel(
            old_name='FPOMemberPermission',
            new_name='RoleActionPermission',
        ),

        # ── 4. Alter RoleActionPermission.role → auth.Group ───────────────────
        migrations.AlterUniqueTogether(
            name='roleactionpermission',
            unique_together=set(),
        ),
        migrations.AlterField(
            model_name='roleactionpermission',
            name='role',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='role_action_permissions',
                to='auth.group',
            ),
        ),
        migrations.AlterUniqueTogether(
            name='roleactionpermission',
            unique_together={('role', 'action')},
        ),

        # ── 5. Add menu_item FK to FPOAction ──────────────────────────────────
        migrations.AddField(
            model_name='fpoaction',
            name='menu_item',
            field=models.ForeignKey(
                blank=True,
                help_text='Page this action belongs to — used to group actions in the permission matrix',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='actions',
                to='database.menuitem',
            ),
        ),

        # ── 6. Alter FPOUserMembership.role → auth.Group ─────────────────────
        migrations.AlterField(
            model_name='fpousermembership',
            name='role',
            field=models.ForeignKey(
                blank=True,
                help_text='FPO-internal role — Django Group (primary, secondary, etc.)',
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='fpo_memberships',
                to='auth.group',
            ),
        ),

        # ── 7. Create RolePageAccess ──────────────────────────────────────────
        migrations.CreateModel(
            name='RolePageAccess',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                (
                    'created_at',
                    models.DateTimeField(
                        auto_now_add=True,
                        db_index=True,
                        help_text='Timestamp when record was created',
                    ),
                ),
                (
                    'updated_at',
                    models.DateTimeField(
                        auto_now=True,
                        help_text='Timestamp when record was last updated',
                    ),
                ),
                (
                    'is_deleted',
                    models.BooleanField(
                        db_index=True,
                        default=False,
                        help_text='Soft delete flag. True means record is deleted.',
                    ),
                ),
                (
                    'deleted_at',
                    models.DateTimeField(
                        blank=True,
                        help_text='Timestamp when record was soft deleted',
                        null=True,
                    ),
                ),
                (
                    'uuid',
                    models.UUIDField(
                        db_index=True,
                        default=uuid.uuid4,
                        editable=False,
                        help_text='Public UUID identifier (use this in APIs instead of PK)',
                        unique=True,
                    ),
                ),
                ('is_allowed', models.BooleanField(default=False)),
                (
                    'created_by',
                    models.ForeignKey(
                        blank=True,
                        help_text='User who created this record',
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='%(class)s_created',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    'deleted_by',
                    models.ForeignKey(
                        blank=True,
                        help_text='User who deleted this record',
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='%(class)s_deleted',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    'menu_item',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='role_access',
                        to='database.menuitem',
                    ),
                ),
                (
                    'role',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='page_access',
                        to='auth.group',
                    ),
                ),
                (
                    'updated_by',
                    models.ForeignKey(
                        blank=True,
                        help_text='User who last updated this record',
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='%(class)s_updated',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                'ordering': ['role', 'menu_item'],
                'unique_together': {('role', 'menu_item')},
            },
        ),
    ]
