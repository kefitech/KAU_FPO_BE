"""
DPR Admin — FPO-first roll-up endpoints.

Two views:

    GET /api/admin/dpr/projects/fpos/
        Paginated list of every FPO that has at least one DPR project, with
        per-FPO totals (draft / submitted / generated / etc). Powers the
        FPO-first admin table on /admin/dpr/projects.

    GET /api/admin/dpr/projects/fpos/<fpo_id>/
        Drill-down: FPO summary + a 12-month bar-chart series + the FPO's
        DPR projects (unpaginated because a single FPO's list is short).
        Powers /admin/dpr/projects/fpo/<fpo_id>.

Author: Athul Gopan (Kefi Tech Solutions)
"""
from datetime import date
from collections import Counter

from django.db.models import (
    Count, Max, Q,
    Case, When, IntegerField,
)
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.permissions.rbac import IsSubAdminOrSuperAdmin
from apps.core.utils.pagination import StandardPagination
from apps.core.utils.responses import StandardResponse
from apps.database.models import DPRProject, FPO


# ── Helpers ─────────────────────────────────────────────────────────────────

def _last_n_month_keys(n: int) -> list[str]:
    """Return the last N `YYYY-MM` keys, oldest first, ending at current month."""
    today = date.today()
    year, month = today.year, today.month
    out: list[str] = []
    for _ in range(n):
        out.append(f'{year:04d}-{month:02d}')
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return list(reversed(out))


def _fpo_rollup(fpo: FPO, aggregates: dict) -> dict:
    """Shape one FPO for the roll-up table."""
    return {
        'id':        fpo.id,
        'name':      fpo.name,
        'district':  fpo.district or '',
        'tier':      fpo.tier or None,
        'total_dprs':      aggregates.get('total', 0),
        'draft_dprs':      aggregates.get('draft', 0),
        'in_progress_dprs': aggregates.get('in_progress', 0),
        'submitted_dprs':  aggregates.get('submitted', 0),
        'generated_dprs':  aggregates.get('generated', 0),
        'last_updated':    aggregates.get('last_updated'),
    }


# ── List endpoint ───────────────────────────────────────────────────────────

@extend_schema(
    tags=['Admin - DPR Projects'],
    summary='List FPOs that have DPR projects (roll-up)',
    description=(
        'Paginated. One row per FPO that has at least one DPR project, with '
        'per-status counts and the newest updated_at across their DPRs. '
        'Filter with `search` (FPO name contains) or `district`.'
    ),
    parameters=[
        OpenApiParameter('search',   str, description='Case-insensitive substring on FPO name'),
        OpenApiParameter('district', str, description='FPO district code (e.g. TRS)'),
    ],
)
class DPRProjectFpoRollupListView(APIView):
    permission_classes = [IsAuthenticated, IsSubAdminOrSuperAdmin]

    def get(self, request):
        # One SQL aggregate — annotate each FPO with per-status counts and
        # the max updated_at across their DPRs. `dpr_projects` is the reverse
        # accessor (FPO has a related_name of `dpr_projects` on DPRProject via
        # `fpo = FK(FPO, related_name='dpr_projects')`; if not, the accessor
        # is the default `dprproject_set`).
        related = 'dpr_projects' if hasattr(FPO, 'dpr_projects') else 'dprproject_set'
        prefix = f'{related}__'

        qs = (
            FPO.objects
            .filter(**{f'{related}__isnull': False})
            .distinct()
            .annotate(
                total_dprs      = Count(related),
                draft_dprs      = Count(Case(When(**{f'{prefix}status': 'draft'},       then=1), output_field=IntegerField())),
                in_progress_dprs = Count(Case(When(**{f'{prefix}status': 'in_progress'}, then=1), output_field=IntegerField())),
                submitted_dprs  = Count(Case(When(**{f'{prefix}status': 'submitted'},   then=1), output_field=IntegerField())),
                generated_dprs  = Count(Case(When(**{f'{prefix}status': 'generated'},   then=1), output_field=IntegerField())),
                last_updated    = Max(f'{prefix}updated_at'),
            )
            .order_by('-total_dprs', 'name')
        )

        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(name__icontains=search)

        district = request.query_params.get('district', '').strip().upper()
        if district:
            qs = qs.filter(district=district)

        results = [
            {
                'id':               fpo.id,
                'name':             fpo.name,
                'district':         fpo.district or '',
                'tier':             fpo.tier or None,
                'total_dprs':       fpo.total_dprs,
                'draft_dprs':       fpo.draft_dprs,
                'in_progress_dprs': fpo.in_progress_dprs,
                'submitted_dprs':   fpo.submitted_dprs,
                'generated_dprs':   fpo.generated_dprs,
                'last_updated':     fpo.last_updated,
            }
            for fpo in qs
        ]

        paginator = StandardPagination()
        page = paginator.paginate_queryset(results, request)
        return paginator.get_paginated_response(page)


# ── Detail endpoint ─────────────────────────────────────────────────────────

@extend_schema(
    tags=['Admin - DPR Projects'],
    summary='FPO DPR detail (chart series + project list)',
    description=(
        'One FPO plus their DPRs and a monthly-count series covering the '
        'last 12 months for the activity chart. Not paginated — a single '
        'FPO typically has a short DPR list.'
    ),
)
class DPRProjectFpoRollupDetailView(APIView):
    permission_classes = [IsAuthenticated, IsSubAdminOrSuperAdmin]

    def get(self, request, fpo_id: int):
        try:
            fpo = FPO.objects.get(pk=fpo_id)
        except FPO.DoesNotExist:
            return StandardResponse.error('FPO not found', status_code=404)

        projects = list(
            DPRProject.objects
            .filter(fpo=fpo)
            .order_by('-updated_at')
        )

        # Bar-chart series — count created_at by YYYY-MM over the last 12
        # months so quiet months still render as zero bars, not gaps.
        month_keys = _last_n_month_keys(12)
        counts = Counter(f'{p.created_at.year:04d}-{p.created_at.month:02d}' for p in projects)
        monthly = [{'month': k, 'count': counts.get(k, 0)} for k in month_keys]

        by_status: dict[str, int] = {}
        for p in projects:
            by_status[p.status] = by_status.get(p.status, 0) + 1

        data = {
            'fpo': {
                'id':             fpo.id,
                'name':           fpo.name,
                'application_id': fpo.application_id,
                'district':       fpo.district or '',
                'tier':           fpo.tier or None,
                'office_email':   fpo.office_email or '',
                'office_phone':   fpo.office_phone or '',
                'total_members':  fpo.total_members or 0,
            },
            'stats': {
                'total_dprs':     len(projects),
                'by_status':      by_status,
                'generated_dprs': by_status.get('generated', 0),
            },
            'monthly_counts': monthly,
            'projects': [
                {
                    'uuid':       str(p.uuid),
                    'title':      p.title,
                    'status':     p.status,
                    'created_at': p.created_at,
                    'updated_at': p.updated_at,
                }
                for p in projects
            ],
        }
        return StandardResponse.success(data, 'FPO DPR detail retrieved')
