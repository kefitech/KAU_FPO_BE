from rest_framework import serializers, status
from rest_framework.views import APIView
 
from apps.core.utils.responses import StandardResponse
from apps.core.utils.pagination import StandardPagination
from apps.core.services.translation import t
from apps.core.services.audit import AuditService
from apps.core.models.generic import AuditLog
from apps.database.models.fpo import FPO
from apps.database.models.cbbo import TrainingSession, TrainingAttendance
 
from apps.cbbo.api.assignments import is_cbbo_user, is_fpo_assigned, scope_fpo_qs
 
 
# ──────────────────────────────────────────────────────────────────────────────
# Serializers
# ──────────────────────────────────────────────────────────────────────────────
class _SessionListSerializer(serializers.ModelSerializer):
    fpo_name = serializers.CharField(source='fpo.name', read_only=True)
    district = serializers.CharField(source='fpo.district', read_only=True)
    attendance_count = serializers.SerializerMethodField()
 
    class Meta:
        model  = TrainingSession
        fields = ['id', 'fpo', 'fpo_name', 'district', 'topic', 'date',
                  'duration_hours', 'participants_count', 'venue', 'attendance_count']
 
    def get_attendance_count(self, obj):
        return obj.attendance.filter(attended=True).count()
 
 
class _SessionDetailSerializer(serializers.ModelSerializer):
    fpo_name = serializers.CharField(source='fpo.name', read_only=True)
    attendance = serializers.SerializerMethodField()
 
    class Meta:
        model  = TrainingSession
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
 
 
class _SessionEditSerializer(serializers.Serializer):
    topic = serializers.CharField(max_length=300, required=False)
    date = serializers.DateField(required=False)
    duration_hours = serializers.DecimalField(max_digits=4, decimal_places=1, min_value=0.1, required=False)
    participants_count = serializers.IntegerField(min_value=0, required=False)
    venue = serializers.CharField(max_length=300, required=False, allow_blank=True)
 
 
class _AttendanceRowSerializer(serializers.Serializer):
    member_name = serializers.CharField(max_length=200)
    attended = serializers.BooleanField(default=False)
 
 
class _AttendanceSetSerializer(serializers.Serializer):
    attendance = _AttendanceRowSerializer(many=True)
 
 
# ──────────────────────────────────────────────────────────────────────────────
# Internal helper
# ──────────────────────────────────────────────────────────────────────────────
def _get_session_scoped(session_id, user):
    session = TrainingSession.objects.filter(
        id=session_id, cbbo=user, is_deleted=False,
    ).select_related('fpo').prefetch_related('attendance').first()
    if not session:
        return None
    if not is_fpo_assigned(session.fpo, user):
        return None
    return session
 
 
# ──────────────────────────────────────────────────────────────────────────────
# Views
# ──────────────────────────────────────────────────────────────────────────────
class TrainingSessionListCreateView(APIView):
    
     # ── LIST MY TRAINING SESSIONS ────────────────────────────────────────────
    # Scoped to own sessions only, and to the caller's CURRENT jurisdiction
    # (a revoked district assignment hides that district's sessions immediately).
    # Optional: ?topic=<text> (icontains match)

    def get(self, request):
        if not is_cbbo_user(request.user):
            return StandardResponse.error(
                t('common.permission_denied', request.language),
                status_code=status.HTTP_403_FORBIDDEN,
            )
 
        qs = TrainingSession.objects.filter(
            cbbo=request.user, is_deleted=False,
        ).select_related('fpo')
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
        if not is_cbbo_user(request.user):
            return StandardResponse.error(
                t('common.permission_denied', request.language),
                status_code=status.HTTP_403_FORBIDDEN,
            )
 
        ser = _SessionCreateSerializer(data=request.data)
        if not ser.is_valid():
            return StandardResponse.error(ser.errors, status_code=status.HTTP_400_BAD_REQUEST)
 
        fpo = FPO.objects.filter(id=ser.validated_data['fpo_id'], is_deleted=False).first()
        if not fpo or not is_fpo_assigned(fpo, request.user):
            return StandardResponse.error(t('fpo.fpo_not_found', request.language), status_code=status.HTTP_404_NOT_FOUND)
 
        session = TrainingSession.objects.create(
            fpo=fpo,
            cbbo=request.user,
            topic=ser.validated_data['topic'],
            date=ser.validated_data['date'],
            duration_hours=ser.validated_data['duration_hours'],
            participants_count=ser.validated_data.get('participants_count', 0),
            venue=ser.validated_data.get('venue', ''),
        )
 
        AuditService.log(
            user=request.user, action=AuditLog.Action.CREATE, instance=session, request=request,
            changes={'fpo_id': fpo.id, 'topic': session.topic, 'date': str(session.date)},
        )
 
        return StandardResponse.success(data={'id': session.id}, message='Training session recorded.')
 
 
class TrainingSessionDetailView(APIView):
 
    def get(self, request, session_id):
        session = _get_session_scoped(session_id, request.user)
        if not session:
            return StandardResponse.error(t('fpo.fpo_not_found', request.language), status_code=status.HTTP_404_NOT_FOUND)
        return StandardResponse.success(data=_SessionDetailSerializer(session).data)
 
    def patch(self, request, session_id):
        session = _get_session_scoped(session_id, request.user)
        if not session:
            return StandardResponse.error(t('fpo.fpo_not_found', request.language), status_code=status.HTTP_404_NOT_FOUND)
 
        ser = _SessionEditSerializer(data=request.data)
        if not ser.is_valid():
            return StandardResponse.error(ser.errors, status_code=status.HTTP_400_BAD_REQUEST)
 
        changes = {}
        for field, value in ser.validated_data.items():
            old = getattr(session, field)
            if old != value:
                changes[field] = {'old': str(old), 'new': str(value)}
                setattr(session, field, value)
 
        if changes:
            session.save()
            AuditService.log(
                user=request.user, action=AuditLog.Action.UPDATE, instance=session, request=request, changes=changes,
            )
 
        return StandardResponse.success(data={'id': session.id}, message='Session updated.')
 
 
class TrainingAttendanceSetView(APIView):
    """Replaces the full attendance roster for a session in one call —
    simpler for the frontend than per-row create/update/delete calls."""
 
    def post(self, request, session_id):
        session = _get_session_scoped(session_id, request.user)
        if not session:
            return StandardResponse.error(t('fpo.fpo_not_found', request.language), status_code=status.HTTP_404_NOT_FOUND)
 
        ser = _AttendanceSetSerializer(data=request.data)
        if not ser.is_valid():
            return StandardResponse.error(ser.errors, status_code=status.HTTP_400_BAD_REQUEST)
 
        from django.db import transaction
        with transaction.atomic():
            session.attendance.all().delete()
            rows = [
                TrainingAttendance(
                    session=session,
                    member_name=row['member_name'],
                    attended=row['attended'],
                )
                for row in ser.validated_data['attendance']
            ]
            TrainingAttendance.objects.bulk_create(rows)
 
        AuditService.log(
            user=request.user, action=AuditLog.Action.UPDATE, instance=session, request=request,
            changes={'attendance_rows': len(rows)},
        )
 
        return StandardResponse.success(
            data={'session_id': session.id, 'attendance_count': len(rows)},
            message='Attendance recorded.',
        )
