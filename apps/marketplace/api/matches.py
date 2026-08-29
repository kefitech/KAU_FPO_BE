"""
ArunimaS 

Buyer-Seller Match API — Farmer Connect
=========================================
FPO base path:   /api/marketplace/matches/
Admin base path: /api/admin/matches/
"""

from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, viewsets
from rest_framework.decorators import action

from apps.core.permissions.rbac import IsAdmin, IsAuthenticated, IsFPOManager
from apps.core.services.translation import t
from apps.core.utils.pagination import StandardPagination
from apps.core.utils.responses import StandardResponse
from apps.database.models import BuyerSellerMatch
from apps.marketplace.serializers import BuyerSellerMatchSerializer


@extend_schema_view(
    list=extend_schema(tags=['Marketplace - Matches']),
)
class BuyerSellerMatchViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    FPO — GET /api/marketplace/matches/ — sees suggested matches for their products.
    POST /api/marketplace/matches/{id}/accept/
    POST /api/marketplace/matches/{id}/reject/
    """

    serializer_class = BuyerSellerMatchSerializer
    permission_classes = [IsAuthenticated, IsFPOManager]
    pagination_class = StandardPagination

    def get_queryset(self):
        return (
            BuyerSellerMatch.objects.filter(product__fpo=self.request.user.fpo, is_deleted=False)
            .select_related('product', 'buyer')
            .order_by('-suggested_at')
        )

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page if page is not None else queryset, many=True)
        lang = getattr(request, 'language', 'en')
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return StandardResponse.success(
            data=serializer.data,
            message=t('marketplace.matches_retrieved', lang),
        )

    def _lang(self):
        return getattr(self.request, 'language', 'en')

    @extend_schema(tags=['Marketplace - Matches'])
    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        match = self.get_object()
        if match.status != BuyerSellerMatch.Status.SUGGESTED:
            return StandardResponse.error(t('marketplace.match_not_actionable', self._lang()), status_code=400)
        match.status = BuyerSellerMatch.Status.ACCEPTED
        match.save(update_fields=['status', 'updated_at'])
        return StandardResponse.success(
            data=BuyerSellerMatchSerializer(match).data,
            message=t('marketplace.match_accepted', self._lang()),
        )

    @extend_schema(tags=['Marketplace - Matches'])
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        match = self.get_object()
        if match.status != BuyerSellerMatch.Status.SUGGESTED:
            return StandardResponse.error(t('marketplace.match_not_actionable', self._lang()), status_code=400)
        match.status = BuyerSellerMatch.Status.REJECTED
        match.save(update_fields=['status', 'updated_at'])
        return StandardResponse.success(
            data=BuyerSellerMatchSerializer(match).data,
            message=t('marketplace.match_rejected', self._lang()),
        )


@extend_schema_view(
    list=extend_schema(tags=['Marketplace - Matches']),
)
class AdminMatchViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Admin — GET /api/admin/matches/ — sees all matches across all FPOs."""

    serializer_class = BuyerSellerMatchSerializer
    permission_classes = [IsAuthenticated, IsAdmin]
    pagination_class = StandardPagination

    def get_queryset(self):
        return BuyerSellerMatch.objects.filter(is_deleted=False).select_related(
            'product', 'buyer'
        ).order_by('-suggested_at')

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page if page is not None else queryset, many=True)
        lang = getattr(request, 'language', 'en')
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return StandardResponse.success(
            data=serializer.data,
            message=t('marketplace.matches_retrieved', lang),
        )