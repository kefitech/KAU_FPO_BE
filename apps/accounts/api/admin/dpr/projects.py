"""
DPR Admin — Projects list endpoint.

GET /api/admin/dpr/projects/ — paginated list of every FPO's DPR project with
filters (status, district, FPO name search).

Read-only for now. Detail view lives in a separate file when built.

Author: Athul Gopan (Kefi Tech Solutions)
"""
from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.permissions.rbac import IsSubAdminOrSuperAdmin
from apps.core.utils.pagination import StandardPagination
from apps.database.models import DPRProject


@extend_schema(
    tags=['Admin - DPR Projects'],
    summary='List DPR projects across all FPOs',
    description=(
        'Paginated. Filter with `status`, `district`, `search` (FPO name / DPR title '
        'contains, case-insensitive). Ordering: newest first.'
    ),
    parameters=[
        OpenApiParameter('status', str, description="Filter by status: draft | in_progress | submitted | generated"),
        OpenApiParameter('district', str, description="FPO district code (e.g. TRS)"),
        OpenApiParameter('search', str, description="Case-insensitive substring match on FPO name or DPR title"),
    ],
)
class DPRProjectAdminListView(APIView):
    permission_classes = [IsAuthenticated, IsSubAdminOrSuperAdmin]

    def get(self, request):
        qs = (
            DPRProject.objects
            .select_related('fpo')
            .order_by('-created_at')
        )

        status_filter = request.query_params.get('status', '').strip()
        if status_filter:
            qs = qs.filter(status=status_filter)

        district = request.query_params.get('district', '').strip().upper()
        if district:
            qs = qs.filter(fpo__district=district)

        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(Q(fpo__name__icontains=search) | Q(title__icontains=search))

        results = [
            {
                'uuid':        str(p.uuid),
                'title':       p.title,
                'status':      p.status,
                'created_at':  p.created_at,
                'updated_at':  p.updated_at,
                'fpo': {
                    'id':       p.fpo_id,
                    'name':     p.fpo.name,
                    'district': p.fpo.district,
                    'tier':     p.fpo.tier,
                } if p.fpo_id else None,
            }
            for p in qs
        ]

        paginator = StandardPagination()
        page = paginator.paginate_queryset(results, request)
        return paginator.get_paginated_response(page)
