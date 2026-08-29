#Arunima S  
from celery import shared_task

@shared_task
def expire_products():
    """Daily — mark products past available_until as expired."""
    from django.utils import timezone
    from apps.database.models import Product

    Product.objects.filter(
        status=Product.Status.ACTIVE,
        available_until__lt=timezone.now().date()
    ).update(status=Product.Status.EXPIRED)


@shared_task
def run_buyer_seller_matching():
    """Daily — run matching for all newly active products."""
    from apps.database.models import Product
    from apps.marketplace.services import run_matching

    for product in Product.objects.filter(status=Product.Status.ACTIVE):
        run_matching(product)


# Wire later — waiting for AGMARKNET API access
# @shared_task
# def refresh_market_prices():
#     pass