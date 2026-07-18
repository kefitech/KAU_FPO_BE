from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.views import APIView

from apps.core.permissions.rbac import IsFPOManager
from apps.core.utils.constants import FPOStatus
from apps.core.utils.responses import StandardResponse
from apps.database.models.fpo import FPO, ApplicationStatusHistory


class _InfoResponseSerializer(serializers.Serializer):
    notes = serializers.CharField(
        min_length=10,
        help_text='Reply to the admin info request — minimum 10 characters',
    )


class FPOInfoResponseView(APIView):
    permission_classes = [IsFPOManager]

    @extend_schema(
        tags=['FPO - Registration'],
        summary='Reply to admin info request',
        description=(
            'Submits a response to an admin information request and moves the application back to '
            '`SUBMITTED` for manual admin review.\n\n'
            'FPO must be in `INFO_REQUIRED` status. The response note is recorded in the status '
            'history and the status transitions to `SUBMITTED`.'
        ),
        request=_InfoResponseSerializer,
        responses={200: None, 400: None},
    )
    def post(self, request):
        try:
            fpo = FPO.objects.get(primary_user=request.user)
        except FPO.DoesNotExist:
            return StandardResponse.error(
                'FPO profile not found.',
                status_code=status.HTTP_404_NOT_FOUND,
            )

        if fpo.status != FPOStatus.INFO_REQUIRED:
            return StandardResponse.error(
                'FPO must be in INFO_REQUIRED status to submit a response.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        ser = _InfoResponseSerializer(data=request.data)
        if not ser.is_valid():
            return StandardResponse.error(ser.errors, status_code=status.HTTP_400_BAD_REQUEST)

        ApplicationStatusHistory.objects.create(
            fpo=fpo,
            from_status=FPOStatus.INFO_REQUIRED,
            to_status=FPOStatus.SUBMITTED,
            notes=ser.validated_data['notes'],
            changed_by=request.user,
        )

        fpo.status = FPOStatus.SUBMITTED
        fpo.save(update_fields=['status'])

        return StandardResponse.success(message='Response submitted. Your application is now under review.')
