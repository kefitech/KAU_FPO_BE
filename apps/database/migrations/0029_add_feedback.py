from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('database', '0028_add_gallery_photo'),
    ]

    operations = [
        migrations.CreateModel(
            name='Feedback',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('email', models.EmailField(max_length=254)),
                ('phone', models.CharField(blank=True, default='', max_length=20)),
                ('subject', models.CharField(max_length=300)),
                ('message', models.TextField()),
                ('status', models.CharField(
                    choices=[('unread', 'Unread'), ('read', 'Read'), ('resolved', 'Resolved')],
                    default='unread',
                    max_length=20,
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
