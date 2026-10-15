# Hand-written for dev-aravind pick 0eca4e2 (batch numbers + product-level
# is_active switch), which shipped without a migration. Existing stock rows
# need unique backfilled batch numbers, so this is a three-step add →
# backfill → tighten migration rather than an auto-generated one.
from django.db import migrations, models


def backfill_batch_numbers(apps, schema_editor):
    Product = apps.get_model('database', 'Product')
    ProductStock = apps.get_model('database', 'ProductStock')
    for product in Product.objects.all():
        counter = 0
        for stock in product.stocks.order_by('created_at', 'id'):
            counter += 1
            ProductStock.objects.filter(pk=stock.pk).update(
                batch_number=f'P{product.pk}-B{counter}'
            )
        if counter:
            Product.objects.filter(pk=product.pk).update(batch_counter=counter)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('database', '0133_expertbooking_user_inquiry_submitted_by_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='is_active',
            field=models.BooleanField(
                default=True,
                help_text='Product-level switch. When off, none of its batches are shown to '
                          'buyers or on the public Market Hub — the batches keep their own '
                          'status, so switching the product back on restores them as they were.',
            ),
        ),
        migrations.AddField(
            model_name='product',
            name='batch_counter',
            field=models.PositiveIntegerField(
                default=0, editable=False,
                help_text='Last batch sequence issued for this product (see ProductStock.batch_number). '
                          'Only ever increases, so a number is never reused after a batch is deleted.',
            ),
        ),
        migrations.AddField(
            model_name='productstock',
            name='batch_number',
            field=models.CharField(max_length=30, null=True, editable=False),
        ),
        migrations.RunPython(backfill_batch_numbers, noop),
        migrations.AlterField(
            model_name='productstock',
            name='batch_number',
            field=models.CharField(
                max_length=30, unique=True, editable=False,
                help_text='Auto-generated on create — "P<product id>-B<n>", n counting up per '
                          'product (e.g. P34-B2). Shown on cards and inquiries so the FPO '
                          'knows which batch a buyer asked about.',
            ),
        ),
    ]
