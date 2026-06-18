"""
Admin Dashboard Stats API
==========================
GET /api/admin/dashboard/stats/

Returns all data needed for the admin dashboard in one call:
- Stat cards (totals)
- Status breakdown
- Tier distribution
- District-wise distribution
- Monthly registration trend (last 12 months)
- Pending actions count (claims, documents)
"""

from datetime import date
from dateutil.relativedelta import relativedelta

from django.db.models import Count, Q
from django.db.models.functions import TruncMonth

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.views import APIView

from apps.core.utils.constants import FPOStatus, District, DISTRICTS_BILINGUAL, UserRole
from apps.core.utils.responses import StandardResponse
from apps.database.models.fpo import FPO, FPODocument, FPOOwnershipClaim, ClaimStatus


def _can_view(user):
    return user.groups.filter(name__in=[UserRole.SUPER_ADMIN, UserRole.SUB_ADMIN]).exists()


class AdminDashboardStatsView(APIView):

    @extend_schema(
        tags=['Admin - Dashboard'],
        summary='Admin dashboard statistics',
        description=(
            'Returns all stats for the admin dashboard in one call:\n\n'
            '- **stat_cards** — total registrations, approved, pending, suspended\n'
            '- **status_breakdown** — count per FPO status\n'
            '- **tier_distribution** — count of A/B/C/D/not-assessed FPOs\n'
            '- **district_distribution** — FPO count per district\n'
            '- **monthly_trend** — registrations per month for last 12 months\n'
            '- **pending_actions** — items needing admin attention\n'
        ),
        responses={200: None},
    )
    def get(self, request):
        if not _can_view(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        fpos = FPO.objects.filter(is_deleted=False)

        # ── Stat Cards ────────────────────────────────────────────────────────
        total        = fpos.count()
        approved     = fpos.filter(status=FPOStatus.APPROVED).count()
        pending      = fpos.filter(status__in=[
            FPOStatus.SUBMITTED, FPOStatus.UNDER_REVIEW, FPOStatus.INFO_REQUIRED
        ]).count()
        draft        = fpos.filter(status=FPOStatus.DRAFT).count()
        rejected     = fpos.filter(status=FPOStatus.REJECTED).count()
        suspended    = fpos.filter(status=FPOStatus.SUSPENDED).count()

        stat_cards = {
            'total_registrations': total,
            'approved_fpos':       approved,
            'pending_applications': pending,
            'draft_fpos':          draft,
            'rejected_fpos':       rejected,
            'suspended_fpos':      suspended,
        }

        # ── Status Breakdown ─────────────────────────────────────────────────
        status_counts = fpos.values('status').annotate(count=Count('id'))
        status_breakdown = {
            row['status']: row['count'] for row in status_counts
        }
        # Ensure all statuses present even if 0
        for s in FPOStatus.values:
            status_breakdown.setdefault(s, 0)

        # ── Tier Distribution ─────────────────────────────────────────────────
        tier_counts = (
            fpos.filter(status=FPOStatus.APPROVED)
            .values('tier')
            .annotate(count=Count('id'))
        )
        tier_distribution = {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'not_assessed': 0}
        for row in tier_counts:
            t = row['tier']
            if t in ('A', 'B', 'C', 'D'):
                tier_distribution[t] = row['count']
            else:
                tier_distribution['not_assessed'] += row['count']

        # ── District Distribution ─────────────────────────────────────────────
        district_counts = (
            fpos.exclude(district='')
            .values('district')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
        district_distribution = []
        for row in district_counts:
            code  = row['district']
            names = DISTRICTS_BILINGUAL.get(code, (code, code))
            district_distribution.append({
                'code':    code,
                'name':    names[0],
                'name_ml': names[1],
                'count':   row['count'],
            })

        # ── Monthly Registration Trend (last 12 months) ───────────────────────
        twelve_months_ago = date.today().replace(day=1) - relativedelta(months=11)
        monthly_qs = (
            fpos.filter(created_at__date__gte=twelve_months_ago)
            .annotate(month=TruncMonth('created_at'))
            .values('month')
            .annotate(count=Count('id'))
            .order_by('month')
        )
        # Build complete 12-month series (fill 0 for months with no registrations)
        monthly_map = {
            row['month'].strftime('%Y-%m'): row['count']
            for row in monthly_qs
        }
        monthly_trend = []
        for i in range(12):
            month_date  = twelve_months_ago + relativedelta(months=i)
            month_key   = month_date.strftime('%Y-%m')
            month_label = month_date.strftime('%b %Y')
            monthly_trend.append({
                'month':  month_key,
                'label':  month_label,
                'count':  monthly_map.get(month_key, 0),
            })

        # ── Pending Actions (items needing attention) ─────────────────────────
        pending_claims    = FPOOwnershipClaim.objects.filter(status=ClaimStatus.PENDING).count()
        unverified_docs   = FPODocument.objects.filter(
            is_deleted=False, is_verified=False,
            fpo__status=FPOStatus.APPROVED,
        ).count()

        pending_actions = {
            'ownership_claims':    pending_claims,
            'unverified_documents': unverified_docs,
            'info_required_fpos':  fpos.filter(status=FPOStatus.INFO_REQUIRED).count(),
        }

        return StandardResponse.success(
            data={
                'stat_cards':           stat_cards,
                'status_breakdown':     status_breakdown,
                'tier_distribution':    tier_distribution,
                'district_distribution': district_distribution,
                'monthly_trend':        monthly_trend,
                'pending_actions':      pending_actions,
            },
            message='Dashboard stats loaded.',
        )
