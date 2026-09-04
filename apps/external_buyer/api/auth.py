"""
External Buyer Authentication APIs
====================================
Public registration endpoint for external buyers.
URL: POST /api/external-buyer/register/
"""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.core.utils.responses import StandardResponse
from apps.core.utils.throttles import RegisterThrottle
from apps.notifications.services import send_notification

from .serializers import RegisterBuyerUserSerializer


class RegisterBuyerUserView(APIView):
    """
    POST /api/external-buyer/register/

    Self-registration for external buyers. Creates account, assigns the
    external_buyer group, and creates a pending BuyerDirectory row awaiting
    KAU verification. Requires phone + email to already be OTP-verified.
    """

    permission_classes = [AllowAny]
    throttle_classes    = [RegisterThrottle]
    serializer_class    = RegisterBuyerUserSerializer

    @extend_schema(
        tags=["External Buyer - Registration"],
        summary="Register External Buyer",
        description=(
            "Public self-registration for external buyers. Creates an external_buyer "
            "account and a pending BuyerDirectory entry awaiting KAU verification. "
            "Requires phone_token and email_token from the pre-registration OTP flow."
        ),
        request=RegisterBuyerUserSerializer,
        responses={
            201: OpenApiResponse(description="Registration successful — pending KAU verification"),
            400: OpenApiResponse(description="Validation error"),
        },
    )
    def post(self, request):
        serializer = RegisterBuyerUserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        try:
            send_notification(
                user=user,
                code='welcome_fpo',
                channel='email',
                context={'user_name': user.get_full_name() or user.email},
            )
        except Exception:
            pass

        return StandardResponse.created(
            data={
                'id':         user.id,
                'email':      user.email,
                'first_name': user.first_name,
                'last_name':  user.last_name,
                'phone':      user.profile.phone,
            },
            message="Registration successful. Your buyer account is pending KAU verification.",
        )