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
    attendance_total = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()

    class Meta:
        model = TrainingSession
        fields = ['id', 'fpo', 'fpo_name', 'district', 'topic', 'trainer_name', 'date', 'time',
                  'duration_hours', 'participants_count', 'venue', 'attendance_count', 'attendance_total',
                  'created_by_name', 'can_edit']

    def get_attendance_count(self, obj):
        return obj.attendance.filter(attended=True).count()

    def get_attendance_total(self, obj):
        # Distinguishes "attendance not yet recorded" (0 rows exist at all)
        # from "recorded, and zero people attended" (rows exist, none marked).
        return obj.attendance.count()

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
        fields = ['id', 'fpo', 'fpo_name', 'topic', 'trainer_name', 'date', 'time', 'duration_hours',
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
    fpo_application_ids = serializers.ListField(
        child=serializers.CharField(max_length=50), min_length=1
    )
    topic = serializers.CharField(max_length=300)
    trainer_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    date = serializers.DateField()
    time = serializers.CharField(max_length=10, required=False, allow_blank=True)
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
        data = serializer.validated_data

        created_ids = []
        not_found = []

        for app_id in data['fpo_application_ids']:
            try:
                fpo_obj = FPO.objects.get(application_id=app_id, is_deleted=False)
            except FPO.DoesNotExist:
                not_found.append(app_id)
                continue

            fpo = get_fpo_scoped(fpo_obj.id, request.user)
            if not fpo:
                not_found.append(app_id)
                continue

            session = TrainingSession.objects.create(
                fpo=fpo,
                cbbo=request.user,
                topic=data['topic'],
                trainer_name=data.get('trainer_name', ''),
                date=data['date'],
                time=data.get('time', ''),
                duration_hours=data['duration_hours'],
                participants_count=data.get('participants_count', 0),
                venue=data.get('venue', ''),
            )
            created_ids.append(session.id)

            if fpo.primary_user:
                from apps.notifications.services import send_notification
                notify_context = {
                    'fpo_name': fpo.name,
                    'topic': session.topic,
                    'trainer_name': session.trainer_name or 'TBD',
                    'date': str(session.date),
                    'time': session.time or 'TBD',
                    'venue': session.venue or 'TBD',
                }
                try:
                    send_notification(
                        user=fpo.primary_user, code='fpo_training_scheduled', channel='in_app',
                        context=notify_context,
                    )
                except Exception:
                    pass
                try:
                    send_notification(
                        user=fpo.primary_user, code='fpo_training_scheduled', channel='email',
                        context=notify_context,
                    )
                except Exception:
                    pass

        if not created_ids:
            return StandardResponse.error(
                'None of the selected FPOs could be found in your jurisdiction.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        message = f'Training session recorded for {len(created_ids)} FPO(s).'
        if not_found:
            message += f" Could not find/access: {', '.join(not_found)}."

        return StandardResponse.success(
            data={'session_ids': created_ids, 'not_found': not_found}, message=message,
        )


class _SessionUpdateSerializer(serializers.Serializer):
    topic = serializers.CharField(max_length=300, required=False)
    trainer_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    date = serializers.DateField(required=False)
    time = serializers.CharField(max_length=10, required=False, allow_blank=True)
    duration_hours = serializers.DecimalField(max_digits=4, decimal_places=1, min_value=0.1, required=False)
    participants_count = serializers.IntegerField(min_value=0, required=False)
    venue = serializers.CharField(max_length=300, required=False, allow_blank=True)


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

    def delete(self, request, session_id):
        if not is_government_user(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        # Deleting is restricted to the creator, same boundary as edit.
        session = TrainingSession.objects.filter(id=session_id, cbbo=request.user, is_deleted=False).first()
        if not session:
            return StandardResponse.error(
                'Session not found, or you do not have permission to delete it.',
                status_code=status.HTTP_403_FORBIDDEN,
            )

        session.soft_delete(user=request.user)
        return StandardResponse.success(message='Training session deleted.')


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