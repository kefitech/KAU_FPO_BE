"""
CBBO - Dashboard

GET /api/cbbo/dashboard/stats/   training sessions per month, last 12 months

Counts the same sessions the officer's training table lists: their own,
not deleted, for FPOs still inside their current jurisdiction.

`training_trend()` also feeds the government dashboard (apps/government/api/dashboard.py).
"""
from datetime import date

from dateutil.relativedelta import relativedelta
from django.db.models import Count
from django.db.models.functions import TruncMonth
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.views import APIView

from apps.core.services.translation import t
from apps.core.utils.responses import StandardResponse
from apps.database.models.cbbo import TrainingSession
from apps.database.models.fpo import FPO

from apps.cbbo.api.assignments import is_cbbo_user, scope_fpo_qs


def training_trend(sessions):
    """[{month: 'YYYY-MM', count}] — sessions per month by session date, the last
    12 months oldest first, months with no sessions included as 0."""
    first_month = date.today().replace(day=1) - relativedelta(months=11)
    monthly_map = {
        row['month'].strftime('%Y-%m'): row['count']
        for row in (
            sessions.filter(date__gte=first_month)
            .annotate(month=TruncMonth('date'))
            .values('month')
            .annotate(count=Count('id'))
        )
    }
    trend = []
    for i in range(12):
        month_key = (first_month + relativedelta(months=i)).strftime('%Y-%m')
        trend.append({'month': month_key, 'count': monthly_map.get(month_key, 0)})
    return trend


class CBBODashboardStatsView(APIView):

    @extend_schema(
        tags=['CBBO - Dashboard'],
        summary='CBBO dashboard statistics',
        description=(
            '- **training_trend** — sessions recorded per month (by session date) for the '
            'last 12 months, oldest first, months with no sessions included as 0'
        ),
        responses={200: None},
    )
    def get(self, request):
        if not is_cbbo_user(request.user):
            return StandardResponse.error(
                t('common.permission_denied', request.language),
                status_code=status.HTTP_403_FORBIDDEN,
            )

        sessions = TrainingSession.objects.filter(
            cbbo=request.user,
            is_deleted=False,
            fpo__in=scope_fpo_qs(FPO.objects.filter(is_deleted=False), request.user),
        )
        return StandardResponse.success(data={'training_trend': training_trend(sessions)})
