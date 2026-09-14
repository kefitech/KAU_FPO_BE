"""
Buyer Dashboard API
====================

ARUNIMA S
==============
GET /api/marketplace/buyer/dashboard/

Returns the buyer's own profile summary. Works for both buyer types:
- External buyer (BuyerDirectory.user is set)
- FPO-as-buyer (BuyerDirectory.fpo is set, linked via request.user.fpo)

Access restricted to buyers with status='verified'.
"""
from rest_framework import status as http_status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.utils.responses import StandardResponse
from apps.database.models import BuyerDirectory


def _get_buyer_row(user):
    """Resolve the BuyerDirectory row for this user, whichever way they're linked."""
    # External buyer — direct OneToOne link
    buyer = getattr(user, 'buyer_profile', None)
    if buyer is not None:
        return buyer

    # FPO-as-buyer — linked via the FPO the user belongs to
    fpo = getattr(user, 'fpo', None)
    if fpo is not None:
        buyer = getattr(fpo, 'buyer_registration', None)
        if buyer is not None:
            return buyer

    return None


class BuyerDashboardView(APIView):
    """
    GET /api/marketplace/buyer/dashboard/

    Returns 403 if the user has no BuyerDirectory row at all, or if their
    status isn't 'verified'. Frontend uses the returned `status` to decide
    where to redirect (pending → waiting page, rejected → rejected page).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        buyer = _get_buyer_row(request.user)

        if buyer is None:
            return StandardResponse.error(
                message='No buyer profile found for this account',
                status_code=http_status.HTTP_404_NOT_FOUND,
            )

        buyer_type = 'fpo' if buyer.fpo_id else 'external'

        data = {
            'id': buyer.id,
            'name': buyer.name,
            'organisation': buyer.organisation,
            'contact_email': buyer.contact_email,
            'contact_phone': buyer.contact_phone,
            'location': buyer.location,
            'commodities_interested': buyer.commodities_interested,
            'status': buyer.status,
            'buyer_type': buyer_type,
            'created_at': buyer.created_at,
        }

        return StandardResponse.success(
            data=data,
            message='Buyer dashboard retrieved successfully',
        )