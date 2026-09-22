"""
Buyer Self-Service Profile API
================================
Lets a verified buyer read + patch their own BuyerDirectory row.

GET   /api/marketplace/buyer/profile/    — return the buyer's own row
PATCH /api/marketplace/buyer/profile/    — update location / commodities / etc.

Only the fields we consider safe for buyer self-edit are exposed. Contact
email/phone stay locked (they're what the buyer registered with) and admin
fields (is_verified, status, fpo, user) are never editable here.
"""

from rest_framework import serializers, status as http_status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.utils.responses import StandardResponse
from apps.database.models import BuyerDirectory

from apps.marketplace.services import _get_buyer_row


class BuyerProfileSerializer(serializers.ModelSerializer):
    """
    Fields the buyer can edit themselves. Everything else on BuyerDirectory
    is admin-only (status, verified flag, fpo/user links, contact_email/phone).
    """

    class Meta:
        model = BuyerDirectory
        fields = [
            'organisation',
            'location',
            'commodities_interested',
            'min_quantity',
            'max_quantity',
            'unit',
        ]


class BuyerProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def _resolve(self, user):
        buyer = _get_buyer_row(user)
        if buyer is None:
            return None, StandardResponse.error(
                message='No buyer profile found for this account',
                status_code=http_status.HTTP_404_NOT_FOUND,
            )
        return buyer, None

    def get(self, request):
        buyer, err = self._resolve(request.user)
        if err:
            return err
        return StandardResponse.success(
            data=BuyerProfileSerializer(buyer).data,
            message='Buyer profile retrieved',
        )

    def patch(self, request):
        buyer, err = self._resolve(request.user)
        if err:
            return err
        ser = BuyerProfileSerializer(buyer, data=request.data, partial=True)
        if not ser.is_valid():
            return StandardResponse.error(
                message='Validation failed',
                errors=ser.errors,
                status_code=http_status.HTTP_400_BAD_REQUEST,
            )
        ser.save()
        return StandardResponse.success(
            data=BuyerProfileSerializer(buyer).data,
            message='Buyer profile updated',
        )
