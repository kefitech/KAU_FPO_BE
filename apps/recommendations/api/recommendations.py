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
from pathlib import Path

import httpx
from django.conf import settings
from rest_framework import serializers, status
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema

from apps.core.views import TranslatedViewSet
from apps.core.utils.responses import StandardResponse
from apps.core.utils.pagination import StandardPagination
from apps.core.services.translation import t
from apps.core.permissions.rbac import IsAdmin

from apps.database.models import FPO, MLModelVersion, CropRecommendation
from apps.recommendations.services import (
    get_crop_recommendation,
    get_current_financial_year,
    build_recommendation_payload,
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

        # Same payload-building logic used for the actual FastAPI call —
        # stored as the audit snapshot, matching the doc's requirement
        # that input_snapshot capture "district, zone, soil, season at
        # time of request".
        input_snapshot = build_recommendation_payload(fpo, active_model, fy)

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

def _save_model_file(uploaded_file, version_code: str) -> str:
    """
    Saves an uploaded model file into the shared ML_MODELS_DIR folder
    (settings.ML_MODELS_DIR — a sibling folder to both this Django
    project and ml_service/, matching the doc's eventual Docker volume
    plan). Returns a path RELATIVE to that shared root, e.g.
    "v1.0.0/model.pkl" — not an absolute filesystem path — so it stays
    valid no matter where each service mounts the shared volume.

    SECURITY NOTE: any file type is currently accepted (deliberately
    permissive for now, per team decision) — validate/restrict file
    types before this goes anywhere near production. Model files like
    .pkl/.joblib can execute arbitrary code when loaded; only trusted
    admins should ever be able to reach this endpoint (already enforced
    via IsAdmin), and loading should eventually be hardened further.
    """
    models_dir = Path(settings.ML_MODELS_DIR) / version_code
    models_dir.mkdir(parents=True, exist_ok=True)

    dest_path = models_dir / uploaded_file.name
    with open(dest_path, 'wb') as f:
        for chunk in uploaded_file.chunks():
            f.write(chunk)

    return f"{version_code}/{uploaded_file.name}"


class MLModelVersionAdminView(APIView):
    """
    GET  /api/admin/ml-models/  — list all versions
    POST /api/admin/ml-models/  — register a new version, with an
                                   optional file upload ("model_file")
    """
    permission_classes = [IsAdmin]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

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

        data = request.data.copy()
        uploaded_file = request.FILES.get('model_file')

        # If a file was uploaded, save it and use its path — overrides
        # any model_file_path the client tried to send directly.
        if uploaded_file:
            version_code = data.get('version_code')
            if not version_code:
                return StandardResponse.error(
                    t('recommendations.version_code_required', lang),
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            data['model_file_path'] = _save_model_file(uploaded_file, version_code)

        serializer = MLModelVersionSerializer(data=data)
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
    every other version, so no extra logic needed for that part.

    Also notifies the FastAPI service (POST {ML_SERVICE_URL}/reload-model/)
    so it actually loads the newly activated model file — without this,
    activating a version here would only update Django's own records
    and never affect what FastAPI actually predicts with. Notification
    failure does NOT block activation — matches the same graceful-
    degradation philosophy used elsewhere (e.g. recommendation
    fallback): Django's record of "which model is active" is the
    source of truth even if FastAPI is temporarily unreachable.
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

        reload_warning = None
        try:
            response = httpx.post(
                f"{settings.ML_SERVICE_URL}/reload-model/",
                json={
                    'model_file_path': version.model_file_path,
                    'version_code': version.version_code,
                },
                timeout=10.0,
            )
            response.raise_for_status()
        except Exception:
            reload_warning = t('recommendations.model_reload_failed', lang)

        serializer = MLModelVersionSerializer(version)
        data = serializer.data
        if reload_warning:
            data['warning'] = reload_warning

        return StandardResponse.success(
            data=data,
            message=t('recommendations.model_activated', lang),
        )

# ---------------------------------------------------------------------------
# Admin — recommendation feedback (read-only)
# ---------------------------------------------------------------------------

class RecommendationFeedbackSerializer(serializers.ModelSerializer):
    """
    Read-only view of a CropRecommendation for admin feedback review.
    Includes the FPO's name and a flat list of the crops that were
    recommended (pulled from the JSON recommendations field) so an
    admin can see what was rated without opening the full record.
    """
    fpo_name = serializers.CharField(source='fpo.name', read_only=True)
    crops = serializers.SerializerMethodField()

    class Meta:
        model = CropRecommendation
        fields = [
            'id', 'fpo_name', 'financial_year',
            'feedback_rating', 'feedback_comment',
            'crops', 'created_at',
        ]

    def get_crops(self, obj):
        return [item.get('crop') for item in (obj.recommendations or []) if item.get('crop')]


class RecommendationFeedbackAdminViewSet(TranslatedViewSet):
    """
    GET /api/admin/recommendations/feedback/ — list recommendations
    that have farmer feedback (feedback_rating is not null), most
    recent first.

    Read-only by design — admins review feedback here, they don't edit
    it. Wired via an explicit GET-only path() in admin/urls.py.
    """
    queryset = (
        CropRecommendation.objects
        .exclude(feedback_rating__isnull=True)
        .select_related('fpo')
        .order_by('-created_at')
    )
    serializer_class = RecommendationFeedbackSerializer
    permission_classes = [IsAdmin]
    pagination_class = StandardPagination

    list_message = 'recommendations.feedback_list_retrieved'

    @extend_schema(tags=["Admin - Recommendations"])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
