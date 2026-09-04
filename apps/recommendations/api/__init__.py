"""
Crop Recommendations API — P2-06
Endpoints:
    GET  /api/recommendations/me/              — FPO's current year recommendation (DB cache)
    POST /api/recommendations/me/request/      — request fresh recommendation (calls FastAPI)
    POST /api/recommendations/me/feedback/     — FPO submits 1-5 rating + comment

    GET  /api/admin/ml-models/                 — list all ML model versions (admin only)
    POST /api/admin/ml-models/                 — register new model version
    POST /api/admin/ml-models/{id}/activate/   — set as active model
"""
from rest_framework import serializers, status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema

from apps.core.utils.responses import StandardResponse
from apps.core.services.translation import t
from apps.core.permissions.rbac import IsAdmin

from apps.database.models import FPO, MLModelVersion, CropRecommendation
from apps.recommendations.services import (
    get_crop_recommendation,
    get_current_financial_year,
)


# ---------------------------------------------------------------------------
# Helper — mirrors _get_fpo_or_404 convention from apps/fpo/api/documents.py
# ---------------------------------------------------------------------------

def _get_fpo_or_404(user, lang):
    try:
        return FPO.objects.get(primary_user=user), None
    except FPO.DoesNotExist:
        return None, StandardResponse.error(
            t('recommendations.fpo_not_found', lang),
            status_code=status.HTTP_404_NOT_FOUND,
        )


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------

class CropRecommendationSerializer(serializers.ModelSerializer):
    class Meta:
        model = CropRecommendation
        fields = [
            'id', 'financial_year', 'input_snapshot', 'recommendations',
            'feedback_rating', 'feedback_comment', 'created_at',
        ]


class MLModelVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MLModelVersion
        fields = [
            'id', 'version_code', 'description', 'is_active',
            'deployed_at', 'model_file_path',
        ]


# ---------------------------------------------------------------------------
# FPO-facing endpoints
# ---------------------------------------------------------------------------

class MyRecommendationView(APIView):
    """GET /api/recommendations/me/ — cached recommendation for the current FY."""
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Recommendations"])
    def get(self, request, *args, **kwargs):
        lang = request.language

        fpo, err = _get_fpo_or_404(request.user, lang)
        if err:
            return err

        fy = get_current_financial_year()
        rec = CropRecommendation.objects.filter(fpo=fpo, financial_year=fy).first()

        if not rec:
            return StandardResponse.error(
                t('recommendations.not_found', lang),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        serializer = CropRecommendationSerializer(rec)
        return StandardResponse.success(
            data=serializer.data,
            message=t('recommendations.retrieved', lang),
        )


class RequestRecommendationView(APIView):
    """POST /api/recommendations/me/request/ — triggers a fresh FastAPI call."""
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Recommendations"])
    def post(self, request, *args, **kwargs):
        lang = request.language

        fpo, err = _get_fpo_or_404(request.user, lang)
        if err:
            return err

        active_model = MLModelVersion.objects.filter(is_active=True).first()
        if not active_model:
            return StandardResponse.error(
                t('recommendations.no_active_model', lang),
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        fy = get_current_financial_year()
        result = get_crop_recommendation(fpo, active_model, fy)

        input_snapshot = {
            'district': fpo.district,
            'agro_zone': getattr(fpo, 'agro_zone', None),
            'financial_year': fy,
        }

        rec, _created = CropRecommendation.objects.update_or_create(
            fpo=fpo,
            financial_year=fy,
            defaults={
                'model_version': active_model,
                'input_snapshot': input_snapshot,
                'recommendations': result.get('recommendations', []),
            },
        )

        serializer = CropRecommendationSerializer(rec)
        data = serializer.data
        if result.get('cached'):
            data['warning'] = result.get('warning', t('recommendations.service_unavailable', lang))

        return StandardResponse.success(
            data=data,
            message=t('recommendations.requested', lang),
        )


class RecommendationFeedbackView(APIView):
    """POST /api/recommendations/me/feedback/ — {rating: 1-5, comment: str}"""
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Recommendations"])
    def post(self, request, *args, **kwargs):
        lang = request.language

        fpo, err = _get_fpo_or_404(request.user, lang)
        if err:
            return err

        rating = request.data.get('rating')
        comment = request.data.get('comment', '')

        try:
            rating = int(rating)
        except (TypeError, ValueError):
            rating = None

        if rating is None or not (1 <= rating <= 5):
            return StandardResponse.error(
                t('recommendations.invalid_rating', lang),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        fy = get_current_financial_year()
        rec = CropRecommendation.objects.filter(fpo=fpo, financial_year=fy).first()

        if not rec:
            return StandardResponse.error(
                t('recommendations.not_found', lang),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        rec.feedback_rating = rating
        rec.feedback_comment = comment
        rec.save(update_fields=['feedback_rating', 'feedback_comment'])

        serializer = CropRecommendationSerializer(rec)
        return StandardResponse.success(
            data=serializer.data,
            message=t('recommendations.feedback_saved', lang),
        )


# ---------------------------------------------------------------------------
# Admin — ML model version management
# ---------------------------------------------------------------------------

class MLModelVersionAdminView(APIView):
    """
    GET  /api/admin/ml-models/  — list all versions
    POST /api/admin/ml-models/  — register a new version
    """
    permission_classes = [IsAdmin]

    @extend_schema(tags=["Admin - ML Models"])
    def get(self, request, *args, **kwargs):
        lang = request.language
        versions = MLModelVersion.objects.all().order_by('-deployed_at')
        serializer = MLModelVersionSerializer(versions, many=True)
        return StandardResponse.success(
            data=serializer.data,
            message=t('recommendations.models_retrieved', lang),
        )

    @extend_schema(tags=["Admin - ML Models"])
    def post(self, request, *args, **kwargs):
        lang = request.language
        serializer = MLModelVersionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return StandardResponse.success(
            data=serializer.data,
            message=t('recommendations.model_registered', lang),
            status_code=status.HTTP_201_CREATED,
        )


class MLModelVersionActivateView(APIView):
    """
    POST /api/admin/ml-models/{id}/activate/
    Sets this version active. MLModelVersion.save() already deactivates
    every other version, so no extra logic needed here.
    """
    permission_classes = [IsAdmin]

    @extend_schema(tags=["Admin - ML Models"])
    def post(self, request, pk, *args, **kwargs):
        lang = request.language
        try:
            version = MLModelVersion.objects.get(pk=pk)
        except MLModelVersion.DoesNotExist:
            return StandardResponse.error(
                t('recommendations.model_not_found', lang),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        version.is_active = True
        version.save()  # triggers the model's own save() deactivation logic

        serializer = MLModelVersionSerializer(version)
        return StandardResponse.success(
            data=serializer.data,
            message=t('recommendations.model_activated', lang),
        )