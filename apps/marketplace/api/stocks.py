"""
Product Stock API — per-batch CRUD for the multi-batch marketplace
===================================================================
Base path: /api/marketplace/products/{product_pk}/stocks/

A single Product can have many stock batches live simultaneously
(e.g. 100 kg @ ₹85 + 500 kg @ ₹82). Each batch has its own quantity,
price, availability window and lifecycle (DRAFT → ACTIVE → SOLD / EXPIRED).

Legacy single-batch actions (ProductViewSet.publish / mark_sold) still
work for the common one-batch-per-product case, but any multi-batch
flow must come through here.
"""

from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.decorators import action

from apps.core.exceptions import BusinessLogicError
from apps.core.permissions.rbac import IsAuthenticated, IsFPOManager
from apps.core.services.fpo_permission import get_member_fpo
from apps.core.services.translation import t
from apps.core.utils.responses import StandardResponse
from apps.core.views import TranslatedViewSet
from apps.database.models import Product, ProductStock
from apps.marketplace.permissions import CanManageProducts, IsApprovedFPO
from apps.marketplace.serializers import ProductStockSerializer
from apps.marketplace.services import (
    run_matching, switch_product_off_if_all_inactive, switch_product_off_if_no_live_batch,
    switch_product_on_for_live_batch,
)


def _clear_public_market_cache():
    """Mirror of products.py — same purpose, kept local to avoid a cross-
    import between sibling API modules."""
    from django.core.cache import cache
    try:
        cache.delete_pattern('public:market:products:*')
        cache.delete_pattern('public:market:commodities:*')
        cache.delete_pattern('public:market:opportunities')
    except AttributeError:
        pass


@extend_schema_view(
    list=extend_schema(tags=['Marketplace - Product Stocks']),
    create=extend_schema(tags=['Marketplace - Product Stocks']),
    retrieve=extend_schema(tags=['Marketplace - Product Stocks']),
    update=extend_schema(tags=['Marketplace - Product Stocks']),
    partial_update=extend_schema(tags=['Marketplace - Product Stocks']),
    destroy=extend_schema(tags=['Marketplace - Product Stocks']),
)
class ProductStockViewSet(TranslatedViewSet):
    """
    GET/POST          /api/marketplace/products/{product_pk}/stocks/
    GET/PATCH/DELETE  /api/marketplace/products/{product_pk}/stocks/{id}/
    POST              /api/marketplace/products/{product_pk}/stocks/{id}/publish/
    POST              /api/marketplace/products/{product_pk}/stocks/{id}/mark-sold/
    """

    serializer_class = ProductStockSerializer
    # Same as ProductViewSet: any FPO member can view batches; add / edit /
    # publish / mark-sold / delete need can_manage_products.
    permission_classes = [IsAuthenticated, IsFPOManager, IsApprovedFPO, CanManageProducts]

    list_message = 'marketplace.stocks_retrieved'
    create_message = 'marketplace.stock_created'
    update_message = 'marketplace.stock_updated'
    destroy_message = 'marketplace.stock_deleted'

    def _get_product(self):
        """Resolve the parent product and enforce ownership. Raises 404 if
        the current FPO doesn't own the product — matches the pattern used
        by ProductViewSet.get_queryset(). get_member_fpo() resolves the FPO
        for the primary user and for team members alike."""
        from django.shortcuts import get_object_or_404
        fpo = get_member_fpo(self.request.user)
        return get_object_or_404(
            Product.objects.select_related('fpo'),
            pk=self.kwargs['product_pk'],
            fpo=fpo,
            is_deleted=False,
        )

    def get_queryset(self):
        product = self._get_product()
        return ProductStock.objects.filter(
            product=product, is_deleted=False,
        ).order_by('-created_at')

    def perform_create(self, serializer):
        product = self._get_product()
        # New batches default to DRAFT (ProductStock.status default), but
        # the FPO can send status=active to publish immediately in one
        # request — ProductStockSerializer.validate_status gates the
        # choice to {draft, active}.
        stock = serializer.save(product=product)
        if stock.status == ProductStock.Status.ACTIVE:
            switch_product_on_for_live_batch(product)
            run_matching(stock)
        _clear_public_market_cache()

    def perform_update(self, serializer):
        stock = serializer.instance
        if stock.status not in (
            ProductStock.Status.DRAFT, ProductStock.Status.ACTIVE, ProductStock.Status.INACTIVE,
        ):
            raise BusinessLogicError(
                message=t('marketplace.product_not_editable', self.get_language()),
                code='product_not_editable',
            )
        old_status = stock.status
        updated = serializer.save()
        # Draft → active transition triggered via raw PATCH (status=active)
        # should still fire matching, same as the explicit publish action.
        if old_status == ProductStock.Status.DRAFT and updated.status == ProductStock.Status.ACTIVE:
            run_matching(updated)
        # A PATCH can go live or pause a batch too — same product switch
        # rules as the publish / activate / deactivate actions.
        if old_status != ProductStock.Status.ACTIVE and updated.status == ProductStock.Status.ACTIVE:
            switch_product_on_for_live_batch(updated.product)
        elif old_status == ProductStock.Status.ACTIVE and updated.status == ProductStock.Status.INACTIVE:
            switch_product_off_if_no_live_batch(updated.product)
        _clear_public_market_cache()

    def perform_destroy(self, instance):
        if instance.status != ProductStock.Status.DRAFT:
            raise BusinessLogicError(
                message=t('marketplace.only_draft_deletable', self.get_language()),
                code='only_draft_deletable',
            )
        instance.soft_delete(user=self.request.user)
        # Removing the last non-paused batch leaves only paused ones.
        switch_product_off_if_all_inactive(instance.product)
        _clear_public_market_cache()

    @extend_schema(tags=['Marketplace - Product Stocks'])
    @action(detail=True, methods=['post'])
    def publish(self, request, product_pk=None, pk=None):
        """DRAFT → ACTIVE for one batch, then runs buyer-seller matching
        on that batch."""
        stock = self.get_object()
        if stock.status != ProductStock.Status.DRAFT:
            raise BusinessLogicError(
                message=t('marketplace.only_draft_publishable', self.get_language()),
                code='only_draft_publishable',
            )
        if stock.available_until and stock.available_until < timezone.localdate():
            raise BusinessLogicError(
                message=t('marketplace.batch_validity_ended', self.get_language()),
                code='batch_validity_ended',
            )
        stock.status = ProductStock.Status.ACTIVE
        stock.save()
        switch_product_on_for_live_batch(stock.product)
        run_matching(stock)
        _clear_public_market_cache()
        return StandardResponse.success(
            data=ProductStockSerializer(stock).data,
            message=t('marketplace.product_published', self.get_language()),
        )

    @extend_schema(tags=['Marketplace - Product Stocks'])
    @action(detail=True, methods=['post'], url_path='mark-sold')
    def mark_sold(self, request, product_pk=None, pk=None):
        """ACTIVE → SOLD for one batch."""
        stock = self.get_object()
        if stock.status != ProductStock.Status.ACTIVE:
            raise BusinessLogicError(
                message=t('marketplace.only_active_can_be_sold', self.get_language()),
                code='only_active_can_be_sold',
            )
        stock.status = ProductStock.Status.SOLD
        stock.save()
        _clear_public_market_cache()
        return StandardResponse.success(
            data=ProductStockSerializer(stock).data,
            message=t('marketplace.product_sold', self.get_language()),
        )

    @extend_schema(tags=['Marketplace - Product Stocks'])
    @action(detail=True, methods=['post'])
    def deactivate(self, request, product_pk=None, pk=None):
        """ACTIVE → INACTIVE: pause the batch — hidden from buyers and the
        Market Hub until reactivated. Pausing the last live batch switches
        the product off too."""
        stock = self.get_object()
        if stock.status != ProductStock.Status.ACTIVE:
            raise BusinessLogicError(
                message=t('marketplace.only_active_deactivatable', self.get_language()),
                code='only_active_deactivatable',
            )
        stock.status = ProductStock.Status.INACTIVE
        stock.save()
        switch_product_off_if_no_live_batch(stock.product)
        _clear_public_market_cache()
        return StandardResponse.success(
            data=ProductStockSerializer(stock).data,
            message=t('marketplace.stock_deactivated', self.get_language()),
        )

    @extend_schema(tags=['Marketplace - Product Stocks'])
    @action(detail=True, methods=['post'])
    def activate(self, request, product_pk=None, pk=None):
        """INACTIVE → ACTIVE: list a paused batch again (validity permitting),
        switching the product back on if it was off."""
        stock = self.get_object()
        if stock.status != ProductStock.Status.INACTIVE:
            raise BusinessLogicError(
                message=t('marketplace.only_inactive_activatable', self.get_language()),
                code='only_inactive_activatable',
            )
        if stock.available_until and stock.available_until < timezone.localdate():
            raise BusinessLogicError(
                message=t('marketplace.batch_validity_ended', self.get_language()),
                code='batch_validity_ended',
            )
        stock.status = ProductStock.Status.ACTIVE
        stock.save()
        switch_product_on_for_live_batch(stock.product)
        run_matching(stock)
        _clear_public_market_cache()
        return StandardResponse.success(
            data=ProductStockSerializer(stock).data,
            message=t('marketplace.stock_activated', self.get_language()),
        )
