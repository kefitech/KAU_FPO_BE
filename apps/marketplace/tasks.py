#Arunima S
import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.database.models import Product, ProductStock

logger = logging.getLogger(__name__)


def _notify_fpo(product, code, context):
    """
    Send a notification to the FPO's primary user on both channels — in-app
    inbox and email — matching the pattern used elsewhere in apps/marketplace
    (see apps/marketplace/api/inquiries.py). Each channel is sent
    independently so one channel failing doesn't block the other, and a
    notification failure never blocks the calling task (caller decides
    whether to still proceed, e.g. still delete the expired stock row).
    """
    from apps.notifications.services import send_notification

    primary_user = getattr(product.fpo, 'primary_user', None)
    if not primary_user:
        return

    for channel in ('in_app', 'email'):
        try:
            send_notification(
                user=primary_user,
                code=code,
                channel=channel,
                context=context,
            )
        except Exception:
            logger.exception(
                "Failed to send '%s' notification (%s channel) for product %s",
                code, channel, product.id,
            )


@shared_task
def send_expiry_reminders():
    """
    Daily — for every ACTIVE stock batch whose available_until is exactly
    3 days away, notify the FPO (inbox + email) so they can act before it
    expires. expiry_reminder_sent guards against re-sending on subsequent
    days once a reminder has gone out for a given batch.
    """
    reminder_date = timezone.now().date() + timedelta(days=3)

    stocks = ProductStock.objects.filter(
        status=ProductStock.Status.ACTIVE,
        available_until=reminder_date,
        expiry_reminder_sent=False,
    ).select_related('product', 'product__fpo')

    for stock in stocks:
        product = stock.product
        _notify_fpo(
            product,
            code='product_stock_expiring_soon',
            context={
                'fpo_name': product.fpo.name,
                'product_name': product.name.get('en', '') if product.name else '',
                'quantity': str(stock.quantity),
                'unit': stock.unit,
                'available_until': str(stock.available_until),
            },
        )
        stock.expiry_reminder_sent = True
        stock.save(update_fields=['expiry_reminder_sent', 'updated_at'])


@shared_task
def expire_products():
    """
    Daily — for every ACTIVE stock batch past its available_until date:
      1. Notify the FPO (inbox + email) that the batch has expired.
      2. Genuinely delete the ProductStock row — per the confirmed product
         decision, expired stock is removed outright, not soft-deleted or
         just flagged. The Product (master) row is left untouched, so the
         FPO can "Add Stock" again against the same product later.
    The notification is sent BEFORE deletion, since the row's own data
    (quantity, unit, dates) is needed to build the notification context.
    A batch with no available_until (open-ended) never auto-expires here,
    same as before this rewrite.
    """
    today = timezone.now().date()

    stocks = ProductStock.objects.filter(
        status=ProductStock.Status.ACTIVE,
        available_until__lt=today,
    ).select_related('product', 'product__fpo')

    for stock in stocks:
        product = stock.product
        _notify_fpo(
            product,
            code='product_stock_expired',
            context={
                'fpo_name': product.fpo.name,
                'product_name': product.name.get('en', '') if product.name else '',
                'quantity': str(stock.quantity),
                'unit': stock.unit,
                'available_until': str(stock.available_until),
            },
        )
        stock.delete()


@shared_task
def run_buyer_seller_matching():
    """Daily — run matching for every product with a currently active stock batch."""
    from apps.marketplace.services import run_matching

    for product in Product.objects.filter(stock__status=ProductStock.Status.ACTIVE):
        run_matching(product)


# Wire later — waiting for AGMARKNET API access
# @shared_task
# def refresh_market_prices():
