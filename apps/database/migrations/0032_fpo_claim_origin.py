from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('database', '0031_alter_announcement_created_at_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='fpo',
            name='claimed_from_fpo',
            field=models.ForeignKey(
                blank=True,
                help_text='If this FPO was created via an ownership claim, points to the original FPO',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='resulted_claims',
                to='database.fpo',
            ),
        ),
        migrations.AddField(
            model_name='fpo',
            name='origin_claim_id',
            field=models.IntegerField(
                blank=True,
                help_text='FPOOwnershipClaim ID that created this FPO',
                null=True,
            ),
        ),
    ]
