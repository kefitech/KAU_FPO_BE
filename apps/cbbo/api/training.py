"""
CBBO - Training Sessions

GET    /api/cbbo/training/                     list sessions (?search=, ?district=, ?topic=)
POST   /api/cbbo/training/                     create one session per selected FPO
GET    /api/cbbo/training/<id>/                session detail with attendance roster
PATCH  /api/cbbo/training/<id>/                edit session details
DELETE /api/cbbo/training/<id>/                soft-delete a session
POST   /api/cbbo/training/<id>/attendance/     replace the attendance roster
POST   /api/cbbo/training/<id>/comments/read/  clear the unread KAU-comment marker for the caller

Mirrors apps/government/api/training.py, with CBBO scoping: an officer sees
and edits only the sessions they created themselves, and only while the FPO
is still inside their current jurisdiction. Sessions created by government
officials or other CBBO officers are not shown.
"""
from django.db import transaction
from django.db.models import Q
from rest_framework import serializers, status
from rest_framework.views import APIView

from apps.core.utils.responses import StandardResponse
from apps.core.utils.pagination import StandardPagination
from apps.core.services.translation import t
from apps.core.services.audit import AuditService
from apps.core.models.generic import AuditLog
from apps.core.utils.validators import validate_not_only_symbols
from apps.core.utils.constants import FPOStatus, MAX_TRAINING_PARTICIPANTS
from apps.database.models.fpo import FPO
from apps.database.models.cbbo import TrainingSession, TrainingAttendance
from apps.cbbo.training_comments import (
    TrainingSessionCommentSerializer, comment_read_map, has_unread_comments, mark_comments_read,
)

from apps.cbbo.api.assignments import is_cbbo_user, is_fpo_assigned, scope_fpo_qs
from apps.cbbo.training_cancel import CancelSessionSerializer, cancel_training_session


# ──────────────────────────────────────────────────────────────────────────────
# Serializers
# ──────────────────────────────────────────────────────────────────────────────
# Same cap as the create/edit forms; the column allows 300 but the UI stops at 200.
TOPIC_MAX_CHARS = 200


class _SessionListSerializer(serializers.ModelSerializer):
    fpo_name = serializers.CharField(source='fpo.name', read_only=True)
    district = serializers.CharField(source='fpo.district', read_only=True)
    attendance_count = serializers.SerializerMethodField()
    attendance_total = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    # KAU admin / sub-admin remarks — shown in the session's view sheet
    comments = TrainingSessionCommentSerializer(source='admin_comments', many=True, read_only=True)
    has_unread_comments = serializers.SerializerMethodField()

    class Meta:
        model = TrainingSession
        fields = ['id', 'fpo', 'fpo_name', 'district', 'topic', 'trainer_name', 'date', 'time',
                  'duration_hours', 'participants_count', 'venue', 'attendance_count',
                  'attendance_total', 'created_by_name', 'can_edit', 'comments', 'has_unread_comments']

    def get_has_unread_comments(self, obj):
        return has_unread_comments(obj, self.context.get('comment_reads', {}))

    def get_attendance_count(self, obj):
        return obj.attendance.filter(attended=True).count()

    def get_attendance_total(self, obj):
        # 0 rows = attendance not recorded yet; rows with none attended = recorded as zero.
        return obj.attendance.count()

    def get_created_by_name(self, obj):
        return obj.cbbo.get_full_name() or obj.cbbo.username

    def get_can_edit(self, obj):
        request = self.context.get('request')
        return bool(request and obj.cbbo_id == request.user.id)


class _SessionDetailSerializer(serializers.ModelSerializer):
    fpo_name = serializers.CharField(source='fpo.name', read_only=True)
    district = serializers.CharField(source='fpo.district', read_only=True)
    attendance = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    comments = TrainingSessionCommentSerializer(source='admin_comments', many=True, read_only=True)

    class Meta:
        model = TrainingSession
        fields = ['id', 'fpo', 'fpo_name', 'district', 'topic', 'trainer_name', 'date', 'time',
                  'duration_hours', 'participants_count', 'venue', 'attendance',
                  'created_at', 'updated_at', 'created_by_name', 'can_edit', 'comments']

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


# Free text must contain a letter or digit, so input made only of symbols ("@#$%") is rejected
class _SessionTextValidationMixin:
    def validate_topic(self, value):
        return validate_not_only_symbols(value, 'Topic')

    def validate_trainer_name(self, value):
        return validate_not_only_symbols(value, 'Trainer name')

    def validate_venue(self, value):
        return validate_not_only_symbols(value, 'Venue')


class _SessionCreateSerializer(_SessionTextValidationMixin, serializers.Serializer):
    # New clients send fpo_application_ids (one session is created per FPO).
    # fpo_id is still accepted so older clients keep working.
    fpo_application_ids = serializers.ListField(
        child=serializers.CharField(max_length=50), required=False, allow_empty=True,
    )
    fpo_id = serializers.IntegerField(required=False)
    topic = serializers.CharField(max_length=TOPIC_MAX_CHARS)
    trainer_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    date = serializers.DateField()
    time = serializers.CharField(max_length=10, required=False, allow_blank=True)
    duration_hours = serializers.DecimalField(max_digits=4, decimal_places=1, min_value=0.1)
    participants_count = serializers.IntegerField(min_value=0, max_value=MAX_TRAINING_PARTICIPANTS, default=0)
    venue = serializers.CharField(max_length=300, required=False, allow_blank=True)

    def validate(self, attrs):
        if not attrs.get('fpo_application_ids') and attrs.get('fpo_id') is None:
            raise serializers.ValidationError({'fpo_application_ids': 'Select at least one FPO.'})
        return attrs


class _SessionEditSerializer(_SessionTextValidationMixin, serializers.Serializer):
    topic = serializers.CharField(max_length=TOPIC_MAX_CHARS, required=False)
    trainer_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    date = serializers.DateField(required=False)
    time = serializers.CharField(max_length=10, required=False, allow_blank=True)
    duration_hours = serializers.DecimalField(max_digits=4, decimal_places=1, min_value=0.1, required=False)
    participants_count = serializers.IntegerField(min_value=0, max_value=MAX_TRAINING_PARTICIPANTS, required=False)
    venue = serializers.CharField(max_length=300, required=False, allow_blank=True)


class _AttendanceRowSerializer(serializers.Serializer):
    member_name = serializers.CharField(max_length=200)
    attended = serializers.BooleanField(default=False)

    def validate_member_name(self, value):
        return validate_not_only_symbols(value, 'Member name')


class _AttendanceSetSerializer(serializers.Serializer):
    attendance = _AttendanceRowSerializer(many=True)


# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────────────
# DataTable column id -> model field, for the `ordering` query param
_ORDERING_FIELDS = {
    'topic': 'topic',
    'fpo_name': 'fpo__name',
    'district': 'fpo__district',
    'date': 'date',
}


def _denied(request):
    return StandardResponse.error(
        t('common.permission_denied', request.language),
        status_code=status.HTTP_403_FORBIDDEN,
    )


def _session_not_found():
    return StandardResponse.error('Session not found.', status_code=status.HTTP_404_NOT_FOUND)


def _not_editable(action='edit'):
    return StandardResponse.error(
        f'Session not found, or you do not have permission to {action} it.',
        status_code=status.HTTP_403_FORBIDDEN,
    )


def _get_session_visible(session_id, user):
    """Own session whose FPO is still inside the caller's current jurisdiction."""
    session = TrainingSession.objects.filter(
        id=session_id, cbbo=user, is_deleted=False,
    ).select_related('fpo', 'cbbo').prefetch_related('attendance', 'admin_comments').first()
    if not session or not is_fpo_assigned(session.fpo, user):
        return None
    return session


def _get_session_owned(session_id, user):
    """Edit boundary: created by the caller, and still inside their jurisdiction."""
    session = _get_session_visible(session_id, user)
    if not session or session.cbbo_id != user.id:
        return None
    return session


def _notify_fpo(fpo, session):
    """
    Same notification the government portal sends when a session is scheduled:
    in-app to the primary user and every active team member, email to the
    primary user.
    """
    from apps.core.services.fpo_permission import fpo_notification_recipients
    from apps.notifications.services import send_notification
    context = {
        'fpo_name': fpo.name,
        'topic': session.topic,
        'trainer_name': session.trainer_name or 'TBD',
        'date': str(session.date),
        'time': session.time or 'TBD',
        'venue': session.venue or 'TBD',
        'link': '/fpo/trainings',
    }
    for member in fpo_notification_recipients(fpo):
        try:
            send_notification(user=member, code='fpo_training_scheduled', channel='in_app', context=context)
        except Exception:
            pass
    if fpo.primary_user:
        try:
            send_notification(
                user=fpo.primary_user, code='fpo_training_scheduled', channel='email', context=context,
            )
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────────────────────
# Views
# ──────────────────────────────────────────────────────────────────────────────
class TrainingSessionListCreateView(APIView):

    # ── LIST MY TRAINING SESSIONS ────────────────────────────────────────────
    # Own sessions only, and only for FPOs in the caller's CURRENT jurisdiction
    # (a revoked district assignment hides that district's sessions immediately).
    # Optional: ?search=<text>   topic OR FPO name
    #           ?district=<code> FPO district
    #           ?topic=<text>    topic only (kept for older clients)
    #           ?ordering=<column id>, '-' prefix for descending

    def get(self, request):
        if not is_cbbo_user(request.user):
            return _denied(request)

        qs = TrainingSession.objects.filter(cbbo=request.user, is_deleted=False).select_related('fpo', 'cbbo').prefetch_related('admin_comments')
        qs = qs.filter(fpo__in=scope_fpo_qs(FPO.objects.filter(is_deleted=False), request.user))

        search = (request.query_params.get('search') or '').strip()
        if search:
            qs = qs.filter(Q(topic__icontains=search) | Q(fpo__name__icontains=search))

        district = request.query_params.get('district')
        if district:
            qs = qs.filter(fpo__district=district)

        topic = request.query_params.get('topic')
        if topic:
            qs = qs.filter(topic__icontains=topic)

        ordering = request.query_params.get('ordering', '').strip()
        field = _ORDERING_FIELDS.get(ordering.lstrip('-'))
        if field:
            qs = qs.order_by(f'-{field}' if ordering.startswith('-') else field, '-id')
        else:
            qs = qs.order_by('-date', '-id')

        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        data = _SessionListSerializer(
            page, many=True,
            context={'request': request, 'comment_reads': comment_read_map(request.user, page)},
        ).data
        return paginator.get_paginated_response(data)

    # ── CREATE ───────────────────────────────────────────────────────────────
    # One session row is created per selected FPO. FPOs that do not exist or
    # are outside the caller's jurisdiction are skipped and reported back.

    def post(self, request):
        if not is_cbbo_user(request.user):
            return _denied(request)

        ser = _SessionCreateSerializer(data=request.data)
        if not ser.is_valid():
            return StandardResponse.error(ser.errors, status_code=status.HTTP_400_BAD_REQUEST)
        data = ser.validated_data

        fpos, not_found, not_approved = [], [], []
        seen = set()

        for app_id in data.get('fpo_application_ids') or []:
            fpo = FPO.objects.filter(
                application_id=app_id, is_deleted=False,
            ).select_related('primary_user').first()
            if not fpo or not is_fpo_assigned(fpo, request.user):
                not_found.append(app_id)
            elif fpo.status != FPOStatus.APPROVED:
                not_approved.append(app_id)
            elif fpo.id not in seen:
                seen.add(fpo.id)
                fpos.append(fpo)

        if data.get('fpo_id') is not None:
            fpo = FPO.objects.filter(
                id=data['fpo_id'], is_deleted=False,
            ).select_related('primary_user').first()
            if not fpo or not is_fpo_assigned(fpo, request.user):
                not_found.append(str(data['fpo_id']))
            elif fpo.status != FPOStatus.APPROVED:
                not_approved.append(fpo.application_id or str(fpo.id))
            elif fpo.id not in seen:
                seen.add(fpo.id)
                fpos.append(fpo)

        # Sessions can only be scheduled for approved FPOs; drafts / pending applications are skipped
        if not fpos:
            return StandardResponse.error(
                'Training sessions can only be scheduled for approved FPOs.' if not_approved and not not_found
                else 'None of the selected FPOs could be found in your jurisdiction.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        created = []
        with transaction.atomic():
            for fpo in fpos:
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
                created.append((fpo, session))

        for fpo, session in created:
            AuditService.log(
                user=request.user, action=AuditLog.Action.CREATE, instance=session, request=request,
                changes={'fpo_id': fpo.id, 'topic': session.topic, 'date': str(session.date)},
            )
            _notify_fpo(fpo, session)

        session_ids = [session.id for _, session in created]
        message = f'Training session recorded for {len(session_ids)} FPO(s).'
        if not_found:
            message += f" Could not find/access: {', '.join(not_found)}."
        if not_approved:
            message += f" Skipped (not approved): {', '.join(not_approved)}."

        return StandardResponse.success(
            # 'id' is kept for older clients that created a single session.
            data={
                'id': session_ids[0], 'session_ids': session_ids,
                'not_found': not_found, 'not_approved': not_approved,
            },
            message=message,
        )


class TrainingSessionDetailView(APIView):

    def get(self, request, session_id):
        if not is_cbbo_user(request.user):
            return _denied(request)

        session = _get_session_visible(session_id, request.user)
        if not session:
            return _session_not_found()
        return StandardResponse.success(
            data=_SessionDetailSerializer(session, context={'request': request}).data,
        )

    # The FPO a session was logged against is intentionally not editable.
    def patch(self, request, session_id):
        if not is_cbbo_user(request.user):
            return _denied(request)

        session = _get_session_owned(session_id, request.user)
        if not session:
            return _not_editable('edit')

        ser = _SessionEditSerializer(data=request.data, partial=True)
        if not ser.is_valid():
            return StandardResponse.error(ser.errors, status_code=status.HTTP_400_BAD_REQUEST)

        changes = {}
        for field, value in ser.validated_data.items():
            old = getattr(session, field)
            if old != value:
                changes[field] = {'old': str(old), 'new': str(value)}
                setattr(session, field, value)

        if changes:
            session.save(update_fields=list(changes.keys()) + ['updated_at'])
            AuditService.log(
                user=request.user, action=AuditLog.Action.UPDATE, instance=session, request=request,
                changes=changes,
            )

        return StandardResponse.success(
            data=_SessionDetailSerializer(session, context={'request': request}).data,
            message='Training session updated.',
        )

    def delete(self, request, session_id):
        if not is_cbbo_user(request.user):
            return _denied(request)

        session = _get_session_owned(session_id, request.user)
        if not session:
            return _not_editable('delete')

        session.soft_delete(user=request.user)
        AuditService.log(
            user=request.user,
            action=getattr(AuditLog.Action, 'DELETE', AuditLog.Action.UPDATE),
            instance=session, request=request,
            changes={'deleted': True, 'topic': session.topic},
        )
        return StandardResponse.success(message='Training session deleted.')


class TrainingCommentsReadView(APIView):
    """POST — the officer opened this session; clears its unread-comment marker for them."""

    def post(self, request, session_id):
        if not is_cbbo_user(request.user):
            return _denied(request)

        session = _get_session_visible(session_id, request.user)
        if not session:
            return _session_not_found()

        mark_comments_read(request.user, session)
        return StandardResponse.success(message='Comments marked as read.')


class TrainingAttendanceSetView(APIView):
    """Replaces the full attendance roster for a session in one call —
    simpler for the frontend than per-row create/update/delete calls."""

    def post(self, request, session_id):
        if not is_cbbo_user(request.user):
            return _denied(request)

        session = _get_session_owned(session_id, request.user)
        if not session:
            return _not_editable('edit')

        ser = _AttendanceSetSerializer(data=request.data)
        if not ser.is_valid():
            return StandardResponse.error(ser.errors, status_code=status.HTTP_400_BAD_REQUEST)

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

class TrainingSessionCancelView(APIView):
    """POST — cancel my own session with an optional reason; the FPO and its team are notified."""

    def post(self, request, session_id):
        if not is_cbbo_user(request.user):
            return _denied(request)
        session = _get_session_owned(session_id, request.user)
        if not session:
            return _not_editable('cancel')
        ser = CancelSessionSerializer(data=request.data)
        if not ser.is_valid():
            return StandardResponse.error(ser.errors, status_code=status.HTTP_400_BAD_REQUEST)
        reason = ser.validated_data.get('reason', '')
        cancel_training_session(session, request.user, reason)
        AuditService.log(
            user=request.user, action=getattr(AuditLog.Action, 'DELETE', AuditLog.Action.UPDATE),
            instance=session, request=request,
            changes={'cancelled': True, 'topic': session.topic, 'reason': session.cancellation_reason},
        )
        return StandardResponse.success(message='Training session cancelled. The FPO has been notified.')
