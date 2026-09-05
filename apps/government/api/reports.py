"""
Government - District-level FPO Report Export (PDF/Excel)
GET /api/government/reports/fpo-summary/
Reuses the exact Excel/PDF generation logic from the admin report endpoint,
scoped to the requesting official's jurisdiction.
"""
from datetime import datetime

from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import status
from rest_framework.views import APIView
from django.http import HttpResponse

from apps.core.utils.responses import StandardResponse
from apps.database.models.fpo import FPO

from apps.accounts.api.admin.reports import _build_queryset, _rows, _generate_excel, _generate_pdf

from apps.government.api.scoping import is_government_user, scope_fpo_qs


class GovernmentFPOReportView(APIView):
    @extend_schema(
        tags=['Government - Reports'],
        parameters=[
            OpenApiParameter('file_format', description='excel or pdf (default: excel)', required=False, type=str),
            OpenApiParameter('status', description='FPO status filter', required=False, type=str),
            OpenApiParameter('tier', description='Tier A/B/C/D', required=False, type=str),
            OpenApiParameter('from_date', description='YYYY-MM-DD', required=False, type=str),
            OpenApiParameter('to_date', description='YYYY-MM-DD', required=False, type=str),
        ],
        responses={200: None},
    )
    def get(self, request):
        if not is_government_user(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        fmt = request.query_params.get('file_format', 'excel').lower().strip()
        if fmt not in ('excel', 'pdf'):
            return StandardResponse.error(
                'file_format must be excel or pdf.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        qs = _build_queryset(request.query_params)
        qs = scope_fpo_qs(qs, request.user)
        rows = _rows(qs)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')

        if fmt == 'excel':
            buf = _generate_excel(rows, title='District FPO Report')
            filename = f'government_fpo_report_{ts}.xlsx'
            response = HttpResponse(
                buf.read(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            )
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response

        buf = _generate_pdf(rows)
        filename = f'government_fpo_report_{ts}.pdf'
        response = HttpResponse(buf.read(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
