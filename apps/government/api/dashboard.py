from rest_framework import status
from rest_framework.views import APIView

from apps.core.utils.responses import StandardResponse
from apps.core.services.translation import t
from apps.database.models.fpo import FPO

from apps.government.api.scoping import is_government_user, scope_fpo_qs, get_jurisdiction_scope


class GovernmentDashboardStatsView(APIView):
    """GET /api/government/dashboard/stats/
    Returns FPO counts scoped to the caller's jurisdiction:
      - total: FPO count in scope
      - by_status: {status_display: count}
      - by_district: {district_code: count} — only varies for state-level;
        district-level officials will just see their one district here
    """

    def get(self, request):
        if not is_government_user(request.user):
            return StandardResponse.error(
                t('common.permission_denied', request.language),
                status_code=status.HTTP_403_FORBIDDEN,
            )

        qs = scope_fpo_qs(FPO.objects.all(), request.user)

        by_status = {}
        for fpo in qs.only('status'):
            label = fpo.get_status_display()
            by_status[label] = by_status.get(label, 0) + 1

        by_district = {}
        for fpo in qs.only('district'):
            by_district[fpo.district] = by_district.get(fpo.district, 0) + 1

        return StandardResponse.success(data={
            'total': qs.count(),
            'by_status': by_status,
            'by_district': by_district,
            'jurisdiction_type': 'state' if get_jurisdiction_scope(request.user) == 'ALL' else 'district',
        })