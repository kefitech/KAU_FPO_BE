"""
Arunima S

Admin Market Linkage API — Browse FPOs and their product listings
====================================================================
Base Path: /api/admin/market-linkage/

Read-only. Lets an admin pick an FPO from those that have listed at least
one product, then view that FPO's product listings. No new model — this
is a view-only feature over the existing Product/FPO data. Query + response
logic is shared with the CBBO portal (apps/marketplace/linkage.py).

Sub-admins only see FPOs assigned to them (P2-01 row-level security).
"""

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.views import APIView

from apps.core.permissions.fpo_scope import scope_fpo_queryset
from apps.core.permissions.rbac import IsAuthenticated, IsSubAdminOrSuperAdmin
from apps.core.services.translation import t
from apps.core.utils.responses import StandardResponse
from apps.database.models import FPO
from apps.marketplace.linkage import linkage_fpos_response, linkage_products_response


@extend_schema(
    tags=['Marketplace - Admin Market Linkage'],
    parameters=[OpenApiParameter('search', str, description='FPO name contains')],
)
class AdminMarketLinkageFPOListView(APIView):
    """
    GET /api/admin/market-linkage/fpos/

    Lists only FPOs that have listed at least one (non-deleted) stock batch.
    Paginated; `product_count` is the number of listed batches.
    """

    permission_classes = [IsAuthenticated, IsSubAdminOrSuperAdmin]

    def get(self, request):
        return linkage_fpos_response(request, scope_fpo_queryset(FPO.objects.all(), request.user))


@extend_schema(
    tags=['Marketplace - Admin Market Linkage'],
    parameters=[
        OpenApiParameter('search', str, description='Product name (English or Malayalam) contains'),
        OpenApiParameter('commodity', str, description='Commodity code, or several comma-separated codes'),
        OpenApiParameter('status', str, description='draft / active / sold / expired'),
    ],
)
class AdminMarketLinkageFPOProductsView(APIView):
    """
    GET /api/admin/market-linkage/fpos/{fpo_id}/products/

    Lists the FPO's stock batches (one card per batch, every status) in the
    same shape as the buyer product catalog, plus status/is_public.
    """

    permission_classes = [IsAuthenticated, IsSubAdminOrSuperAdmin]

    def get(self, request, fpo_id):
        lang = getattr(request, 'language', 'en')

        # out-of-scope FPO is a 404, same as a missing one
        if not scope_fpo_queryset(FPO.objects.filter(id=fpo_id, is_deleted=False), request.user).exists():
            return StandardResponse.error(
                message=t('marketplace.linkage_fpo_not_found', lang),
                status_code=404,
            )
        return linkage_products_response(request, fpo_id)
