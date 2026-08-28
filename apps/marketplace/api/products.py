"""
Arunima S

Product API — FPO Product Listings
===================================
Base Path: /api/marketplace/products/
"""

from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.decorators import action

from apps.core.exceptions import BusinessLogicError
from apps.core.permissions.rbac import IsAuthenticated, IsFPOManager
from apps.core.services.translation import t
from apps.core.utils.pagination import StandardPagination
from apps.core.utils.responses import StandardResponse
from apps.core.views import TranslatedViewSet
from apps.database.models import Product
from apps.marketplace.permissions import IsApprovedFPO
from apps.marketplace.serializers import ProductSerializer
from apps.marketplace.services import run_matching


@extend_schema_view(
    list=extend_schema(tags=['Marketplace - Products']),
    create=extend_schema(tags=['Marketplace - Products']),
    retrieve=extend_schema(tags=['Marketplace - Products']),
    update=extend_schema(tags=['Marketplace - Products']),
    partial_update=extend_schema(tags=['Marketplace - Products']),
    destroy=extend_schema(tags=['Marketplace - Products']),
)
class ProductViewSet(TranslatedViewSet):
    """
    GET/POST          /api/marketplace/products/
    GET/PATCH/DELETE  /api/marketplace/products/{id}/
    POST              /api/marketplace/products/{id}/publish/
    POST              /api/marketplace/products/{id}/mark-sold/
    """

    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated, IsFPOManager, IsApprovedFPO]
    pagination_class = StandardPagination

    list_message = 'marketplace.products_retrieved'
    create_message = 'marketplace.product_created'
    update_message = 'marketplace.product_updated'
    destroy_message = 'marketplace.product_deleted'

    def get_queryset(self):
        # FPO only sees their own products; exclude soft-deleted rows
        fpo = self.request.user.fpo
        return Product.objects.filter(fpo=fpo, is_deleted=False).select_related(
            'commodity', 'fpo'
        ).order_by('-created_at')

    # update()/destroy() are NOT overridden — per house convention, business
    # rule checks live in perform_update()/perform_destroy(), raising
    # BusinessLogicError (HTTP 422). custom_exception_handler (apps/core/
    # exceptions/handlers.py) catches BaseAPIException subclasses and formats
    # them into the standard {"status": "error", "message": ..., "code": ...}
    # shape via exc.to_dict() — so TranslatedViewSet's built-in update()/
    # destroy() (which already return StandardResponse on success) stay
    # untouched.
    #
    # NOTE: BusinessLogicError returns HTTP 422, not 400 — this is a genuine
    # behavior change from the earlier StandardResponse.error(..., status_code=400)
    # version. 422 is arguably more correct for "valid request, wrong state"
    # (vs 400 "malformed request"), but flag this if the frontend specifically
    # expects 400 for these cases.

    def perform_update(self, serializer):
        product = serializer.instance
        if product.status not in (Product.Status.DRAFT, Product.Status.ACTIVE):
            raise BusinessLogicError(
                message=t('marketplace.product_not_editable', self.get_language()),
                code='product_not_editable',
            )
        serializer.save()

    def perform_destroy(self, instance):
        # Soft delete — draft only. BaseModel provides .soft_delete(), which
        # sets is_deleted=True instead of removing the row.
        if instance.status != Product.Status.DRAFT:
            raise BusinessLogicError(
                message=t('marketplace.only_draft_deletable', self.get_language()),
                code='only_draft_deletable',
            )
        instance.soft_delete(user=self.request.user)

    @extend_schema(tags=['Marketplace - Products'])
    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        """draft -> active, then runs buyer-seller matching."""
        product = self.get_object()
        if product.status != Product.Status.DRAFT:
            raise BusinessLogicError(
                message=t('marketplace.only_draft_publishable', self.get_language()),
                code='only_draft_publishable',
            )
        product.status = Product.Status.ACTIVE
        product.save()

        run_matching(product)

        return StandardResponse.success(
            data=ProductSerializer(product).data,
            message=t('marketplace.product_published', self.get_language())
        )

    @extend_schema(tags=['Marketplace - Products'])
    @action(detail=True, methods=['post'], url_path='mark-sold')
    def mark_sold(self, request, pk=None):
        product = self.get_object()
        if product.status != Product.Status.ACTIVE:
            raise BusinessLogicError(
                message=t('marketplace.only_active_can_be_sold', self.get_language()),
                code='only_active_can_be_sold',
            )
        product.status = Product.Status.SOLD
        product.save()
        return StandardResponse.success(
            data=ProductSerializer(product).data,
            message=t('marketplace.product_sold', self.get_language())
        )