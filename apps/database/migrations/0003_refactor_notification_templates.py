"""
Refactor notification templates — add NotificationTemplateCode parent table.

Drops the old notification_templates table (0 rows in DB) and recreates it
with a FK to the new notification_template_codes table.
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('database', '0002_initial'),
    ]

    operations = [
        # Drop old table (no data, safe to recreate)
        migrations.DeleteModel(
            name='NotificationTemplate',
        ),

        # Create parent/definition table
        migrations.CreateModel(
            name='NotificationTemplateCode',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('code', models.CharField(
                    max_length=50,
                    help_text="Unique event code (e.g. 'fpo_approved', 'password_reset', 'otp_sent')"
                )),
                ('name', models.CharField(
                    max_length=100,
                    help_text='Human-readable name shown in admin'
                )),
                ('channel', models.CharField(
                    choices=[('email', 'Email'), ('sms', 'SMS'), ('in_app', 'In-App Notification'), ('push', 'Push Notification')],
                    max_length=10,
                    help_text='Delivery channel for this definition'
                )),
                ('variables', models.JSONField(
                    blank=True,
                    default=list,
                    help_text="Variable names the template body expects (e.g. ['user_name', 'fpo_name'])"
                )),
                ('description', models.TextField(
                    blank=True,
                    help_text='When this notification is triggered — for admin reference'
                )),
                ('is_active', models.BooleanField(
                    db_index=True,
                    default=True,
                    help_text='Inactive definitions are hidden from the template creation dropdown'
                )),
            ],
            options={
                'verbose_name': 'Notification Template Code',
                'verbose_name_plural': 'Notification Template Codes',
                'db_table': 'notification_template_codes',
                'ordering': ['channel', 'code'],
            },
        ),
        migrations.AlterUniqueTogether(
            name='notificationtemplatecode',
            unique_together={('code', 'channel')},
        ),

        # Recreate content table with FK to parent
        migrations.CreateModel(
            name='NotificationTemplate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('template_code', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='templates',
                    to='database.notificationtemplatecode',
                    help_text='Select the notification event this content belongs to'
                )),
                ('language', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='notification_templates',
                    to='database.language',
                    help_text='Language this content is written in'
                )),
                ('subject', models.CharField(
                    blank=True,
                    max_length=255,
                    help_text='Email subject line (email channel only). Supports {{variables}}.'
                )),
                ('body', models.TextField(
                    help_text='Template body. Use {{variable_name}} for dynamic content.'
                )),
                ('is_active', models.BooleanField(
                    db_index=True,
                    default=True,
                    help_text='Only active templates are used when sending notifications'
                )),
            ],
            options={
                'verbose_name': 'Notification Template',
                'verbose_name_plural': 'Notification Templates',
                'db_table': 'notification_templates',
            },
        ),
        migrations.AlterUniqueTogether(
            name='notificationtemplate',
            unique_together={('template_code', 'language')},
        ),
        migrations.AddIndex(
            model_name='notificationtemplate',
            index=models.Index(fields=['template_code', 'language', 'is_active'], name='notif_tmpl_lookup_idx'),
        ),
        migrations.AddIndex(
            model_name='notificationtemplate',
            index=models.Index(fields=['is_active'], name='notif_tmpl_active_idx'),
        ),
    ]
