"""
Arunima S

Buyer Directory API
====================
Admin-managed CRUD: /api/admin/buyers/
FPO browse (verified only, read-only): /api/marketplace/buyers/
"""

from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, viewsets
from rest_framework.decorators import action

from apps.core.permissions.rbac import IsAdmin, IsAuthenticated, IsFPOManager
from apps.core.services.translation import t
from apps.core.utils.pagination import StandardPagination
from apps.core.utils.responses import StandardResponse
from apps.core.views import TranslatedViewSet
from apps.database.models import BuyerDirectory
from apps.marketplace.serializers import BuyerDirectorySerializer


@extend_schema_view(
    list=extend_schema(tags=['Marketplace - Buyers']),
    create=extend_schema(tags=['Marketplace - Buyers']),
    retrieve=extend_schema(tags=['Marketplace - Buyers']),
    update=extend_schema(tags=['Marketplace - Buyers']),
    partial_update=extend_schema(tags=['Marketplace - Buyers']),
    destroy=extend_schema(tags=['Marketplace - Buyers']),
)
class BuyerDirectoryViewSet(TranslatedViewSet):
    """
    Admin only — ARUNIMA.md "Buyer Directory (Admin only)":
    GET/POST          /api/admin/buyers/
    PATCH/DELETE      /api/admin/buyers/{id}/
    POST              /api/admin/buyers/{id}/verify/
    """

    serializer_class = BuyerDirectorySerializer 
    permission_classes = [IsAuthenticated, IsAdmin]
    pagination_class = StandardPagination

    list_message = 'marketplace.buyers_retrieved'
    create_message = 'marketplace.buyer_created'
    update_message = 'marketplace.buyer_updated'
    destroy_message = 'marketplace.buyer_deleted'

    def get_queryset(self):
        return BuyerDirectory.objects.filter(is_deleted=False).order_by('-created_at')

    def perform_destroy(self, instance):
        # BaseModel provides soft_delete() — use it instead of a hard delete.
        # This is the standard DRF hook (not list/create/update/destroy itself),
        # so TranslatedViewSet's destroy() still handles the StandardResponse
        # formatting/message normally — nothing else needs to change here.
        instance.soft_delete(user=self.request.user)

    @extend_schema(tags=['Marketplace - Buyers'])
    @action(detail=True, methods=['post'])
    def verify(self, request, pk=None):
        buyer = self.get_object()
        buyer.is_verified = True
        buyer.status = BuyerDirectory.Status.VERIFIED
        buyer.save(update_fields=['is_verified', 'status', 'updated_at'])
        return StandardResponse.success(
            data=BuyerDirectorySerializer(buyer).data,
            message=t('marketplace.buyer_verified', self.get_language())
        )
    @extend_schema(tags=['Marketplace - Buyers'])
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        buyer = self.get_object()
        buyer.is_verified = False
        buyer.status = BuyerDirectory.Status.REJECTED
        buyer.save(update_fields=['is_verified', 'status', 'updated_at'])
        return StandardResponse.success(
            data=BuyerDirectorySerializer(buyer).data,
            message=t('marketplace.buyer_rejected', self.get_language())
        )


@extend_schema_view(
    list=extend_schema(tags=['Marketplace - Buyers']),
)
class FPOBuyerListViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    FPO — GET /api/marketplace/buyers/ — browse verified buyers.

    Not in ARUNIMA.md's original endpoint list (buyer directory there was
    admin-only); added on request from the other P2-11 spec doc. Read-only
    on purpose — FPOs can look but not edit the buyer directory, that stays
    admin-managed via /api/admin/buyers/.

    Only shows is_verified=True buyers — an unverified buyer hasn't been
    checked by admin yet, so FPOs shouldn't see or contact them.
    """

    serializer_class = BuyerDirectorySerializer
    permission_classes = [IsAuthenticated, IsFPOManager]
    pagination_class = StandardPagination

    def get_queryset(self):
        return BuyerDirectory.objects.filter(
            is_verified=True, is_deleted=False
        ).order_by('name')

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page if page is not None else queryset, many=True)
        lang = getattr(request, 'language', 'en')
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return StandardResponse.success(
            data=serializer.data,
            message=t('marketplace.buyers_retrieved', lang),
        )
    #Arunima 04 sep-----
    @extend_schema(tags=['Marketplace - Buyers'])
    @action(detail=False, methods=['get'], url_path='my-status')
    def my_status(self, request):
        """
        GET /api/marketplace/buyers/my-status/

        Returns the requesting FPO's own BuyerDirectory row, if any.
        Drives the 3-state UI: not registered / pending / verified.
        """
        from apps.database.models import FPO

        fpo = FPO.objects.filter(primary_user=request.user).first()
        if not fpo:
            return StandardResponse.error(
                'No FPO found for this user.',
                status_code=404,
            )

        buyer = BuyerDirectory.objects.filter(fpo=fpo, is_deleted=False).first()
        lang = getattr(request, 'language', 'en')

        if not buyer:
            return StandardResponse.success(
                data={'registered': False, 'status': None},
                message=t('marketplace.buyers_retrieved', lang),
            )

        return StandardResponse.success(
            data={'registered': True, **BuyerDirectorySerializer(buyer).data},
            message=t('marketplace.buyers_retrieved', lang),
        )

    @extend_schema(tags=['Marketplace - Buyers'])
    @action(detail=False, methods=['post'], url_path='register')
    def register_as_buyer(self, request):
        """
        POST /api/marketplace/buyers/register/

        Primary User only. Registers the requesting FPO as a buyer —
        creates a pending BuyerDirectory row awaiting KAU verification.
        """
        from apps.database.models import FPO

        fpo = FPO.objects.filter(primary_user=request.user).first()
        if not fpo:
            return StandardResponse.error(
                'No FPO found for this user.',
                status_code=404,
            )

        if fpo.primary_user_id != request.user.id:
            return StandardResponse.error(
                'Only the FPO Primary User can register as a buyer.',
                status_code=403,
            )

        if BuyerDirectory.objects.filter(fpo=fpo, is_deleted=False).exists():
            return StandardResponse.error(
                'This FPO has already registered as a buyer.',
                status_code=400,
            )

        buyer = BuyerDirectory.objects.create(
            fpo=fpo,
            name=fpo.name,
            organisation=fpo.name,
            contact_email=fpo.office_email or '',
            contact_phone=fpo.office_phone or '',
            location=fpo.district,
            status=BuyerDirectory.Status.PENDING,
            is_verified=False,
        )

        lang = getattr(request, 'language', 'en')
        return StandardResponse.created(
            data=BuyerDirectorySerializer(buyer).data,
            message=t('marketplace.buyer_created', lang),
        )
    #--------------------------