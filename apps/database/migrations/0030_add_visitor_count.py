from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('database', '0029_add_feedback'),
    ]

    operations = [
        migrations.CreateModel(
            name='VisitorCount',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('count', models.PositiveBigIntegerField(default=0)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Visitor Counter',
            },
        ),
    ]
