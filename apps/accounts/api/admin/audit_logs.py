"""
Admin Audit Log API
====================
GET /api/admin/audit-logs/

Read-only paginated list of all audit events with filters.
Super admin and sub admin (with can_view_all_fpos) can access.

Filters:
    action      — filter by action type (e.g. document_upload, fpo_profile_change)
    fpo_id      — all events related to a specific FPO
    user_id     — all events performed by a specific user
    from_date   — start date (YYYY-MM-DD)
    to_date     — end date (YYYY-MM-DD)
"""
from django.db.models import Q
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from rest_framework.filters import OrderingFilter
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import serializers, status
from rest_framework.views import APIView

from apps.core.models.generic import AuditLog
from apps.core.utils.constants import UserRole
from apps.core.utils.pagination import StandardPagination
from apps.core.utils.responses import StandardResponse
from apps.database.models.fpo import FPO, FPODocument

User = get_user_model()


# ─────────────────────────────────────────────────────────────────────────────
# Serializer
# ─────────────────────────────────────────────────────────────────────────────

class AuditLogSerializer(serializers.ModelSerializer):
    performed_by      = serializers.SerializerMethodField()
    action_display    = serializers.CharField(source='get_action_display', read_only=True)
    object_info       = serializers.SerializerMethodField()

    class Meta:
        model  = AuditLog
        fields = [
            'id',
            'action',
            'action_display',
            'performed_by',
            'object_info',
            'changes',
            'ip_address',
            'user_agent',
            'request_path',
            'request_method',
            'created_at',
        ]
        read_only_fields = fields

    def get_performed_by(self, obj):
        if not obj.user:
            return {'id': None, 'name': 'System', 'role': None}
        roles = list(obj.user.groups.values_list('name', flat=True))
        return {
            'id':   obj.user.id,
            'name': f"{obj.user.first_name} {obj.user.last_name}".strip() or obj.user.username,
            'role': roles[0] if roles else None,
        }

    def get_object_info(self, obj):
        if not obj.content_type or not obj.object_id:
            return None
        return {
            'model':  obj.content_type.model,
            'app':    obj.content_type.app_label,
            'id':     obj.object_id,
            'repr':   obj.object_repr,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Permission helpers
# ─────────────────────────────────────────────────────────────────────────────

def _can_view(user):
    if user.groups.filter(name=UserRole.SUPER_ADMIN).exists():
        return True
    if user.groups.filter(name=UserRole.SUB_ADMIN).exists():
        return user.has_perm('accounts.can_view_all_fpos')
    return False


# ─────────────────────────────────────────────────────────────────────────────
# View
# ─────────────────────────────────────────────────────────────────────────────

class AuditLogListView(APIView):
    ordering_fields = ['action', 'created_at']
    ordering = ['-created_at']  # default sort when no `ordering` param is sent
 

    @extend_schema(
        tags=['Admin - Audit Logs'],
        summary='List audit log events',
        description=(
            'Paginated audit trail of all system events. '
            'Supports filtering by action type, FPO, user, and date range.\n\n'
            '**Available action types:**\n'
            '`create`, `update`, `delete`, `soft_delete`, `restore`, '
            '`login`, `logout`, `failed_login`, `password_change`, `password_reset`, '
            '`export`, `import`, `document_upload`, `document_delete`, '
            '`fpo_profile_change`, `fpo_submit`, `fpo_status_change`, '
            '`tier_recalculation`, `fpo_user_invite`, `fpo_user_activate`, `fpo_user_deactivate`'
        ),
        parameters=[
            OpenApiParameter('action',     str, description='Filter by action type'),
            OpenApiParameter('fpo_id',     int, description='Filter by FPO ID — shows all events on that FPO'),
            OpenApiParameter('user_id',    int, description='Filter by user who performed the action'),
            OpenApiParameter('from_date',  str, description='Start date (YYYY-MM-DD)'),
            OpenApiParameter('to_date',    str, description='End date (YYYY-MM-DD)'),
        ],
        responses={200: AuditLogSerializer(many=True)},
    )
    def get(self, request):
        if not _can_view(request.user):
            return StandardResponse.error(
                'Permission denied.',
                status_code=status.HTTP_403_FORBIDDEN,
            )

        qs = AuditLog.objects.select_related(
            'user', 'content_type'
        )

        # Filter: action type
        action = request.query_params.get('action', '').strip()
        if action:
            qs = qs.filter(action=action)

        # Filter: by FPO — find all AuditLog rows related to a specific FPO
        fpo_id = request.query_params.get('fpo_id', '').strip()
        if fpo_id:
            try:
                fpo     = FPO.objects.get(id=fpo_id)
                fpo_ct  = ContentType.objects.get_for_model(FPO)
                doc_ct  = ContentType.objects.get_for_model(FPODocument)
                doc_ids_str = [
                    str(d) for d in
                    FPODocument.objects.filter(fpo=fpo).values_list('id', flat=True)
                ]

                # Direct FPO object logs
                qs_fpo  = qs.filter(content_type=fpo_ct, object_id=str(fpo.id))
                # Document logs for this FPO
                qs_docs = qs.filter(content_type=doc_ct, object_id__in=doc_ids_str)
                # User/other logs that carry fpo_id in their changes JSON
                # (e.g. account_deactivated on ownership transfer, team invites)
                qs_refs = qs.filter(changes__fpo_id=fpo.id)

                qs = (qs_fpo | qs_docs | qs_refs).distinct().order_by('-created_at')
            except (FPO.DoesNotExist, ValueError):
                return StandardResponse.error(
                    'FPO not found.',
                    status_code=status.HTTP_404_NOT_FOUND,
                )

        # Filter: by user
        user_id = request.query_params.get('user_id', '').strip()
        if user_id:
            qs = qs.filter(user_id=user_id)

        # Filter: date range
        from_date = request.query_params.get('from_date', '').strip()
        to_date   = request.query_params.get('to_date', '').strip()
        if from_date:
            qs = qs.filter(created_at__date__gte=from_date)
        if to_date:
            qs = qs.filter(created_at__date__lte=to_date)


        search = request.query_params.get('search', '').strip()
        if search:
            search_terms = search.split()
            search_query = Q()
            for term in search_terms:
                search_query &= (
                    Q(action__icontains=term) |
                    Q(user__first_name__icontains=term) |
                    Q(user__last_name__icontains=term) |
                    Q(user__email__icontains=term) |
                    Q(object_repr__icontains=term)
                )
            qs = qs.filter(search_query)
        qs = OrderingFilter().filter_queryset(request, qs, self)
        # Paginate
        paginator   = StandardPagination()
        page        = paginator.paginate_queryset(qs, request)
        serializer  = AuditLogSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)
