"""
AI Business Plan API — FPO "Business Plan Guidance" tab.
Endpoints:
    GET  /api/recommendations/business-plan/me/            — cached plan (request language) + profile
    POST /api/recommendations/business-plan/me/generate/   — generate / regenerate via Gemini (sync)
    GET  /api/recommendations/business-plan/me/pdf/        — download the plan as PDF (DPR report look)
    GET  /api/recommendations/business-plan/me/docx/       — download the plan as an editable Word file

Both return {plan, profile, is_outdated}; `plan` is null until generated.
"""
from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.services.translation import t
from apps.core.utils.responses import StandardResponse
from apps.database.models import BusinessPlan
from apps.recommendations.api.recommendations import _get_fpo_or_404, _require_fpo_action
from apps.recommendations.notifications import notify_business_plan_ready
from apps.recommendations.business_plan import (
    BusinessPlanError,
    build_profile,
    generate_business_plan,
    is_outdated,
    normalise_language,
)
from apps.recommendations.business_plan_export import (
    build_filename,
    render_business_plan_docx,
    render_business_plan_pdf,
)


class BusinessPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessPlan
        fields = [
            'id', 'language', 'financial_year', 'content',
            'provider', 'model_used', 'generated_at',
        ]


def _payload(fpo, plan, lang):
    return {
        'plan': BusinessPlanSerializer(plan).data if plan else None,
        'profile': build_profile(fpo, lang),
        'is_outdated': is_outdated(plan, fpo) if plan else False,
    }


_ERROR_RESPONSES = {
    BusinessPlanError.NO_COMMODITY: ('recommendations.business_plan_no_commodity', status.HTTP_400_BAD_REQUEST),
    BusinessPlanError.SERVICE_UNAVAILABLE: (
        'recommendations.business_plan_service_unavailable', status.HTTP_503_SERVICE_UNAVAILABLE,
    ),
    BusinessPlanError.GENERATION_FAILED: (
        'recommendations.business_plan_generation_failed', status.HTTP_503_SERVICE_UNAVAILABLE,
    ),
}


class MyBusinessPlanView(APIView):
    """GET /api/recommendations/business-plan/me/ — the FPO's plan in the request language."""
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Recommendations"])
    def get(self, request, *args, **kwargs):
        lang = request.language

        fpo, err = _get_fpo_or_404(request.user, lang)
        if err:
            return err

        plan = BusinessPlan.objects.filter(fpo=fpo, language=normalise_language(lang)).first()
        return StandardResponse.success(
            data=_payload(fpo, plan, lang),
            message=t('recommendations.business_plan_retrieved', lang),
        )


class GenerateBusinessPlanView(APIView):
    """POST /api/recommendations/business-plan/me/generate/ — synchronous Gemini call (~20-60 s)."""
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Recommendations"])
    def post(self, request, *args, **kwargs):
        lang = request.language

        fpo, err = _get_fpo_or_404(request.user, lang)
        if err:
            return err
        err = _require_fpo_action(
            request.user, fpo, 'can_generate_business_plan',
            'You do not have permission to generate a business plan.',
        )
        if err:
            return err

        try:
            plan = generate_business_plan(fpo, request.user, lang)
        except BusinessPlanError as e:
            key, status_code = _ERROR_RESPONSES[e.code]
            return StandardResponse.error(t(key, lang), status_code=status_code)

        # The plan belongs to the FPO: tell the primary user and, if a
        # different member generated it, that member too.
        notify_business_plan_ready(fpo, plan, request.user)

        return StandardResponse.success(
            data=_payload(fpo, plan, lang),
            message=t('recommendations.business_plan_generated', lang),
        )


class _BusinessPlanDownloadView(APIView):
    """
    Download the saved plan (request language) as a file. Any member of the
    FPO can download — it's a read of the plan already shown on the tab.
    Subclasses set `ext`, `content_type` and `render`.
    """
    permission_classes = [IsAuthenticated]
    ext = ''
    content_type = ''

    def render(self, plan) -> bytes:
        raise NotImplementedError

    def get(self, request, *args, **kwargs):
        lang = request.language

        fpo, err = _get_fpo_or_404(request.user, lang)
        if err:
            return err

        plan = (
            BusinessPlan.objects.select_related('fpo')
            .filter(fpo=fpo, language=normalise_language(lang)).first()
        )
        if not plan or not plan.content:
            return StandardResponse.error(
                'Generate a business plan before downloading it.',
                status_code=status.HTTP_404_NOT_FOUND,
            )

        data = self.render(plan)
        response = HttpResponse(data, content_type=self.content_type)
        response['Content-Disposition'] = f'attachment; filename="{build_filename(plan, self.ext)}"'
        response['Content-Length'] = str(len(data))
        return response


class BusinessPlanPdfView(_BusinessPlanDownloadView):
    """GET /api/recommendations/business-plan/me/pdf/"""
    ext = 'pdf'
    content_type = 'application/pdf'

    def render(self, plan):
        return render_business_plan_pdf(plan)

    @extend_schema(tags=["Recommendations"], summary='Download the business plan (PDF)', responses={200: bytes})
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class BusinessPlanDocxView(_BusinessPlanDownloadView):
    """GET /api/recommendations/business-plan/me/docx/"""
    ext = 'docx'
    content_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'

    def render(self, plan):
        return render_business_plan_docx(plan)

    @extend_schema(tags=["Recommendations"], summary='Download the business plan (Word)', responses={200: bytes})
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
