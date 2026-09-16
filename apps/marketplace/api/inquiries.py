"""
Arunima S

Inquiry API — verified-buyer purchase inquiries on marketplace products
=========================================================================
POST /api/marketplace/buyer/products/{id}/inquire/   — buyer submits inquiry
GET  /api/marketplace/inquiries/                       — seller's own inquiries list
POST /api/marketplace/inquiries/{id}/mark-contacted/  — seller action
POST /api/marketplace/inquiries/{id}/mark-resolved/   — seller action

Distinct from the public Market Hub's anonymous inquiry flow
(apps/marketplace/api/public.py: PublicProductInquireView), which creates
a new BuyerDirectory row for unverified visitors. Here the buyer is already
a verified BuyerDirectory row (FPO-as-buyer or external buyer) — this
endpoint does NOT create a new BuyerDirectory row.
"""
from drf_spectacular.utils import extend_schema
from rest_framework import status as http_status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import mixins, viewsets

from apps.core.permissions.rbac import IsFPOManager
from apps.core.utils.pagination import StandardPagination
from apps.core.utils.responses import StandardResponse
from apps.database.models import Inquiry, Product
from apps.marketplace.api.buyers import _resolve_buyer_user
from apps.marketplace.serializers import InquiryCreateSerializer, InquirySerializer
from apps.marketplace.services import _get_buyer_row


class InquiryCreateView(APIView):
    """
    POST /api/marketplace/buyer/products/{id}/inquire/

    Verified-buyer-only (same check as BuyerProductListView). Creates an
    Inquiry linked to the requesting user's BuyerDirectory row, with
    contact_user resolved via _resolve_buyer_user() — the same helper
    already used for admin deactivate/reset-password actions in
    apps/marketplace/api/buyers.py — so the FPO-vs-external-buyer
    resolution logic isn't duplicated here.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Marketplace - Inquiries'], summary='Submit a purchase inquiry', request=InquiryCreateSerializer)
    def post(self, request, pk):
        buyer = _get_buyer_row(request.user)
        if buyer is None or buyer.status != 'verified':
            return StandardResponse.error(
                message='Only verified buyers can submit inquiries',
                status_code=http_status.HTTP_403_FORBIDDEN,
            )

        try:
            product = Product.objects.select_related('fpo').get(
                pk=pk, status=Product.Status.ACTIVE, is_public=True, is_deleted=False,
            )
        except Product.DoesNotExist:
            return StandardResponse.error(message='Product not found', status_code=http_status.HTTP_404_NOT_FOUND)

        serializer = InquiryCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        contact_user = _resolve_buyer_user(buyer)

        inquiry = Inquiry.objects.create(
            product=product,
            buyer=buyer,
            contact_user=contact_user,
            quantity_requested=serializer.validated_data['quantity_requested'],
            message=serializer.validated_data.get('message', ''),
        )

        # Notify the selling FPO's primary user — short notification only,
        # per confirmed requirement (no full message/contact details in body).
        seller_user = getattr(product.fpo, 'primary_user', None)
        if seller_user:
            from apps.notifications.services import send_notification
            try:
                send_notification(
                    user=seller_user,
                    code='verified_buyer_inquiry',
                    channel='email',
                    context={
                        'product_name': product.name.get('en', '') if product.name else '',
                        'fpo_name': product.fpo.name,
                    },
                )
            except Exception:
                pass  # Inquiry already saved — don't fail the request if notification dispatch fails

        return StandardResponse.success(
            data={'inquiry_id': inquiry.id},
            message='Inquiry submitted successfully',
            status_code=http_status.HTTP_201_CREATED,
        )


class InquiryViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    GET /api/marketplace/inquiries/ — seller's own incoming inquiries.
    Scoped to inquiries on products belonging to the logged-in FPO, same
    scoping pattern as ProductViewSet.get_queryset() (request.user.fpo).

    POST .../mark-contacted/ and .../mark-resolved/ — one-way status
    progression only (pending -> contacted -> resolved), matching the
    confirmed requirement. No reverse transitions, no "resolved -> pending".
    """
    permission_classes = [IsFPOManager]
    pagination_class = StandardPagination
    serializer_class = InquirySerializer

    def get_queryset(self):
        return Inquiry.objects.filter(
            product__fpo=self.request.user.fpo,
            is_deleted=False,
        ).select_related('product', 'buyer', 'buyer__fpo', 'contact_user').order_by('-created_at')

    @extend_schema(tags=['Marketplace - Inquiries'])
    @action(detail=True, methods=['post'], url_path='mark-contacted')
    def mark_contacted(self, request, pk=None):
        inquiry = self.get_object()
        if inquiry.status != Inquiry.Status.PENDING:
            return StandardResponse.error(
                message='Only pending inquiries can be marked as contacted',
                status_code=http_status.HTTP_400_BAD_REQUEST,
            )
        inquiry.status = Inquiry.Status.CONTACTED
        inquiry.save(update_fields=['status', 'updated_at'])
        return StandardResponse.success(message='Inquiry marked as contacted')

    @extend_schema(tags=['Marketplace - Inquiries'])
    @action(detail=True, methods=['post'], url_path='mark-resolved')
    def mark_resolved(self, request, pk=None):
        inquiry = self.get_object()
        if inquiry.status != Inquiry.Status.CONTACTED:
            return StandardResponse.error(
                message='Only contacted inquiries can be marked as resolved',
                status_code=http_status.HTTP_400_BAD_REQUEST,
            )
        inquiry.status = Inquiry.Status.RESOLVED
        inquiry.save(update_fields=['status', 'updated_at'])
        return StandardResponse.success(message='Inquiry marked as resolved')