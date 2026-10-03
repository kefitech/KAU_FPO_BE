"""
Buyer Dashboard API
====================

ARUNIMA S
==============
GET /api/marketplace/buyer/dashboard/

Returns the buyer's own profile summary plus a `stats` block for the
dashboard metrics. Works for both buyer types:
- External buyer (BuyerDirectory.user is set)
- FPO-as-buyer (BuyerDirectory.fpo is set, linked via request.user.fpo)

The profile fields are also used by the buyer Products page (to default its
commodity filter), so `stats` is purely additive.
"""
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta
from django.db.models import Count, Max, Min
from django.db.models.functions import TruncMonth
from django.utils import timezone
from rest_framework import status as http_status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.models.generic import MasterLookup
from apps.core.utils.responses import StandardResponse
from apps.database.models import Inquiry, ProductStock
from apps.marketplace.services import _get_buyer_row, buyer_catalogue_queryset

TREND_MONTHS = 6
RECENT_INQUIRIES = 5
EXPIRING_SOON_DAYS = 7


def _commodity_names(codes, lang):
    # Read MasterLookup directly so a commodity an admin has since
    # deactivated still shows its name instead of the raw code.
    lookups = {m.code: m for m in MasterLookup.objects.filter(category='commodity', code__in=codes)}
    return {code: (lookups[code].get_name(lang) if code in lookups else code) for code in codes}


def _inquiry_trend(inquiries):
    start = date.today().replace(day=1) - relativedelta(months=TREND_MONTHS - 1)
    counts = {
        row['month'].strftime('%Y-%m'): row['count']
        for row in (
            inquiries.filter(created_at__date__gte=start)
            .annotate(month=TruncMonth('created_at'))
            .values('month')
            .annotate(count=Count('id'))
        )
    }
    months = [start + relativedelta(months=i) for i in range(TREND_MONTHS)]
    return [{'month': m.strftime('%Y-%m'), 'count': counts.get(m.strftime('%Y-%m'), 0)} for m in months]


def _supply_by_commodity(mine, interested, names):
    """Listings / FPOs / price range per interested commodity (zero-filled, profile order)."""
    totals = {
        row['product__commodity__code']: row
        for row in mine.values('product__commodity__code').annotate(
            listings=Count('id'), fpos=Count('product__fpo', distinct=True),
        )
    }
    # Prices only compare within a unit (kg vs quintal), so group by unit too.
    prices = {}
    for row in mine.values('product__commodity__code', 'unit').annotate(
        min_price=Min('price_per_unit'), max_price=Max('price_per_unit'),
    ).order_by('unit'):
        prices.setdefault(row['product__commodity__code'], []).append(
            {'unit': row['unit'], 'min': row['min_price'], 'max': row['max_price']}
        )
    return [
        {
            'code': code,
            'name': names.get(code, code),
            'listings': totals.get(code, {}).get('listings', 0),
            'fpos': totals.get(code, {}).get('fpos', 0),
            'prices': prices.get(code, []),
        }
        for code in interested
    ]


def _recent_inquiries(inquiries, lang):
    rows = inquiries.select_related('product__fpo', 'product__commodity').order_by('-created_at')[:RECENT_INQUIRIES]
    return [
        {
            'id': inq.id,
            'product_name': inq.product.name,
            'commodity_name': inq.product.commodity.get_name(lang) if inq.product.commodity_id else '',
            'fpo_name': inq.product.fpo.name,
            'quantity_requested': inq.quantity_requested,
            'status': inq.status,
            'created_at': inq.created_at,
            'updated_at': inq.updated_at,
        }
        for inq in rows
    ]


def build_buyer_stats(buyer, lang='en'):
    """Dashboard metrics for one buyer — catalogue supply + their own inquiries."""
    now = timezone.now()
    today = now.date()
    interested = list(buyer.commodities_interested or [])

    catalogue = buyer_catalogue_queryset(buyer)
    mine = catalogue.filter(product__commodity__code__in=interested)
    inquiries = Inquiry.objects.filter(buyer=buyer, is_deleted=False)

    by_status = {s: 0 for s in Inquiry.Status.values}
    for row in inquiries.values('status').annotate(count=Count('id')):
        by_status[row['status']] = row['count']
    total = sum(by_status.values())
    responded = by_status[Inquiry.Status.CONTACTED] + by_status[Inquiry.Status.RESOLVED]

    return {
        'cards': {
            'products_available': catalogue.count(),
            'fpos_selling': catalogue.values('product__fpo_id').distinct().count(),
            'matching_interests': mine.count(),
            'new_this_week': mine.filter(created_at__gte=now - timedelta(days=7)).count(),
            'inquiries_total': total,
            'inquiries_pending': by_status[Inquiry.Status.PENDING],
            'inquiries_responded': responded,
            'response_rate': round(responded * 100 / total) if total else None,
            'fpos_contacted': inquiries.values('product__fpo_id').distinct().count(),
            'expiring_soon': mine.filter(
                status=ProductStock.Status.ACTIVE,
                available_until__range=(today, today + timedelta(days=EXPIRING_SOON_DAYS)),
            ).count(),
        },
        'inquiry_status': by_status,
        'inquiry_trend': _inquiry_trend(inquiries),
        'supply_by_commodity': _supply_by_commodity(mine, interested, _commodity_names(interested, lang)),
        'recent_inquiries': _recent_inquiries(inquiries, lang),
    }


class BuyerDashboardView(APIView):
    """
    GET /api/marketplace/buyer/dashboard/

    Returns 404 if the user has no BuyerDirectory row. Frontend uses the
    returned `status` to decide where to redirect (pending → waiting page,
    rejected → rejected page).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        buyer = _get_buyer_row(request.user)

        if buyer is None:
            return StandardResponse.error(
                message='No buyer profile found for this account',
                status_code=http_status.HTTP_404_NOT_FOUND,
            )

        buyer_type = 'fpo' if buyer.fpo_id else 'external'

        data = {
            'id': buyer.id,
            'name': buyer.name,
            'organisation': buyer.organisation,
            'contact_email': buyer.contact_email,
            'contact_phone': buyer.contact_phone,
            'location': buyer.location,
            'commodities_interested': buyer.commodities_interested,
            'status': buyer.status,
            'buyer_type': buyer_type,
            'created_at': buyer.created_at,
            'stats': build_buyer_stats(buyer, getattr(request, 'language', 'en')),
        }

        return StandardResponse.success(
            data=data,
            message='Buyer dashboard retrieved successfully',
        )
