#Arunima S + KAU suggestion #3 grace period
import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.database.models import Product, ProductStock

logger = logging.getLogger(__name__)


# KAU suggestion #3 — product keeps showing in the buyer directory for N
# days after its `available_until` passes, with a "Validity is over —
# contact the buyer to know if it's restocked" banner. Only after this
# grace is the stock row genuinely deleted.
PRODUCT_GRACE_DAYS = 3


def _in_grace_period(stock, today=None) -> bool:
    """True if this stock row is EXPIRED but still within the public-display
    grace window (`available_until + PRODUCT_GRACE_DAYS >= today`)."""
    if not stock or stock.status != ProductStock.Status.EXPIRED:
        return False
    if not stock.available_until:
        return False
    today = today or timezone.now().date()
    return stock.available_until + timedelta(days=PRODUCT_GRACE_DAYS) >= today


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
    Daily — 2-stage lifecycle per KAU suggestion #3:

      Stage A — Day of expiry: ACTIVE stock past its available_until →
        mark status=EXPIRED, notify FPO. The row is kept so buyers still
        see it in the directory with a "Validity is over — contact the
        buyer to know if it's restocked" banner for the next 3 days.

      Stage B — End of grace: EXPIRED stock whose available_until is
        more than PRODUCT_GRACE_DAYS old → genuinely delete the row.
        Product master row is left untouched; FPO can "Add Stock" again.

    Stocks with no available_until (open-ended) never auto-expire.
    """
    today = timezone.now().date()

    # ── Stage A: ACTIVE → EXPIRED (keep row, send FPO notice) ───────────
    active_past_due = ProductStock.objects.filter(
        status=ProductStock.Status.ACTIVE,
        available_until__lt=today,
    ).select_related('product', 'product__fpo')

    expired_count = 0
    for stock in active_past_due:
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
        stock.status = ProductStock.Status.EXPIRED
        stock.save(update_fields=['status', 'updated_at'])
        expired_count += 1

    # ── Stage B: EXPIRED past grace → hard-delete ──────────────────────
    cutoff = today - timedelta(days=PRODUCT_GRACE_DAYS)
    stale_expired = ProductStock.objects.filter(
        status=ProductStock.Status.EXPIRED,
        available_until__lt=cutoff,
    ).select_related('product')

    deleted_count = stale_expired.count()
    for stock in stale_expired:
        stock.delete()

    logger.info(
        'expire_products: %d marked EXPIRED, %d hard-deleted after %d-day grace',
        expired_count, deleted_count, PRODUCT_GRACE_DAYS,
    )
    return {'expired': expired_count, 'deleted': deleted_count}


@shared_task
def run_buyer_seller_matching():
    """Daily — run matching for every ACTIVE stock batch."""
    from apps.marketplace.services import run_matching

    for stock in ProductStock.objects.filter(status=ProductStock.Status.ACTIVE).select_related('product'):
        run_matching(stock)


# Wire later — waiting for AGMARKNET API access
# @shared_task
# def refresh_market_prices():
