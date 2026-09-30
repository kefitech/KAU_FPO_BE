"""
AI Business Plan API — FPO "Business Plan Guidance" tab.
Endpoints:
    GET  /api/recommendations/business-plan/me/            — cached plan (request language) + profile
    POST /api/recommendations/business-plan/me/generate/   — generate / regenerate via Gemini (sync)

Both return {plan, profile, is_outdated}; `plan` is null until generated.
"""
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.services.translation import t
from apps.core.utils.responses import StandardResponse
from apps.database.models import BusinessPlan
from apps.recommendations.api.recommendations import _get_fpo_or_404
from apps.recommendations.business_plan import (
    BusinessPlanError,
    build_profile,
    generate_business_plan,
    is_outdated,
    normalise_language,
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

        try:
            plan = generate_business_plan(fpo, request.user, lang)
        except BusinessPlanError as e:
            key, status_code = _ERROR_RESPONSES[e.code]
            return StandardResponse.error(t(key, lang), status_code=status_code)

        return StandardResponse.success(
            data=_payload(fpo, plan, lang),
            message=t('recommendations.business_plan_generated', lang),
        )
