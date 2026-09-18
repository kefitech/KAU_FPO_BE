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
    created_by_name = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()

    class Meta:
        model = TrainingSession
        fields = ['id', 'fpo', 'fpo_name', 'district', 'topic', 'trainer_name', 'date',
                  'duration_hours', 'participants_count', 'venue', 'attendance_count',
                  'created_by_name', 'can_edit']

    def get_attendance_count(self, obj):
        return obj.attendance.filter(attended=True).count()

    def get_created_by_name(self, obj):
        return obj.cbbo.get_full_name() or obj.cbbo.username

    def get_can_edit(self, obj):
        request = self.context.get('request')
        return bool(request and obj.cbbo_id == request.user.id)


class _SessionDetailSerializer(serializers.ModelSerializer):
    fpo_name = serializers.CharField(source='fpo.name', read_only=True)
    attendance = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()

    class Meta:
        model = TrainingSession
        fields = ['id', 'fpo', 'fpo_name', 'topic', 'trainer_name', 'date', 'duration_hours',
                  'participants_count', 'venue', 'attendance', 'created_at', 'updated_at',
                  'created_by_name', 'can_edit']

    def get_attendance(self, obj):
        return [
            {'id': a.id, 'member_name': a.member_name, 'attended': a.attended}
            for a in obj.attendance.all()
        ]

    def get_created_by_name(self, obj):
        return obj.cbbo.get_full_name() or obj.cbbo.username

    def get_can_edit(self, obj):
        request = self.context.get('request')
        return bool(request and obj.cbbo_id == request.user.id)


class _SessionCreateSerializer(serializers.Serializer):
    fpo_application_id = serializers.CharField(max_length=50)
    topic = serializers.CharField(max_length=300)
    trainer_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    date = serializers.DateField()
    duration_hours = serializers.DecimalField(max_digits=4, decimal_places=1, min_value=0.1)
    participants_count = serializers.IntegerField(min_value=0, default=0)
    venue = serializers.CharField(max_length=300, required=False, allow_blank=True)


class _SessionUpdateSerializer(serializers.Serializer):
    topic = serializers.CharField(max_length=300, required=False)
    trainer_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    date = serializers.DateField(required=False)
    duration_hours = serializers.DecimalField(max_digits=4, decimal_places=1, min_value=0.1, required=False)
    participants_count = serializers.IntegerField(min_value=0, required=False)
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

        # Show every session for FPOs within this official's jurisdiction
        # (district/block/state), not just sessions they personally created.
        # Edit/attendance actions remain restricted to the creator -- see
        # `can_edit` on the serializer and the creator check in the detail
        # and attendance views below.
        qs = TrainingSession.objects.filter(is_deleted=False).select_related('fpo', 'cbbo')
        qs = qs.filter(fpo__in=scope_fpo_qs(FPO.objects.filter(is_deleted=False), request.user))

        search = request.query_params.get('search')
        if search:
            from django.db.models import Q
            qs = qs.filter(Q(topic__icontains=search) | Q(fpo__name__icontains=search))

        district = request.query_params.get('district')
        if district:
            qs = qs.filter(fpo__district=district)

        qs = qs.order_by('-date')

        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        data = _SessionListSerializer(page, many=True, context={'request': request}).data
        return paginator.get_paginated_response(data)

    def post(self, request):
        if not is_government_user(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        serializer = _SessionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            fpo_obj = FPO.objects.get(
                application_id=serializer.validated_data['fpo_application_id'],
                is_deleted=False,
            )
        except FPO.DoesNotExist:
            return StandardResponse.error('FPO not found.', status_code=status.HTTP_404_NOT_FOUND)

        fpo = get_fpo_scoped(fpo_obj.id, request.user)
        if not fpo:
            return StandardResponse.error('FPO not found.', status_code=status.HTTP_404_NOT_FOUND)

        session = TrainingSession.objects.create(
            fpo=fpo,
            cbbo=request.user,
            topic=serializer.validated_data['topic'],
            trainer_name=serializer.validated_data.get('trainer_name', ''),
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

        # Anyone in the same jurisdiction can VIEW the session detail.
        session = TrainingSession.objects.filter(
            id=session_id, is_deleted=False
        ).select_related('fpo', 'cbbo').prefetch_related('attendance').first()
        if not session or session.fpo not in scope_fpo_qs(FPO.objects.filter(is_deleted=False), request.user):
            return StandardResponse.error('Session not found.', status_code=status.HTTP_404_NOT_FOUND)

        return StandardResponse.success(data=_SessionDetailSerializer(session, context={'request': request}).data)

    def patch(self, request, session_id):
        if not is_government_user(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        # Editing core session details is restricted to the creator, same
        # boundary as the attendance-set view below. The FPO a session was
        # logged against is intentionally immutable here.
        session = TrainingSession.objects.filter(id=session_id, cbbo=request.user, is_deleted=False).first()
        if not session:
            return StandardResponse.error(
                'Session not found, or you do not have permission to edit it.',
                status_code=status.HTTP_403_FORBIDDEN,
            )

        serializer = _SessionUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        for field, value in serializer.validated_data.items():
            setattr(session, field, value)
        session.save(update_fields=list(serializer.validated_data.keys()) + ['updated_at'])

        return StandardResponse.success(
            data=_SessionDetailSerializer(session, context={'request': request}).data,
            message='Training session updated.',
        )


class GovernmentTrainingAttendanceSetView(APIView):
    def post(self, request, session_id):
        if not is_government_user(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        # Setting attendance is an edit action -- restricted to the session's
        # creator, regardless of jurisdiction visibility.
        session = TrainingSession.objects.filter(id=session_id, cbbo=request.user, is_deleted=False).first()
        if not session:
            return StandardResponse.error(
                'Session not found, or you do not have permission to edit it.',
                status_code=status.HTTP_403_FORBIDDEN,
            )

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