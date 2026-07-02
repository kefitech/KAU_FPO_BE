"""
FPO User Authentication APIs
=============================
Public registration endpoint for FPO primary users.
URL: POST /api/auth/register/
"""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.core.utils.responses import StandardResponse
from apps.core.utils.throttles import RegisterThrottle
from apps.notifications.services import send_notification

from .serializers import RegisterFPOUserSerializer


class RegisterFPOUserView(APIView):
    """
    POST /api/auth/register/

    Self-registration for FPO primary users (CEO / Manager).
    Creates account and assigns fpo_manager role automatically.

    After successful registration the user can log in immediately
    using their email and password via POST /api/auth/login/.
    """

    permission_classes  = [AllowAny]
    throttle_classes    = [RegisterThrottle]
    serializer_class    = RegisterFPOUserSerializer

    @extend_schema(
        tags=["Authentication"],
        summary="Register FPO User",
        description=(
            "Public self-registration for FPO primary users. "
            "Creates an fpo_manager account. Username is set to email automatically. "
            "After registration, log in via POST /api/auth/login/ using email and password."
        ),
        request=RegisterFPOUserSerializer,
        responses={
            201: OpenApiResponse(description="Registration successful"),
            400: OpenApiResponse(description="Validation error"),
        },
    )
    def post(self, request):
        serializer = RegisterFPOUserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Send welcome notifications (best-effort — don't block registration)
        try:
            send_notification(
                user=user,
                code='welcome_fpo',
                channel='email',
                context={
                    'user_name': user.get_full_name() or user.email,
                },
            )
        except Exception:
            pass

        try:
            send_notification(
                user=user,
                code='welcome_fpo',
                channel='sms',
                context={
                    'user_name': user.get_full_name() or user.email,
                },
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
            message="Registration successful. You can now log in.",
        )
