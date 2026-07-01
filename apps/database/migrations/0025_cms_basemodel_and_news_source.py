"""
Migrate CMS models to BaseModel and add NewsSource model.

Steps:
1. Add all new BaseModel fields (nullable where needed)
2. Populate uuid for existing rows
3. Make uuid unique/not-null
"""

import uuid as uuid_lib

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def populate_uuids(apps, schema_editor):
    for model_name in ('SiteBlock', 'Announcement', 'FAQ', 'QuickLink'):
        Model = apps.get_model('database', model_name)
        for obj in Model.objects.all():
            obj.uuid = uuid_lib.uuid4()
            obj.save(update_fields=['uuid'])


class Migration(migrations.Migration):

    dependencies = [
        ('database', '0024_quicklink_logo_nullable'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── SiteBlock ────────────────────────────────────────────────────────
        migrations.AddField(
            model_name='siteblock',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name='siteblock',
            name='is_deleted',
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name='siteblock',
            name='deleted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='siteblock',
            name='deleted_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name='siteblock_deleted', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='siteblock',
            name='created_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name='siteblock_created', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='siteblock',
            name='updated_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name='siteblock_updated', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='siteblock',
            name='uuid',
            field=models.UUIDField(null=True, editable=False),
        ),

        # ── Announcement ─────────────────────────────────────────────────────
        migrations.AddField(
            model_name='announcement',
            name='is_deleted',
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name='announcement',
            name='deleted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='announcement',
            name='deleted_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name='announcement_deleted', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='announcement',
            name='created_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name='announcement_created', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='announcement',
            name='updated_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name='announcement_updated', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='announcement',
            name='uuid',
            field=models.UUIDField(null=True, editable=False),
        ),

        # ── FAQ ──────────────────────────────────────────────────────────────
        migrations.AddField(
            model_name='faq',
            name='is_deleted',
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name='faq',
            name='deleted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='faq',
            name='deleted_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name='faq_deleted', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='faq',
            name='created_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name='faq_created', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='faq',
            name='updated_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name='faq_updated', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='faq',
            name='uuid',
            field=models.UUIDField(null=True, editable=False),
        ),

        # ── QuickLink ────────────────────────────────────────────────────────
        migrations.AddField(
            model_name='quicklink',
            name='is_deleted',
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name='quicklink',
            name='deleted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='quicklink',
            name='deleted_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name='quicklink_deleted', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='quicklink',
            name='created_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name='quicklink_created', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='quicklink',
            name='updated_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name='quicklink_updated', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='quicklink',
            name='uuid',
            field=models.UUIDField(null=True, editable=False),
        ),

        # ── Populate UUIDs for existing rows ─────────────────────────────────
        migrations.RunPython(populate_uuids, migrations.RunPython.noop),

        # ── Make uuid unique + not null ───────────────────────────────────────
        migrations.AlterField(
            model_name='siteblock',
            name='uuid',
            field=models.UUIDField(default=uuid_lib.uuid4, editable=False, unique=True, db_index=True),
        ),
        migrations.AlterField(
            model_name='announcement',
            name='uuid',
            field=models.UUIDField(default=uuid_lib.uuid4, editable=False, unique=True, db_index=True),
        ),
        migrations.AlterField(
            model_name='faq',
            name='uuid',
            field=models.UUIDField(default=uuid_lib.uuid4, editable=False, unique=True, db_index=True),
        ),
        migrations.AlterField(
            model_name='quicklink',
            name='uuid',
            field=models.UUIDField(default=uuid_lib.uuid4, editable=False, unique=True, db_index=True),
        ),

        # ── Also remove duplicate created_at/updated_at from Announcement/FAQ/QuickLink ──
        # (BaseModel provides these via TimeStampedModel — they were already there, no change needed)

        # ── NewsSource model ─────────────────────────────────────────────────
        migrations.CreateModel(
            name='NewsSource',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(db_index=True, default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('uuid', models.UUIDField(default=uuid_lib.uuid4, editable=False, unique=True, db_index=True)),
                ('name', models.CharField(max_length=200)),
                ('url', models.URLField(max_length=500)),
                ('logo', models.ImageField(blank=True, null=True, upload_to='cms/news-sources/')),
                ('category', models.CharField(choices=[('newspaper', 'Newspaper'), ('magazine', 'Magazine')],
                                              default='newspaper', max_length=20)),
                ('is_active', models.BooleanField(default=True)),
                ('deleted_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                  related_name='newssource_deleted', to=settings.AUTH_USER_MODEL)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                  related_name='newssource_created', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                  related_name='newssource_updated', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['category', 'name'],
            },
        ),
    ]
