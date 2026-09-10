"""
Expert - Get my own Expert profile.
GET /api/experts/me/
Returns the Expert record linked to the logged-in user's account, if any.
"""
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.utils.responses import StandardResponse


class MyExpertProfileView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Expert Booking'], summary='Get my own expert profile')
    def get(self, request):
        expert = getattr(request.user, 'expert_profile', None)
        if not expert:
            return StandardResponse.error('No expert profile linked to this account.', status_code=status.HTTP_404_NOT_FOUND)

        return StandardResponse.success(data={
            'id': expert.id,
            'name_en': expert.name_en,
            'designation': expert.designation,
        })
