from rest_framework import serializers, status
from rest_framework.views import APIView
 
from apps.core.utils.responses import StandardResponse
from apps.core.utils.pagination import StandardPagination
from apps.core.services.translation import t
from apps.core.services.audit import AuditService
from apps.core.models.generic import AuditLog
from apps.database.models.fpo import FPO
from apps.database.models.cbbo import CapacityBuildingReport
 
from apps.cbbo.api.assignments import is_cbbo_user, is_fpo_assigned, scope_fpo_qs
 
 
# ──────────────────────────────────────────────────────────────────────────────
# Serializers
# ──────────────────────────────────────────────────────────────────────────────
class _ReportListSerializer(serializers.ModelSerializer):
    fpo_name = serializers.CharField(source='fpo.name', read_only=True)
    district = serializers.CharField(source='fpo.district', read_only=True)
 
    class Meta:
        model  = CapacityBuildingReport
        fields = ['id', 'fpo', 'fpo_name', 'district', 'date', 'status',
                  'participants_count', 'created_at']
 
 
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
 
 
class _ReportCreateSerializer(serializers.Serializer):
    fpo_id = serializers.IntegerField()
    date = serializers.DateField()
    activities = serializers.CharField(min_length=10)
    participants_count = serializers.IntegerField(min_value=0, default=0)
    outcomes = serializers.CharField(required=False, allow_blank=True)
 
 
class _ReportEditSerializer(serializers.Serializer):
    date = serializers.DateField(required=False)
    activities = serializers.CharField(min_length=10, required=False)
    participants_count = serializers.IntegerField(min_value=0, required=False)
    outcomes = serializers.CharField(required=False, allow_blank=True)
 
 
# ──────────────────────────────────────────────────────────────────────────────
# Internal helper
# ──────────────────────────────────────────────────────────────────────────────
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
 
        qs = qs.order_by('-date')
 
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
