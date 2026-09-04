"""
Arunima S

Market Price API — e-NAM / AGMARKNET Price Data
==================================================
FPO base path:   /api/marketplace/prices/
Admin base path: /api/admin/prices/
"""

from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, viewsets
from rest_framework.views import APIView

from apps.core.permissions.rbac import IsAdmin, IsAuthenticated
from apps.core.services.translation import t
from apps.core.utils.pagination import StandardPagination
from apps.core.utils.responses import StandardResponse
from apps.database.models import MarketPrice
from apps.marketplace.serializers import MarketPriceSerializer
from apps.marketplace.services import compute_opportunities


def _filtered_queryset(request):
    qs = MarketPrice.objects.filter(is_deleted=False).order_by('-date')
    commodity = request.query_params.get('commodity')
    date = request.query_params.get('date')
    if commodity:
        qs = qs.filter(commodity__code=commodity)
    if date:
        qs = qs.filter(date=date)
    return qs


@extend_schema_view(
    list=extend_schema(tags=['Marketplace - Prices']),
)
class MarketPriceViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """GET /api/marketplace/prices/ — FPO view, filter by commodity, date."""

    serializer_class = MarketPriceSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination

    def get_queryset(self):
        return _filtered_queryset(self.request)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page if page is not None else queryset, many=True)
        lang = getattr(request, 'language', 'en')
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return StandardResponse.success(
            data=serializer.data,
            message=t('marketplace.prices_retrieved', lang),
        )


@extend_schema_view(
    list=extend_schema(tags=['Marketplace - Prices']),
    create=extend_schema(tags=['Marketplace - Prices']),
)
class AdminMarketPriceViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    """
    Admin — GET /api/admin/prices/ — full list.
    POST /api/admin/prices/ — manually seed price data (until AGMARKNET/e-NAM
    pull is wired — see ARUNIMA.md "What NOT to Build Yet").
    """

    serializer_class = MarketPriceSerializer
    permission_classes = [IsAuthenticated, IsAdmin]
    pagination_class = StandardPagination

    def get_queryset(self):
        return _filtered_queryset(self.request)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page if page is not None else queryset, many=True)
        lang = getattr(request, 'language', 'en')
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return StandardResponse.success(
            data=serializer.data,
            message=t('marketplace.prices_retrieved', lang),
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        lang = getattr(request, 'language', 'en')
        return StandardResponse.created(
            data=serializer.data,
            message=t('marketplace.price_seeded', lang),
        )


@extend_schema(tags=['Marketplace - Prices'])
class MarketOpportunitiesView(APIView):
    """
    GET /api/marketplace/opportunities/ — market demand signals by commodity.

    Not in ARUNIMA.md's original endpoint list; added on request. Open to
    any authenticated user (FPO, admin, etc.) — matches MarketPriceViewSet's
    access level, since it's read-only aggregate data, not tied to one FPO.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        lang = getattr(request, 'language', 'en')
        opportunities = compute_opportunities()
        return StandardResponse.success(
            data=opportunities,
            message=t('marketplace.opportunities_retrieved', lang),
        )