"""
Government - Training Sessions (write access)
"""
from rest_framework import serializers, status
from rest_framework.views import APIView

from apps.core.utils.pagination import StandardPagination
from apps.core.utils.responses import StandardResponse
from apps.database.models.fpo import FPO
from apps.database.models.cbbo import TrainingSession, TrainingAttendance

from apps.government.api.scoping import is_government_user, scope_fpo_qs, get_fpo_scoped


class _SessionListSerializer(serializers.ModelSerializer):
    fpo_name = serializers.CharField(source='fpo.name', read_only=True)
    district = serializers.CharField(source='fpo.district', read_only=True)
    attendance_count = serializers.SerializerMethodField()

    class Meta:
        model = TrainingSession
        fields = ['id', 'fpo', 'fpo_name', 'district', 'topic', 'date',
                  'duration_hours', 'participants_count', 'venue', 'attendance_count']

    def get_attendance_count(self, obj):
        return obj.attendance.filter(attended=True).count()


class _SessionDetailSerializer(serializers.ModelSerializer):
    fpo_name = serializers.CharField(source='fpo.name', read_only=True)
    attendance = serializers.SerializerMethodField()

    class Meta:
        model = TrainingSession
        fields = ['id', 'fpo', 'fpo_name', 'topic', 'date', 'duration_hours',
                  'participants_count', 'venue', 'attendance', 'created_at', 'updated_at']

    def get_attendance(self, obj):
        return [
            {'id': a.id, 'member_name': a.member_name, 'attended': a.attended}
            for a in obj.attendance.all()
        ]


class _SessionCreateSerializer(serializers.Serializer):
    fpo_id = serializers.IntegerField()
    topic = serializers.CharField(max_length=300)
    date = serializers.DateField()
    duration_hours = serializers.DecimalField(max_digits=4, decimal_places=1, min_value=0.1)
    participants_count = serializers.IntegerField(min_value=0, default=0)
    venue = serializers.CharField(max_length=300, required=False, allow_blank=True)


class _AttendanceRowSerializer(serializers.Serializer):
    member_name = serializers.CharField(max_length=200)
    attended = serializers.BooleanField(default=False)


class _AttendanceSetSerializer(serializers.Serializer):
    attendance = _AttendanceRowSerializer(many=True)


class GovernmentTrainingSessionListView(APIView):
    def get(self, request):
        if not is_government_user(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        qs = TrainingSession.objects.filter(cbbo=request.user, is_deleted=False).select_related('fpo')
        qs = qs.filter(fpo__in=scope_fpo_qs(FPO.objects.filter(is_deleted=False), request.user))

        topic = request.query_params.get('topic')
        if topic:
            qs = qs.filter(topic__icontains=topic)

        qs = qs.order_by('-date')

        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        data = _SessionListSerializer(page, many=True).data
        return paginator.get_paginated_response(data)

    def post(self, request):
        if not is_government_user(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        serializer = _SessionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        fpo = get_fpo_scoped(serializer.validated_data['fpo_id'], request.user)
        if not fpo:
            return StandardResponse.error('FPO not found.', status_code=status.HTTP_404_NOT_FOUND)

        session = TrainingSession.objects.create(
            fpo=fpo,
            cbbo=request.user,
            topic=serializer.validated_data['topic'],
            date=serializer.validated_data['date'],
            duration_hours=serializer.validated_data['duration_hours'],
            participants_count=serializer.validated_data.get('participants_count', 0),
            venue=serializer.validated_data.get('venue', ''),
        )

        return StandardResponse.success(data={'id': session.id}, message='Training session recorded.')


class GovernmentTrainingSessionDetailView(APIView):
    def get(self, request, session_id):
        if not is_government_user(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        session = TrainingSession.objects.filter(
            id=session_id, cbbo=request.user, is_deleted=False
        ).select_related('fpo').prefetch_related('attendance').first()
        if not session:
            return StandardResponse.error('Session not found.', status_code=status.HTTP_404_NOT_FOUND)
        return StandardResponse.success(data=_SessionDetailSerializer(session).data)


class GovernmentTrainingAttendanceSetView(APIView):
    def post(self, request, session_id):
        if not is_government_user(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        session = TrainingSession.objects.filter(id=session_id, cbbo=request.user, is_deleted=False).first()
        if not session:
            return StandardResponse.error('Session not found.', status_code=status.HTTP_404_NOT_FOUND)

        serializer = _AttendanceSetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        from django.db import transaction
        with transaction.atomic():
            session.attendance.all().delete()
            rows = [
                TrainingAttendance(
                    session=session,
                    member_name=row['member_name'],
                    attended=row['attended'],
                )
                for row in serializer.validated_data['attendance']
            ]
            TrainingAttendance.objects.bulk_create(rows)

        return StandardResponse.success(
            data={'session_id': session.id, 'attendance_count': len(rows)},
            message='Attendance recorded.',
        )
