"""
Arunima S

Buyer Directory API
====================
Admin-managed CRUD: /api/admin/buyers/
FPO browse (verified only, read-only): /api/marketplace/buyers/
"""

import secrets
import string

from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework import filters
from apps.core.models.generic import AuditLog
from apps.core.permissions.rbac import IsAdmin, IsAuthenticated, IsFPOManager
from apps.core.services.audit import AuditService as AuditLogService
from apps.core.services.translation import t
from apps.core.utils.pagination import StandardPagination
from apps.core.utils.responses import StandardResponse
from apps.core.utils.validators import validate_password_strength
from apps.core.views import TranslatedViewSet
from apps.database.models import BuyerDirectory
from apps.marketplace.serializers import BuyerDirectorySerializer
from apps.notifications.services import send_notification

User = get_user_model()


def _resolve_buyer_user(buyer):
    """
    Returns the Django User linked to this buyer, or None if there isn't one
    (e.g. an admin-added buyer with no login account).
    External buyers → buyer.user
    FPO-as-buyer     → buyer.fpo.primary_user
    """
    if buyer.user_id:
        return buyer.user
    if buyer.fpo_id and buyer.fpo.primary_user_id:
        return buyer.fpo.primary_user
    return None


def _generate_temp_password():
    chars = string.ascii_letters + string.digits + '!@#$%'
    while True:
        pwd = ''.join(secrets.choice(chars) for _ in range(12))
        try:
            validate_password_strength(pwd)
            return pwd
        except Exception:
            continue


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

    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'organisation', 'contact_email', 'contact_phone']

    list_message = 'marketplace.buyers_retrieved'
    create_message = 'marketplace.buyer_created'
    update_message = 'marketplace.buyer_updated'
    destroy_message = 'marketplace.buyer_deleted'

    def get_queryset(self):
        from django.db.models import Q

        queryset = BuyerDirectory.objects.filter(is_deleted=False).order_by('-created_at')
        buyer_type = self.request.query_params.get('buyer_type')
        if buyer_type == 'fpo':
            queryset = queryset.filter(fpo__isnull=False)
        elif buyer_type == 'external':
            queryset = queryset.filter(user__isnull=False)

        status = self.request.query_params.get('status')
        if status == 'deactivated':
            # Verified, but the linked account has been switched off.
            queryset = queryset.filter(status='verified').filter(
                Q(user__isnull=False, user__is_active=False) |
                Q(fpo__isnull=False, fpo__primary_user__is_active=False)
            )
        elif status == 'verified':
            # Verified AND active — deactivated buyers are excluded, they get
            # their own filter option above instead.
            queryset = queryset.filter(status='verified').exclude(
                Q(user__isnull=False, user__is_active=False) |
                Q(fpo__isnull=False, fpo__primary_user__is_active=False)
            )
        elif status in ('pending', 'rejected'):
            queryset = queryset.filter(status=status)

        return queryset

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

    @extend_schema(tags=['Marketplace - Buyers'])
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        buyer = self.get_object()
        user = _resolve_buyer_user(buyer)
        if not user:
            return StandardResponse.error(
                'No linked account found for this buyer.',
                status_code=404,
            )
        user.is_active = False
        user.save(update_fields=['is_active'])

        AuditLogService.log(
            user=request.user,
            action=AuditLog.Action.UPDATE,
            instance=buyer,
            request=request,
            changes={'deactivated_buyer': user.email},
        )
        return StandardResponse.success(message='Buyer account deactivated.')

    @extend_schema(tags=['Marketplace - Buyers'])
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        buyer = self.get_object()
        user = _resolve_buyer_user(buyer)
        if not user:
            return StandardResponse.error(
                'No linked account found for this buyer.',
                status_code=404,
            )
        user.is_active = True
        user.save(update_fields=['is_active'])

        AuditLogService.log(
            user=request.user,
            action=AuditLog.Action.UPDATE,
            instance=buyer,
            request=request,
            changes={'activated_buyer': user.email},
        )
        return StandardResponse.success(message='Buyer account activated.')

    @extend_schema(
        tags=['Marketplace - Buyers'],
        summary='Reset a buyer account password',
        description='Generates a temporary password, sets must_change_password=True, and notifies the buyer via email.',
    )
    @action(detail=True, methods=['post'], url_path='reset-password')
    def reset_password(self, request, pk=None):
        buyer = self.get_object()
        user = _resolve_buyer_user(buyer)
        if not user:
            return StandardResponse.error(
                'No linked account found for this buyer.',
                status_code=404,
            )

        temp_password = _generate_temp_password()
        user.set_password(temp_password)
        user.save(update_fields=['password'])

        profile = getattr(user, 'profile', None)
        if profile:
            profile.must_change_password = True
            profile.save(update_fields=['must_change_password'])

        context = {
            'user_name':     f'{user.first_name} {user.last_name}'.strip() or user.email,
            'temp_password': temp_password,
            'button_link':   '',
            'button_text':   'Login',
        }
        try:
            send_notification(user=user, code='password_reset_by_admin', channel='email', context=context)
        except Exception:
            pass

        AuditLogService.log(
            user=request.user,
            action=AuditLog.Action.PASSWORD_RESET,
            instance=buyer,
            request=request,
            changes={'reset_password_for': user.email},
        )
        return StandardResponse.success(message='Password reset. Buyer will be prompted to change it on next login.')


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