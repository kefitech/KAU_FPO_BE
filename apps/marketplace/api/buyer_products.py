"""
Buyer Product Catalog API
===========================
GET /api/marketplace/buyer/products/

Read-only list of all active, publicly-listed products across every FPO.
Verified-buyer-only (external or FPO-as-buyer).

Query params:
    search      — matches against product name (English or Malayalam)
    commodity   — MasterLookup commodity code, exact match
    price_min   — minimum price_per_unit
    price_max   — maximum price_per_unit
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
    filterable by search/commodity/price range.
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

        price_min = request.query_params.get('price_min')
        if price_min:
            queryset = queryset.filter(price_per_unit__gte=price_min)

        price_max = request.query_params.get('price_max')
        if price_max:
            queryset = queryset.filter(price_per_unit__lte=price_max)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)
        serializer = BuyerProductSerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)