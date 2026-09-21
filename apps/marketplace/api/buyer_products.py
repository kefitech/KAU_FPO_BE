"""
Buyer Product Catalog API
===========================
GET /api/marketplace/buyer/products/

Read-only list of all active, publicly-listed products across every FPO.
Verified-buyer-only (external or FPO-as-buyer).

Query params:
    search      — matches against product name (English or Malayalam)
    commodity   — MasterLookup commodity code, exact match
    fpo         — FPO id, exact match — used for "view all products from
                  this FPO" (still excludes buyer's own FPO if buyer.fpo_id
                  matches, same as the base queryset exclusion below)
    price_min   — minimum price_per_unit
    price_max   — maximum price_per_unit
    date_from   — availability window start (requires date_until to also be
                  present; overlap filter — see below)
    date_until  — availability window end (requires date_from to also be
                  present)
    page        — page number (StandardPagination)
    page_size   — items per page (StandardPagination)
"""
from django.db.models import Q
from rest_framework import status as http_status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.utils.pagination import StandardPagination
from apps.core.utils.responses import StandardResponse
from apps.database.models import Product
from apps.marketplace.serializers import BuyerProductSerializer
from apps.marketplace.services import _get_buyer_row


class BuyerProductListView(APIView):
    """
    GET /api/marketplace/buyer/products/

    Returns 403 if the requesting user isn't a verified buyer.
    Otherwise returns paginated, active + public products from all FPOs,
    filterable by search/commodity/price range/date range.
    """
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination

    def get(self, request):
        buyer = _get_buyer_row(request.user)
        if buyer is None or buyer.status != 'verified':
            return StandardResponse.error(
                message='Only verified buyers can browse the product catalog',
                status_code=http_status.HTTP_403_FORBIDDEN,
            )

        queryset = Product.objects.filter(
            status=Product.Status.ACTIVE,
            is_public=True,
            is_deleted=False,
        ).select_related('commodity', 'fpo').order_by('-created_at')

        # FPO-as-buyer shouldn't see its own products in this catalog —
        # only external buyers or genuinely "other" FPOs' listings.
        if buyer.fpo_id:
            queryset = queryset.exclude(fpo_id=buyer.fpo_id)

        search = request.query_params.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(name__en__icontains=search) | Q(name__ml__icontains=search)
            )

        commodity = request.query_params.get('commodity', '').strip()
        if commodity:
            queryset = queryset.filter(commodity__code=commodity)

        fpo_id = request.query_params.get('fpo')
        if fpo_id:
            queryset = queryset.filter(fpo_id=fpo_id)

        price_min = request.query_params.get('price_min')
        if price_min:
            queryset = queryset.filter(price_per_unit__gte=price_min)

        price_max = request.query_params.get('price_max')
        if price_max:
            queryset = queryset.filter(price_per_unit__lte=price_max)

        # Date range filter — overlap logic. A product's availability window
        # (available_from -> available_until) overlaps the requested range if:
        #   product.available_from <= requested_until
        #   AND (product.available_until IS NULL OR product.available_until >= requested_from)
        # Both date_from and date_until must be present together — if only
        # one is sent, the filter is skipped entirely (matches the frontend's
        # "pick both dates before applying" rule).
        date_from = request.query_params.get('date_from', '').strip()
        date_until = request.query_params.get('date_until', '').strip()
        if date_from and date_until:
            from django.db.models import Q as DateQ
            queryset = queryset.filter(
                available_from__lte=date_until,
            ).filter(
                DateQ(available_until__isnull=True) | DateQ(available_until__gte=date_from)
            )

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)
        serializer = BuyerProductSerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)

class BuyerRecommendedProductsView(APIView):
    """
    GET /api/marketplace/buyer/products/recommended/

    Returns a fixed, non-paginated top-N list of active + public products
    whose commodity matches one of the buyer's `commodities_interested`
    (set on their BuyerDirectory profile via the Buyer Dashboard "Complete
    your profile" form). Independent of the search/filter params used by
    BuyerProductListView — this section is always the buyer's own interests,
    not whatever they're currently filtering the main catalog by.

    Returns an empty list (not an error) if the buyer hasn't set any
    commodities_interested yet, so the frontend can simply hide the section.
    """
    permission_classes = [IsAuthenticated]
    RECOMMENDED_LIMIT = 8

    def get(self, request):
        buyer = _get_buyer_row(request.user)
        if buyer is None or buyer.status != 'verified':
            return StandardResponse.error(
                message='Only verified buyers can browse the product catalog',
                status_code=http_status.HTTP_403_FORBIDDEN,
            )

        interested = buyer.commodities_interested or []
        if not interested:
            return StandardResponse.success(data=[], message='No commodity interests set')

        queryset = Product.objects.filter(
            status=Product.Status.ACTIVE,
            is_public=True,
            is_deleted=False,
            commodity__code__in=interested,
        ).select_related('commodity', 'fpo').order_by('-created_at')

        if buyer.fpo_id:
            queryset = queryset.exclude(fpo_id=buyer.fpo_id)

        serializer = BuyerProductSerializer(queryset[: self.RECOMMENDED_LIMIT], many=True)
        return StandardResponse.success(data=serializer.data, message='Recommended products retrieved')