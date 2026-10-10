"""
FPO - Training Sessions (read-only)
FPO users view training sessions scheduled for their own FPO by
government officials or CBBOs.
"""
from django.db.models import Q
from django.utils import timezone
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


# The portal role of the official who recorded a session, for the FPO's card.
CREATOR_ROLE_DISPLAY = {
    'government': 'Government official',
    'cbbo': 'CBBO / NGO officer',
    'admin': 'KAU admin',
    'other': 'Official',
}


NO_CREATOR = {'role': 'other', 'detail': '', 'organisation': ''}


def creator_roles(user_ids):
    """
    {user_id: {'role', 'detail', 'organisation'}} for the officials who recorded
    sessions. Government officials: designation and department as detail.
    CBBO officers: designation as detail and their organisation's name and type.
    KAU admins: nothing extra.
    """
    from django.contrib.auth.models import User
    from apps.database.models.cbbo import CBBOAssignment
    from apps.database.models.cbbo_profile import CBBOOfficerProfile
    from apps.database.models.government import GovernmentOfficialProfile

    user_ids = list(user_ids)
    roles = {}
    for profile in GovernmentOfficialProfile.objects.filter(user_id__in=user_ids):
        detail = ', '.join(part for part in (profile.designation, profile.department) if part)
        roles[profile.user_id] = {'role': 'government', 'detail': detail, 'organisation': ''}
    for profile in CBBOOfficerProfile.objects.filter(user_id__in=user_ids).select_related('organisation'):
        org = profile.organisation
        roles.setdefault(profile.user_id, {
            'role': 'cbbo',
            'detail': profile.designation,
            'organisation': f'{org.name} ({org.get_org_type_display()})' if org else '',
        })
    for uid in CBBOAssignment.objects.filter(cbbo_id__in=user_ids).values_list('cbbo_id', flat=True):
        roles.setdefault(uid, {'role': 'cbbo', 'detail': '', 'organisation': ''})
    admin_ids = User.objects.filter(
        pk__in=user_ids, groups__name__in=['super_admin', 'sub_admin'],
    ).values_list('pk', flat=True)
    for uid in admin_ids:
        roles.setdefault(uid, {'role': 'admin', 'detail': '', 'organisation': ''})
    return roles


class _FPOTrainingSessionSerializer(serializers.ModelSerializer):
    conducted_by_name = serializers.SerializerMethodField()
    conducted_by_role = serializers.SerializerMethodField()
    conducted_by_role_display = serializers.SerializerMethodField()
    conducted_by_detail = serializers.SerializerMethodField()
    conducted_by_organisation = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    status_display = serializers.SerializerMethodField()
    cancelled_at = serializers.DateTimeField(source='deleted_at', read_only=True)

    class Meta:
        model = TrainingSession
        fields = [
            'id', 'topic', 'trainer_name', 'date', 'time', 'duration_hours',
            'venue', 'participants_count', 'conducted_by_name', 'conducted_by_role',
            'conducted_by_role_display', 'conducted_by_detail', 'conducted_by_organisation',
            'status', 'status_display', 'cancelled_at', 'cancellation_reason', 'created_at',
        ]

    # A session an official has removed is "cancelled" from the FPO's side;
    # the rest are "completed" once their date has passed, else "upcoming".
    def get_status(self, obj):
        if obj.is_deleted:
            return 'cancelled'
        return 'completed' if obj.date < self.context['today'] else 'upcoming'

    def get_status_display(self, obj):
        return SESSION_STATUS_DISPLAY[self.get_status(obj)]

    def get_conducted_by_name(self, obj):
        return obj.cbbo.get_full_name() or obj.cbbo.username

    def _creator(self, obj):
        return self.context.get('creator_roles', {}).get(obj.cbbo_id, NO_CREATOR)

    def get_conducted_by_role(self, obj):
        return self._creator(obj)['role']

    def get_conducted_by_role_display(self, obj):
        return CREATOR_ROLE_DISPLAY[self._creator(obj)['role']]

    def get_conducted_by_detail(self, obj):
        return self._creator(obj)['detail']

    def get_conducted_by_organisation(self, obj):
        return self._creator(obj)['organisation']


SESSION_STATUS_DISPLAY = {'upcoming': 'Upcoming', 'completed': 'Completed', 'cancelled': 'Cancelled'}


class FPOTrainingSessionListView(APIView):
    """
    GET /api/fpo/training-sessions/
    ?status=upcoming|completed|cancelled — default lists all three.
    ?search=<text> — topic, trainer or venue.
    """

    def get(self, request):
        fpo = _get_fpo(request.user)
        if not fpo:
            return StandardResponse.error(
                'Your account is not linked to an FPO.', status_code=status.HTTP_403_FORBIDDEN,
            )

        today = timezone.localdate()
        qs = TrainingSession.objects.filter(fpo=fpo).select_related('cbbo')

        status_filter = request.query_params.get('status')
        if status_filter == 'cancelled':
            qs = qs.filter(is_deleted=True).order_by('-deleted_at', '-date')
        elif status_filter == 'completed':
            qs = qs.filter(is_deleted=False, date__lt=today).order_by('-date')
        elif status_filter == 'upcoming':
            qs = qs.filter(is_deleted=False, date__gte=today).order_by('date', 'time')
        else:
            qs = qs.order_by('-date')

        search = (request.query_params.get('search') or '').strip()
        if search:
            qs = qs.filter(
                Q(topic__icontains=search) | Q(trainer_name__icontains=search) | Q(venue__icontains=search)
            )

        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        context = {'creator_roles': creator_roles({s.cbbo_id for s in page}), 'today': today}
        data = _FPOTrainingSessionSerializer(page, many=True, context=context).data
        return paginator.get_paginated_response(data)