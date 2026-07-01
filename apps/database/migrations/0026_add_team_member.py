import uuid as uuid_lib

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):

    dependencies = [
        ('database', '0025_cms_basemodel_and_news_source'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Fix SiteBlock.created_at — was added as nullable, make it non-null with current time as default
        migrations.RunSQL(
            sql="UPDATE database_siteblock SET created_at = NOW() WHERE created_at IS NULL",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AlterField(
            model_name='siteblock',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, db_index=True),
        ),

        # TeamMember model
        migrations.CreateModel(
            name='TeamMember',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(db_index=True, default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('uuid', models.UUIDField(default=uuid_lib.uuid4, editable=False, unique=True, db_index=True)),
                ('name', models.CharField(max_length=200)),
                ('designation', models.CharField(max_length=300)),
                ('photo', models.ImageField(blank=True, null=True, upload_to='cms/team/')),
                ('order', models.PositiveSmallIntegerField(default=0)),
                ('is_active', models.BooleanField(default=True)),
                ('deleted_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                  related_name='teammember_deleted', to=settings.AUTH_USER_MODEL)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                  related_name='teammember_created', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                  related_name='teammember_updated', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['order', 'name'],
            },
        ),
    ]
