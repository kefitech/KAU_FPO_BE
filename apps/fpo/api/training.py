"""
FPO - Training Sessions (read-only)
FPO users view training sessions scheduled for their own FPO by
government officials or CBBOs.
"""
from rest_framework import serializers, status
from rest_framework.views import APIView

from apps.core.utils.pagination import StandardPagination
from apps.core.utils.responses import StandardResponse
from apps.database.models.cbbo import TrainingSession
from apps.database.models.fpo import FPOUserMembership
from apps.database.models.fpo import FPO


def _get_fpo(user):
    membership = FPOUserMembership.objects.filter(user=user, is_active=True).first()
    if membership:
        return membership.fpo
    return FPO.objects.filter(primary_user=user, is_deleted=False).first()


class _FPOTrainingSessionSerializer(serializers.ModelSerializer):
    conducted_by_name = serializers.SerializerMethodField()

    class Meta:
        model = TrainingSession
        fields = [
            'id', 'topic', 'trainer_name', 'date', 'time', 'duration_hours',
            'venue', 'participants_count', 'conducted_by_name', 'created_at',
        ]

    def get_conducted_by_name(self, obj):
        return obj.cbbo.get_full_name() or obj.cbbo.username


class FPOTrainingSessionListView(APIView):
    def get(self, request):
        fpo = _get_fpo(request.user)
        if not fpo:
            return StandardResponse.error(
                'Your account is not linked to an FPO.', status_code=status.HTTP_403_FORBIDDEN,
            )

        qs = TrainingSession.objects.filter(fpo=fpo, is_deleted=False).select_related('cbbo').order_by('-date')

        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        data = _FPOTrainingSessionSerializer(page, many=True).data
        return paginator.get_paginated_response(data)