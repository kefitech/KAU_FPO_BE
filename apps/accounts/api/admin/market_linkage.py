"""
Arunima S

Admin Market Linkage API — Browse FPOs and their product listings
====================================================================
Base Path: /api/admin/market-linkage/

Read-only. Lets an admin pick an FPO from those that have listed at least
one product, then view that FPO's product listings. No new model — this
is a view-only feature over the existing Product/FPO data.
"""

from drf_spectacular.utils import extend_schema
from rest_framework.views import APIView

from apps.core.permissions.rbac import IsAdmin, IsAuthenticated
from apps.core.services.translation import t
from apps.core.utils.pagination import StandardPagination
from apps.core.utils.responses import StandardResponse
from apps.database.models import FPO, Product
from apps.marketplace.serializers import ProductSerializer


@extend_schema(tags=['Marketplace - Admin Market Linkage'])
class AdminMarketLinkageFPOListView(APIView):
    """
    GET /api/admin/market-linkage/fpos/

    Lists only FPOs that have listed at least one (non-deleted) product.
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        lang = getattr(request, 'language', 'en')
        fpos = (
            FPO.objects.filter(is_deleted=False, products__is_deleted=False)
            .distinct()
            .order_by('name')
        )
        data = [
            {
                'id': fpo.id,
                'name': fpo.name,
                'name_ml': fpo.name_ml,
            }
            for fpo in fpos
        ]
        return StandardResponse.success(
            data=data,
            message=t('marketplace.linkage_fpos_retrieved', lang),
        )


@extend_schema(tags=['Marketplace - Admin Market Linkage'])
class AdminMarketLinkageFPOProductsView(APIView):
    """
    GET /api/admin/market-linkage/fpos/{fpo_id}/products/

    Lists all non-deleted products belonging to the given FPO.
    """

    permission_classes = [IsAuthenticated, IsAdmin]
    pagination_class = StandardPagination

    def get(self, request, fpo_id):
        lang = getattr(request, 'language', 'en')

        if not FPO.objects.filter(id=fpo_id).exists():
            return StandardResponse.error(
                message=t('marketplace.linkage_fpo_not_found', lang),
                status_code=404,
            )

        queryset = (
            Product.objects.filter(fpo_id=fpo_id, is_deleted=False)
            .select_related('commodity')
            .order_by('-created_at')
        )

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = ProductSerializer(page if page is not None else queryset, many=True)

        if page is not None:
            return paginator.get_paginated_response(serializer.data)
        return StandardResponse.success(
            data=serializer.data,
            message=t('marketplace.linkage_products_retrieved', lang),
        )