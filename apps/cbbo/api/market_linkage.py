"""
CBBO Market Linkage — products directory of the CBBO's assigned FPOs.

    GET /api/cbbo/market-linkage/fpos/                       — assigned FPOs with listed products
    GET /api/cbbo/market-linkage/fpos/{fpo_id}/products/     — that FPO's batches (every status)

Read-only, same data/shape as the admin Market Linkage screen
(apps/marketplace/linkage.py). Scoped to the CBBO's active district /
state assignments; an FPO outside them is a 404, same as a missing one.
"""
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.views import APIView

from apps.cbbo.api.assignments import is_cbbo_user, scope_fpo_qs
from apps.core.services.translation import t
from apps.core.utils.responses import StandardResponse
from apps.database.models.fpo import FPO
from apps.marketplace.linkage import linkage_fpos_response, linkage_products_response


def _forbidden(request):
    return StandardResponse.error(
        t('common.permission_denied', request.language),
        status_code=status.HTTP_403_FORBIDDEN,
    )


@extend_schema(
    tags=['CBBO - Market Linkage'],
    parameters=[OpenApiParameter('search', str, description='FPO name contains')],
)
class CBBOMarketLinkageFPOListView(APIView):
    """GET /api/cbbo/market-linkage/fpos/ — assigned FPOs that have listed products."""

    def get(self, request):
        if not is_cbbo_user(request.user):
            return _forbidden(request)
        return linkage_fpos_response(request, scope_fpo_qs(FPO.objects.all(), request.user))


@extend_schema(
    tags=['CBBO - Market Linkage'],
    parameters=[
        OpenApiParameter('search', str, description='Product name (English or Malayalam) contains'),
        OpenApiParameter('commodity', str, description='Commodity code, or several comma-separated codes'),
        OpenApiParameter('status', str, description='draft / active / sold / expired'),
    ],
)
class CBBOMarketLinkageFPOProductsView(APIView):
    """GET /api/cbbo/market-linkage/fpos/{fpo_id}/products/ — 404 if outside jurisdiction."""

    def get(self, request, fpo_id):
        if not is_cbbo_user(request.user):
            return _forbidden(request)
        if not scope_fpo_qs(FPO.objects.filter(id=fpo_id, is_deleted=False), request.user).exists():
            return StandardResponse.error(
                t('marketplace.linkage_fpo_not_found', request.language),
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return linkage_products_response(request, fpo_id)
