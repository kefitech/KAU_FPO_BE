from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.views import APIView
 
from apps.core.utils.responses import StandardResponse
from apps.core.utils.pagination import StandardPagination
from apps.core.services.translation import t
from apps.core.services.audit import AuditService
from apps.core.models.generic import AuditLog
from apps.core.utils.constants import District, FPOStatus
from apps.core.utils.validators import validate_not_only_symbols
from apps.database.models.fpo import FPO
from apps.database.models.cbbo import CapacityBuildingReport
 
from apps.cbbo.api.assignments import is_cbbo_user, is_fpo_assigned, scope_fpo_qs
 
 
# ──────────────────────────────────────────────────────────────────────────────
# Serializers
# ──────────────────────────────────────────────────────────────────────────────
class _ReportListSerializer(serializers.ModelSerializer):
    fpo_name = serializers.CharField(source='fpo.name', read_only=True)
    district = serializers.CharField(source='fpo.district', read_only=True)
    district_display = serializers.SerializerMethodField()
 
    class Meta:
        model  = CapacityBuildingReport
        fields = ['id', 'fpo', 'fpo_name', 'district', 'district_display', 'date', 'status',
                  'participants_count', 'activities', 'outcomes', 'created_at', 'updated_at']
    def get_district_display(self, obj):
        return obj.fpo.get_district_display()
 
 
class _ReportDetailSerializer(serializers.ModelSerializer):
    fpo_name = serializers.CharField(source='fpo.name', read_only=True)
    cbbo_name = serializers.SerializerMethodField()
 
    class Meta:
        model  = CapacityBuildingReport
        fields = ['id', 'fpo', 'fpo_name', 'cbbo', 'cbbo_name', 'date',
                  'activities', 'participants_count', 'outcomes', 'status',
                  'created_at', 'updated_at']
        read_only_fields = ['cbbo', 'status']
 
    def get_cbbo_name(self, obj):
        return f"{obj.cbbo.first_name} {obj.cbbo.last_name}".strip() or obj.cbbo.username
 
 
# Free text must contain a letter or digit, so input made only of symbols ("@#$%") is rejected
class _ReportTextValidationMixin:
    def validate_activities(self, value):
        return validate_not_only_symbols(value, 'Activities')

    def validate_outcomes(self, value):
        return validate_not_only_symbols(value, 'Outcomes')


class _ReportCreateSerializer(_ReportTextValidationMixin, serializers.Serializer):
    fpo_id = serializers.IntegerField()
    date = serializers.DateField()
    activities = serializers.CharField(min_length=10)
    participants_count = serializers.IntegerField(min_value=0, default=0)
    outcomes = serializers.CharField(required=False, allow_blank=True)
 
 
class _ReportEditSerializer(_ReportTextValidationMixin, serializers.Serializer):
    date = serializers.DateField(required=False)
    activities = serializers.CharField(min_length=10, required=False)
    participants_count = serializers.IntegerField(min_value=0, required=False)
    outcomes = serializers.CharField(required=False, allow_blank=True)
 
 
# ──────────────────────────────────────────────────────────────────────────────
# Internal helper
# ──────────────────────────────────────────────────────────────────────────────
# DataTable column id -> model field, for the `ordering` query param
_ORDERING_FIELDS = {
    'fpo_name': 'fpo__name',
    'district': 'fpo__district',
    'date': 'date',
    'participants_count': 'participants_count',
    'status': 'status',
}


def _get_report_scoped(report_id, user):
    """A CBBO user can only touch their own reports (not another org/rep's),
    and only for FPOs still in their jurisdiction — checked at read time in
    case an assignment was revoked after the report was filed."""
    report = CapacityBuildingReport.objects.filter(id=report_id, cbbo=user, is_deleted=False).select_related('fpo').first()
    if not report:
        return None
    if not is_fpo_assigned(report.fpo, user):
        return None
    return report
 
 
# ──────────────────────────────────────────────────────────────────────────────
# Views
# ──────────────────────────────────────────────────────────────────────────────
class ReportListCreateView(APIView):
    #created by jobin
    #22/8/26
    # ── LIST MY REPORTS ──────────────────────────────────────────────────────
    # Scoped to own reports only, and to the caller's CURRENT jurisdiction
    # (so a revoked district assignment hides that district immediately).
    # Optional: ?status=draft|submitted
    #           ?search=<text>  FPO name, district name, or status
    #           ?ordering=<column id>, '-' prefix for descending
    def get(self, request):
        if not is_cbbo_user(request.user):
            return StandardResponse.error(
                t('common.permission_denied', request.language),
                status_code=status.HTTP_403_FORBIDDEN,
            )
 
        # own reports only, further constrained to current jurisdiction
        qs = CapacityBuildingReport.objects.filter(
            cbbo=request.user, is_deleted=False,
        ).select_related('fpo')
        qs = qs.filter(fpo__in=scope_fpo_qs(FPO.objects.filter(is_deleted=False), request.user))
 
        s = request.query_params.get('status')
        if s:
            qs = qs.filter(status=s)

        search = (request.query_params.get('search') or '').strip()
        if search:
            # district is stored as a code (TSR), so match the search against the label (Thrissur)
            district_codes = [code for code, label in District.choices if search.lower() in label.lower()]
            qs = qs.filter(
                Q(fpo__name__icontains=search)
                | Q(fpo__district__in=district_codes)
                | Q(status__iexact=search)
            )
 
        ordering = request.query_params.get('ordering', '').strip()
        field = _ORDERING_FIELDS.get(ordering.lstrip('-'))
        if field:
            qs = qs.order_by(f'-{field}' if ordering.startswith('-') else field, '-id')
        else:
            qs = qs.order_by('-date', '-id')
 
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        data = _ReportListSerializer(page, many=True).data
        return paginator.get_paginated_response(data)
 
    def post(self, request):
    # ── CREATE A REPORT (DRAFT) ──────────────────────────────────────────────
    # Always created as draft; locking happens via ReportSubmitView.
    # FPO not-found and FPO-outside-jurisdiction return the same 404 so we
    # don't leak which FPO ids exist to out-of-jurisdiction callers.
        if not is_cbbo_user(request.user):
            return StandardResponse.error(
                t('common.permission_denied', request.language),
                status_code=status.HTTP_403_FORBIDDEN,
            )
 
        ser = _ReportCreateSerializer(data=request.data)
        if not ser.is_valid():
            return StandardResponse.error(ser.errors, status_code=status.HTTP_400_BAD_REQUEST)
 
        fpo = FPO.objects.filter(id=ser.validated_data['fpo_id'], is_deleted=False).first()
        if not fpo:
            return StandardResponse.error(t('fpo.fpo_not_found', request.language), status_code=status.HTTP_404_NOT_FOUND)
 
        if not is_fpo_assigned(fpo, request.user):
            # 404, not 403 — don't confirm the FPO exists to an out-of-jurisdiction user
            return StandardResponse.error(t('fpo.fpo_not_found', request.language), status_code=status.HTTP_404_NOT_FOUND)

        # Draft / pending applications aren't operating FPOs yet
        if fpo.status != FPOStatus.APPROVED:
            return StandardResponse.error(
                'Reports can only be filed for approved FPOs.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if ser.validated_data['date'] > timezone.localdate():
            return StandardResponse.error(
                'Report date cannot be in the future.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )
 
        report = CapacityBuildingReport.objects.create(
            fpo=fpo,
            cbbo=request.user,
            date=ser.validated_data['date'],
            activities=ser.validated_data['activities'],
            participants_count=ser.validated_data.get('participants_count', 0),
            outcomes=ser.validated_data.get('outcomes', ''),
            status='draft',
        )
 
        AuditService.log(
            user=request.user, action=AuditLog.Action.CREATE, instance=report, request=request,
            changes={'fpo_id': fpo.id, 'date': str(report.date)},
        )
 
        return StandardResponse.success(
            data={'id': report.id, 'status': report.status},
            message='Report saved as draft.',
        )
 
 
class ReportDetailView(APIView):
 
    # ── GET ONE REPORT ── must be caller's own report and still in jurisdiction
    def get(self, request, report_id):
        report = _get_report_scoped(report_id, request.user)
        if not report:
            return StandardResponse.error(t('fpo.fpo_not_found', request.language), status_code=status.HTTP_404_NOT_FOUND)
        return StandardResponse.success(data=_ReportDetailSerializer(report).data)
    # ── EDIT A REPORT (DRAFT ONLY) ── locked once status='submitted'
    def patch(self, request, report_id):
        report = _get_report_scoped(report_id, request.user)
        if not report:
            return StandardResponse.error(t('fpo.fpo_not_found', request.language), status_code=status.HTTP_404_NOT_FOUND)
 
        if report.status == 'submitted':
            return StandardResponse.error(
                'This report has been submitted and is locked.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )
 
        ser = _ReportEditSerializer(data=request.data)
        if not ser.is_valid():
            return StandardResponse.error(ser.errors, status_code=status.HTTP_400_BAD_REQUEST)

        new_date = ser.validated_data.get('date')
        if new_date and new_date > timezone.localdate():
            return StandardResponse.error(
                'Report date cannot be in the future.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )
 
        changes = {}
        for field, value in ser.validated_data.items():
            old = getattr(report, field)
            if old != value:
                changes[field] = {'old': str(old), 'new': str(value)}
                setattr(report, field, value)
 
        if changes:
            report.save()
            AuditService.log(
                user=request.user, action=AuditLog.Action.UPDATE, instance=report, request=request, changes=changes,
            )
 
        return StandardResponse.success(data={'id': report.id}, message='Report updated.')

    # ── DELETE A REPORT (DRAFT ONLY) ── soft delete; submitted reports are locked
    def delete(self, request, report_id):
        report = _get_report_scoped(report_id, request.user)
        if not report:
            return StandardResponse.error(t('fpo.fpo_not_found', request.language), status_code=status.HTTP_404_NOT_FOUND)

        if report.status == 'submitted':
            return StandardResponse.error(
                'This report has been submitted and is locked.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        report.soft_delete(user=request.user)
        AuditService.log(
            user=request.user, action=AuditLog.Action.SOFT_DELETE, instance=report, request=request,
            changes={'deleted': True, 'fpo_id': report.fpo_id, 'date': str(report.date)},
        )

        return StandardResponse.success(message='Report deleted.')
 
 
class ReportSubmitView(APIView):
      # ── SUBMIT (LOCK) A REPORT ── one-way draft -> submitted transition
 
    def post(self, request, report_id):
        report = _get_report_scoped(report_id, request.user)
        if not report:
            return StandardResponse.error(t('fpo.fpo_not_found', request.language), status_code=status.HTTP_404_NOT_FOUND)
 
        if report.status == 'submitted':
            return StandardResponse.error(
                'Report is already submitted.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )
 
        report.status = 'submitted'
        report.save(update_fields=['status', 'updated_at'])
 
        AuditService.log(
            user=request.user, action=AuditLog.Action.UPDATE, instance=report, request=request,
            changes={'status': 'submitted'},
        )
 
        return StandardResponse.success(data={'id': report.id, 'status': report.status}, message='Report submitted.')
