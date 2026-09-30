"""
Crop Recommendations API — P2-06
Endpoints:
    GET  /api/recommendations/me/              — FPO's current year recommendation (DB cache)
    POST /api/recommendations/me/request/      — request fresh recommendation (calls FastAPI)
    POST /api/recommendations/me/feedback/     — FPO submits 1-5 rating + comment

    GET  /api/admin/ml-models/                 — list all ML model versions (admin only)
    POST /api/admin/ml-models/                 — register new model version (file validated by ML service first)
    POST /api/admin/ml-models/retrain/         — upload a dataset CSV; returns 202, a Celery task trains it
    POST /api/admin/ml-models/{id}/activate/   — set as active model (ready versions only)
    GET  /api/admin/recommendations/feedback/  — list every farmer feedback submission (history)

    GET  /api/recommendations/internal/active-model/ — ML service only (shared token): active version
"""
import hmac
import json
import uuid
from pathlib import Path
from django.utils import timezone
import httpx
from django.conf import settings
from rest_framework import serializers, status, filters
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from drf_spectacular.utils import extend_schema

from django.contrib.gis.geos import GEOSException, GEOSGeometry
from django.db.models import Q

from apps.core.views import TranslatedViewSet
from apps.core.utils.responses import StandardResponse
from apps.core.utils.pagination import StandardPagination
from apps.core.services.translation import t
from apps.core.permissions.rbac import IsAdmin
from apps.core.models.generic import AuditLog
from apps.core.services.audit import AuditService

from apps.core.services.fpo_permission import get_member_fpo
from apps.database.models import (
    FPO, MLModelVersion, CropRecommendation, CropPackageOfPractices, RecommendationFeedback,
)
from apps.recommendations.api.pop_admin import CropPackageOfPracticesSerializer
from apps.recommendations.services import (
    get_crop_recommendation,
    get_current_financial_year,
    build_recommendation_payload,
)
from apps.gis_module.api.cultivation_area import _compute_hectares
from apps.gis_module.services import (
    find_soil_region_for_point,
    find_zone_for_point,
    get_current_season,
    get_weather_for_point,
    resolve_fpo_zone,
    reverse_geocode_address,
)
from apps.recommendations.tasks import (
    generate_crop_recommendation_task,
    retrain_model_task,
    TRAINING_DESCRIPTION_PLACEHOLDER,
    DATASET_FILENAME,
)


# ---------------------------------------------------------------------------
# Helper — mirrors _get_fpo_or_404 convention from apps/fpo/api/documents.py
# ---------------------------------------------------------------------------

def _get_fpo_or_404(user, lang):
    fpo = get_member_fpo(user)
    if fpo is not None:
        return fpo, None
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
            'id', 'financial_year', 'status', 'input_snapshot', 'recommendations',
            'feedback_rating', 'feedback_comment', 'created_at',
        ]


class MLModelVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MLModelVersion
        fields = [
            'id', 'version_code', 'description', 'is_active',
            'deployed_at', 'model_file_path', 'training_metrics',
            'status', 'training_error',
        ]
        # The retrain flow sets these itself; a client can't claim a
        # version is ready or write its own error text. deployed_at is
        # always stamped by the server (timezone.now()) at creation time --
        # see MLModelVersionAdminView.post() and MLModelRetrainView.post() --
        # never taken from client input, so "deployment date" can't drift
        # from when the version was actually registered/queued.
        read_only_fields = ['status', 'training_error', 'training_metrics', 'deployed_at']


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


class CropPackageOfPracticesDetailView(APIView):
    """
    GET /api/recommendations/pop/?crop_name=Cashew — case-insensitive lookup.

    Query param rather than a path param: several crop names contain spaces
    ("French bean", "Green gram"), and this matches the ?search= / ?category=
    filter convention used across the admin APIs.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Recommendations"])
    def get(self, request, *args, **kwargs):
        lang = request.language
        crop_name = (request.query_params.get('crop_name') or '').strip()
        if not crop_name:
            return StandardResponse.error(
                t('recommendations.pop_crop_name_required', lang),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        pop = CropPackageOfPractices.objects.filter(
            crop_name__iexact=crop_name, is_active=True, is_deleted=False
        ).first()
        if not pop:
            return StandardResponse.error(
                t('recommendations.pop_not_found', lang),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        return StandardResponse.success(
            data=CropPackageOfPracticesSerializer(pop).data,
            message=t('recommendations.pop_retrieved', lang),
        )


class _RequestRecommendationSerializer(serializers.Serializer):
    """
    Optional manual overrides for a recommendation request. Left unset (or
    null), season auto-detects the same way it always has
    (apps.gis_module.services.get_current_season()) and soil_ph falls back
    to the resolved soil category's book-documented pH-range midpoint
    (see ml_service/main.py) — both are purely opt-in overrides, not
    required fields.
    """
    season = serializers.ChoiceField(
        choices=['southwest_monsoon', 'northeast_monsoon', 'dry_season'],
        required=False,
        allow_null=True,
        default=None,
        help_text='Optional manual season override. Defaults to auto-detected season if omitted.',
    )
    soil_ph = serializers.FloatField(
        required=False,
        allow_null=True,
        default=None,
        min_value=3.0,
        max_value=10.0,
        help_text='Optional manual soil pH override (the FPO\'s actual measured value). '
                   'Defaults to an estimate from the resolved soil type if omitted.',
    )


class RequestRecommendationView(APIView):
    """
    POST /api/recommendations/me/request/
    Accepts the request immediately and dispatches a Celery task to do
    the actual FastAPI call + save + notify — does NOT wait for FastAPI.
    Returns 202 Accepted with the pending record, matching the async
    dispatch pattern this project already uses for notification
    delivery (apps/notifications/services.py).
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Recommendations"])
    def post(self, request, *args, **kwargs):
        lang = request.language

        fpo, err = _get_fpo_or_404(request.user, lang)
        if err:
            return err

        ser = _RequestRecommendationSerializer(data=request.data)
        if not ser.is_valid():
            return StandardResponse.error(str(ser.errors), status_code=status.HTTP_400_BAD_REQUEST)
        season_override = ser.validated_data.get('season')
        ph_override = ser.validated_data.get('soil_ph')

        # Reject up front, synchronously, if the FPO's location doesn't fall
        # inside any Kerala agro-climatic zone -- resolve_fpo_zone() is a
        # cheap local PostGIS query (not an external call), so there's no
        # reason to pay for a DB write + Celery round-trip + worker pickup
        # just to discover this asynchronously, the way it used to. No
        # CropRecommendation row is touched here, so a previously valid
        # cached recommendation (if any) is left untouched too.
        if resolve_fpo_zone(fpo) is None:
            return StandardResponse.error(
                t('recommendations.outside_kerala', lang),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        active_model = MLModelVersion.objects.filter(is_active=True).first()
        if not active_model:
            return StandardResponse.error(
                t('recommendations.no_active_model', lang),
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        fy = get_current_financial_year()

        # Mark as 'pending' immediately — the actual FastAPI call happens in
        # the Celery task, not here. Deliberately does NOT clear
        # input_snapshot/recommendations on an existing row: if this refresh
        # ends up falling back to a cached result (ML service unavailable —
        # see get_crop_recommendation()), the task relies on this row still
        # holding the last successfully generated recommendation + its
        # location_snapshot to fall back to. Clearing it here would destroy
        # that before the task ever runs, leaving nothing to show on failure.
        existing = CropRecommendation.objects.filter(fpo=fpo, financial_year=fy).first()
        if existing:
            existing.model_version = active_model
            existing.status = CropRecommendation.Status.PENDING
            # This is a NEW generation request -- any feedback the FPO gave
            # on the PREVIOUS recommendation no longer applies to whatever
            # comes back this time, so it must not carry over. Without this,
            # the frontend (which shows "Thanks for your feedback" purely
            # from feedback_rating being set, see crop-recommendation-
            # display.tsx) kept showing that state for a recommendation the
            # FPO hadn't actually rated yet, since this row is reused
            # (unique_together fpo+financial_year) rather than replaced.
            existing.feedback_rating = None
            existing.feedback_comment = ''
            existing.save(update_fields=['model_version', 'status', 'feedback_rating', 'feedback_comment'])
            rec, _created = existing, False
        else:
            rec = CropRecommendation.objects.create(
                fpo=fpo,
                financial_year=fy,
                model_version=active_model,
                input_snapshot={},
                recommendations=[],
                status=CropRecommendation.Status.PENDING,
            )
            _created = True

        AuditService.log(
            user=request.user,
            action=AuditLog.Action.CREATE if _created else AuditLog.Action.UPDATE,
            instance=rec,
            request=request,
            changes={
                'fpo': fpo.name, 'financial_year': fy, 'model_version': active_model.version_code,
                'season_override': season_override, 'ph_override': ph_override,
            },
        )

        generate_crop_recommendation_task.delay(fpo.pk, active_model.pk, fy, season_override, ph_override)

        serializer = CropRecommendationSerializer(rec)
        return StandardResponse.success(
            data=serializer.data,
            message=t('recommendations.requested', lang),
            status_code=status.HTTP_202_ACCEPTED,
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

        # One submission per generated recommendation -- feedback_rating is
        # cleared when the FPO requests a fresh one, which reopens feedback.
        if rec.feedback_rating is not None:
            return StandardResponse.error(
                t('recommendations.feedback_already_submitted', lang),
                status_code=status.HTTP_409_CONFLICT,
            )

        rec.feedback_rating = rating
        rec.feedback_comment = comment
        rec.save(update_fields=['feedback_rating', 'feedback_comment'])
        # rec's own feedback fields only hold the latest submission (and are
        # cleared on the next request), so keep every submission for admin.
        RecommendationFeedback.objects.create(
            recommendation=rec,
            fpo=fpo,
            model_version=rec.model_version,
            financial_year=rec.financial_year,
            rating=rating,
            comment=comment,
            crops=[item.get('crop') for item in (rec.recommendations or []) if item.get('crop')],
            location_snapshot=(rec.input_snapshot or {}).get('location_snapshot'),
            created_by=request.user,
        )

        AuditService.log(
            user=request.user,
            action=AuditLog.Action.UPDATE,
            instance=rec,
            request=request,
            changes={'feedback_rating': rating, 'feedback_comment': comment},
        )

        serializer = CropRecommendationSerializer(rec)
        return StandardResponse.success(
            data=serializer.data,
            message=t('recommendations.feedback_saved', lang),
        )


# ---------------------------------------------------------------------------
# Admin — ML model version management
# ---------------------------------------------------------------------------

# Cheap, in-process checks on an uploaded model file. These catch obvious
# junk (wrong extension, empty, absurdly large) without a network call or any
# ML dependency. They deliberately do NOT try to open the file: the check that
# actually matters -- "does this model fit the service's feature schema?" --
# needs scikit-learn at the service's exact version, the service's own column
# list, and a real predict_proba() call in the process that will serve it.
# That's what _validate_model_with_service() is for; this is just the gate
# in front of it.
ALLOWED_MODEL_EXTENSIONS = {'.joblib', '.pkl', '.pickle'}
MAX_MODEL_FILE_BYTES = 200 * 1024 * 1024  # matches MAX_MODEL_UPLOAD_BYTES in ml_service/main.py


def _precheck_model_file(uploaded_file):
    """Returns a human-readable problem string, or None if the file passes."""
    suffix = Path(uploaded_file.name or '').suffix.lower()
    if suffix not in ALLOWED_MODEL_EXTENSIONS:
        return (f"Unsupported file type '{suffix or '(none)'}'. "
                f"Expected one of: {', '.join(sorted(ALLOWED_MODEL_EXTENSIONS))}.")
    size = getattr(uploaded_file, 'size', None)
    if not size:
        return "Uploaded file is empty."
    if size > MAX_MODEL_FILE_BYTES:
        return f"File is {size // (1024 * 1024)} MB; the limit is {MAX_MODEL_FILE_BYTES // (1024 * 1024)} MB."
    return None


def _save_model_file(uploaded_file, version_code: str) -> str:
    """
    Saves an uploaded model file into the shared ML_MODELS_DIR folder
    (settings.ML_MODELS_DIR — a sibling folder to both this Django
    project and ml_service/, matching the doc's eventual Docker volume
    plan). Returns a path RELATIVE to that shared root, e.g.
    "v1.0.0/model.pkl" — not an absolute filesystem path — so it stays
    valid no matter where each service mounts the shared volume.

    Only called AFTER the file has passed _precheck_model_file() and the
    ML service's /validate-model/ check (see MLModelVersionAdminView.post),
    so nothing that the service can't actually load and predict with ever
    lands in this folder.

    SECURITY NOTE: .pkl/.joblib files execute arbitrary code when loaded.
    The loading (and therefore the exposure) happens in the ML service,
    which is internal-only; only trusted admins can reach this endpoint
    (IsAdmin). Django itself never unpickles the file.
    """
    models_dir = Path(settings.ML_MODELS_DIR) / version_code
    models_dir.mkdir(parents=True, exist_ok=True)

    dest_path = models_dir / uploaded_file.name
    with open(dest_path, 'wb') as f:
        for chunk in uploaded_file.chunks():
            f.write(chunk)

    return f"{version_code}/{uploaded_file.name}"


def _validate_model_with_service(uploaded_file):
    """
    Sends the uploaded model file to the ML service's POST /validate-model/
    and returns its verdict dict: {valid, problems, warnings, expected_columns,
    detected_columns}. Raises httpx.RequestError if the service is unreachable
    and httpx.HTTPStatusError on a non-2xx (e.g. 413 file too large).

    Reads the whole upload into memory (model files are ~5 MB; the service
    caps at 200 MB) and rewinds it afterward so _save_model_file()'s
    .chunks() still works on the same object.
    """
    contents = uploaded_file.read()
    uploaded_file.seek(0)
    response = httpx.post(
        f"{settings.ML_SERVICE_URL}/validate-model/",
        files={'model_file': (uploaded_file.name, contents, 'application/octet-stream')},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


class MLModelVersionAdminView(APIView):
    """
    GET  /api/admin/ml-models/  — list all versions (paginated, matching
                                   the standard admin list pattern used
                                   everywhere else in this project)
    POST /api/admin/ml-models/  — register a new version, with an
                                   optional file upload ("model_file").
                                   An uploaded file is pre-checked here
                                   (extension/size) and then validated by
                                   the ML service (feature schema, classes,
                                   smoke prediction) BEFORE it is saved or
                                   a row is created.
    """
    permission_classes = [IsAdmin]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    pagination_class = StandardPagination

    @extend_schema(tags=["Admin - ML Models"])
    def get(self, request, *args, **kwargs):
        versions = MLModelVersion.objects.filter(is_deleted=False).order_by('-deployed_at')

        search = request.query_params.get('search')
        if search:
            versions = versions.filter(
                Q(version_code__icontains=search) |
                Q(description__icontains=search)
            )

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(versions, request, view=self)
        serializer = MLModelVersionSerializer(page, many=True)
        # StandardPagination.get_paginated_response() already builds the
        # full {status, message, data, meta.pagination} envelope itself —
        # don't double-wrap with StandardResponse.success() here.
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(tags=["Admin - ML Models"])
    def post(self, request, *args, **kwargs):
        lang = request.language

        # NOT request.data.copy(): for a multipart request that .copy() deep-copies
        # everything in request.data, including the uploaded file object -- fine for
        # a small file (Django keeps it as an in-memory InMemoryUploadedFile, which
        # deepcopies cleanly), but a file over FILE_UPLOAD_MAX_MEMORY_SIZE (5MB) is
        # spooled to disk as a TemporaryUploadedFile wrapping a real OS file handle,
        # which deepcopy can't pickle -- "TypeError: cannot pickle 'BufferedRandom'
        # instances". Only the non-file fields are ever needed here (model_file is
        # already pulled out separately below), so build `data` without the file.
        # deployed_at is never taken from the client -- it's stamped below
        # with the server's current time, same as the retrain flow already
        # does, so "deployment date" always reflects when this was actually
        # registered instead of a manually-typed date.
        data = {k: v for k, v in request.data.items() if k not in ('model_file', 'deployed_at')}
        uploaded_file = request.FILES.get('model_file')
        validation_warnings = []

        # If a file was uploaded: pre-check -> validate with the ML service
        # -> save -> register. Its path overrides any model_file_path the
        # client tried to send directly.
        if uploaded_file:
            version_code = data.get('version_code')
            if not version_code:
                return StandardResponse.error(
                    t('recommendations.version_code_required', lang),
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            # 1. Cheap in-process gate: extension, non-empty, size cap.
            problem = _precheck_model_file(uploaded_file)
            if problem:
                return StandardResponse.error(
                    f"{t('recommendations.model_file_invalid', lang)} {problem}",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            # 2. Real check, done by the ML service (the only place that knows
            #    the feature schema and can actually load + call the model).
            #    POLICY: if the service can't be reached, registration is
            #    BLOCKED (503) rather than allowed-with-a-warning. That's
            #    deliberate for this endpoint -- the point is not letting an
            #    unchecked file in -- and the opposite of the activate view's
            #    graceful-degradation stance, which is fine because activate
            #    only touches versions that already passed this check.
            try:
                verdict = _validate_model_with_service(uploaded_file)
            except httpx.RequestError:
                return StandardResponse.error(
                    t('recommendations.ml_service_unreachable', lang),
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            except httpx.HTTPStatusError as exc:
                detail = None
                try:
                    detail = exc.response.json().get('detail')
                except Exception:  # noqa: BLE001 -- body may not be JSON
                    pass
                return StandardResponse.error(
                    detail or t('recommendations.model_validation_error', lang),
                    status_code=status.HTTP_502_BAD_GATEWAY,
                )

            if not verdict.get('valid'):
                # Surface the service's own problem list -- it names the exact
                # column mismatch, which is what the admin needs to fix it.
                problems = ' '.join(verdict.get('problems') or [])
                return StandardResponse.error(
                    f"{t('recommendations.model_validation_failed', lang)} {problems}".strip(),
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            validation_warnings = verdict.get('warnings') or []

            # 3. Only now does the file touch the shared model folder.
            data['model_file_path'] = _save_model_file(uploaded_file, version_code)

        serializer = MLModelVersionSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        version = serializer.save(deployed_at=timezone.now())

        AuditService.log(
            user=request.user,
            action=AuditLog.Action.CREATE,
            instance=version,
            request=request,
            changes={'version_code': version.version_code, 'via_file_upload': bool(uploaded_file)},
        )

        response_data = dict(serializer.data)
        if validation_warnings:
            # e.g. a scikit-learn version mismatch between where the file was
            # trained and what the service runs -- loaded fine, worth knowing.
            response_data['validation_warnings'] = validation_warnings

        return StandardResponse.success(
            data=response_data,
            message=t('recommendations.model_registered', lang),
            status_code=status.HTTP_201_CREATED,
        )


class MLModelVersionDetailView(APIView):
    """
    DELETE /api/admin/ml-models/{id}/

    Soft-deletes an MLModelVersion row (MLModelVersion already inherits
    BaseModel's is_deleted/deleted_at/soft_delete() -- this just exposes it
    over the API, matching the perform_destroy pattern used everywhere else,
    e.g. CropPackageOfPracticesViewSet). Nothing on disk (the model file) is
    touched -- only Django's record is marked deleted, and the list view
    already filters on is_deleted=False.

    The currently active version can't be deleted -- deactivating it first
    (by activating a different version) is required, so there's never a
    moment where FastAPI is still serving predictions from a version Django
    considers gone.
    """
    permission_classes = [IsAdmin]

    @extend_schema(tags=["Admin - ML Models"])
    def delete(self, request, pk, *args, **kwargs):
        lang = request.language
        try:
            version = MLModelVersion.objects.get(pk=pk, is_deleted=False)
        except MLModelVersion.DoesNotExist:
            return StandardResponse.error(
                t('recommendations.model_not_found', lang),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        if version.is_active:
            return StandardResponse.error(
                t('recommendations.model_delete_active_forbidden', lang),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        version.soft_delete(user=request.user)

        AuditService.log(
            user=request.user,
            action=AuditLog.Action.DELETE,
            instance=version,
            request=request,
            changes={'version_code': version.version_code},
        )

        return StandardResponse.success(
            data=None,
            message=t('recommendations.model_deleted', lang),
        )


# Cheap in-process checks on an uploaded dataset CSV, before any network call.
ALLOWED_DATASET_EXTENSIONS = {'.csv'}
MAX_DATASET_FILE_BYTES = 50 * 1024 * 1024
VERSION_CODE_MAX_LENGTH = 20  # matches MLModelVersion.version_code max_length


def _precheck_dataset_file(uploaded_file):
    """Returns a human-readable problem string, or None if the file passes."""
    suffix = Path(uploaded_file.name or '').suffix.lower()
    if suffix not in ALLOWED_DATASET_EXTENSIONS:
        return f"Unsupported file type '{suffix or '(none)'}'. Expected a .csv file."
    size = getattr(uploaded_file, 'size', None)
    if not size:
        return "Uploaded file is empty."
    if size > MAX_DATASET_FILE_BYTES:
        return f"File is {size // (1024 * 1024)} MB; the limit is {MAX_DATASET_FILE_BYTES // (1024 * 1024)} MB."
    return None


def _validate_dataset_with_service(uploaded_file):
    """
    Sends the CSV to the ML service's POST /validate-dataset/ -- the same
    structural checks /train/ runs first (required columns, known zone values,
    blank crop names, row count), exposed on their own so a broken file is
    refused right now instead of becoming a permanently failed row after a
    Celery round-trip. Takes milliseconds; no training happens.

    Returns {valid, problems, warnings, n_rows}. Raises httpx.RequestError if
    the service is unreachable. Rewinds the file afterward so it can be saved.
    """
    contents = uploaded_file.read()
    uploaded_file.seek(0)
    response = httpx.post(
        f"{settings.ML_SERVICE_URL}/validate-dataset/",
        files={'dataset_file': (uploaded_file.name, contents, 'text/csv')},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def _save_dataset_file(uploaded_file, version_code: str) -> Path:
    """
    Saves the uploaded CSV to ML_MODELS_DIR/{version_code}/dataset.csv -- the
    same per-version folder the ML service will write model.joblib into. The
    Celery task reads it from there, and it stays as a record of exactly what
    this version was trained on.
    """
    version_dir = Path(settings.ML_MODELS_DIR) / version_code
    version_dir.mkdir(parents=True, exist_ok=True)
    dest = version_dir / DATASET_FILENAME
    with open(dest, 'wb') as f:
        for chunk in uploaded_file.chunks():
            f.write(chunk)
    return dest


class MLModelRetrainView(APIView):
    """
    POST /api/admin/ml-models/retrain/
    multipart fields: dataset_file (required, CSV), version_code (optional),
    description (optional).

    Returns 202 Accepted immediately with the new MLModelVersion row in
    status=training. The actual training happens in retrain_model_task
    (apps/recommendations/tasks.py) -- same async-dispatch pattern as
    RequestRecommendationView -- so no HTTP timeout in the chain (browser,
    proxy, Django, httpx) can lose a training result. The row flips to
    ready (with model_file_path + training_metrics) or failed (with
    training_error) when the task finishes; the admin list polls for that.

    What still happens synchronously, because it is fast and it is the
    admin's only chance for immediate feedback:
      1. in-process pre-check: .csv, non-empty, <= 50 MB
      2. ML service /validate-dataset/: required columns present, zone
         values known -- a missing column is a 422 here, never a failed row
      3. version_code: generated if blank; must be unique and <= 20 chars
      4. the CSV is saved beside where the model will land
    Then the row is created and the task dispatched.
    """
    permission_classes = [IsAdmin]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(tags=["Admin - ML Models"])
    def post(self, request, *args, **kwargs):
        lang = request.language

        dataset_file = request.FILES.get('dataset_file')
        trained_from_profiles = False
        if not dataset_file and (request.data.get('source') or '').strip() == 'zone_profiles':
            # Train straight from the CURRENT active crop zone profiles -- the
            # same knowledge base predict_crops() filters candidates with, so
            # the model and the eligibility filter can't drift apart. Built
            # server-side (admins have no file to download/re-upload), then
            # follows the identical validate/save/dispatch path as an upload.
            from django.core.files.uploadedfile import SimpleUploadedFile

            from apps.recommendations.api.crop_zone_profile_admin import build_zone_profiles_csv_bytes
            csv_bytes, n_rows = build_zone_profiles_csv_bytes()
            if n_rows == 0:
                return StandardResponse.error(
                    t('recommendations.no_active_zone_profiles', lang),
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            dataset_file = SimpleUploadedFile('crop_zone_profiles.csv', csv_bytes, content_type='text/csv')
            trained_from_profiles = True
        if not dataset_file:
            return StandardResponse.error(
                t('recommendations.dataset_file_required', lang),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # 1. Cheap in-process gate.
        problem = _precheck_dataset_file(dataset_file)
        if problem:
            return StandardResponse.error(
                f"{t('recommendations.dataset_file_invalid', lang)} {problem}",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Version code: generated when blank (same shape the ML service used
        # to generate, so existing rows look consistent), otherwise checked
        # for length and uniqueness here rather than as an IntegrityError.
        version_code = (request.data.get('version_code') or '').strip()
        if not version_code:
            version_code = f"v-retrain-{uuid.uuid4().hex[:8]}"
        if len(version_code) > VERSION_CODE_MAX_LENGTH:
            return StandardResponse.error(
                f"{t('recommendations.dataset_file_invalid', lang)} "
                f"version_code must be at most {VERSION_CODE_MAX_LENGTH} characters.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        if MLModelVersion.objects.filter(version_code=version_code).exists():
            return StandardResponse.error(
                t('recommendations.version_code_exists', lang),
                status_code=status.HTTP_409_CONFLICT,
            )

        # 2. Structural validation by the ML service (milliseconds). Blocked
        #    if the service is down: a file nobody has checked must not be
        #    queued, and the task would only fail later anyway.
        try:
            verdict = _validate_dataset_with_service(dataset_file)
        except httpx.RequestError:
            return StandardResponse.error(
                t('recommendations.ml_service_unreachable', lang),
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except httpx.HTTPStatusError:
            return StandardResponse.error(
                t('recommendations.retrain_failed', lang),
                status_code=status.HTTP_502_BAD_GATEWAY,
            )
        if not verdict.get('valid'):
            problems = ' '.join(verdict.get('problems') or [])
            return StandardResponse.error(
                f"{t('recommendations.dataset_validation_failed', lang)} {problems}".strip(),
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        validation_warnings = verdict.get('warnings') or []

        # 3. Persist the dataset where the task (and the ML service) can see it.
        _save_dataset_file(dataset_file, version_code)

        # 4. Create the row in 'training' and hand off. deployed_at is when the
        #    admin submitted it -- the list orders by this, so the new row
        #    appears at the top straight away.
        description = (request.data.get('description') or '').strip()
        if not description and trained_from_profiles:
            description = 'Trained from the current active crop zone profiles.'
        description = description or TRAINING_DESCRIPTION_PLACEHOLDER
        version = MLModelVersion.objects.create(
            version_code=version_code,
            description=description,
            is_active=False,
            deployed_at=timezone.now(),
            model_file_path='',  # set by the task when the ML service reports the file
            status=MLModelVersion.Status.TRAINING,
        )

        AuditService.log(
            user=request.user,
            action=AuditLog.Action.CREATE,
            instance=version,
            request=request,
            changes={'version_code': version.version_code, 'trigger': 'retrain',
                     'dataset_file': 'current zone profiles' if trained_from_profiles else dataset_file.name},
        )

        retrain_model_task.delay(version.pk)

        response_data = dict(MLModelVersionSerializer(version).data)
        if validation_warnings:
            # Non-blocking findings (unknown zone values dropped, tiny file,
            # blank crop names). They will also be saved into training_metrics
            # when training finishes; surfacing them now lets the admin cancel
            # a mistake early -- by uploading a corrected file, since a
            # queued job cannot be cancelled.
            response_data['validation_warnings'] = validation_warnings

        return StandardResponse.success(
            data=response_data,
            message=t('recommendations.training_started', lang),
            status_code=status.HTTP_202_ACCEPTED,
        )


class MLModelVersionActivateView(APIView):
    """
    POST /api/admin/ml-models/{id}/activate/
    Asks the FastAPI service to load this version (POST
    {ML_SERVICE_URL}/reload-model/) FIRST, and only marks it active here once
    the service confirms it's serving it -- so this DB never claims a model
    is active that isn't actually being used for predictions.

    /reload-model/ validates the file before swapping it in and returns
    HTTP 422 (with the reason) if it's missing, won't load, or doesn't fit
    the service's feature schema. That becomes a 400 here with the reason in
    the message, and nothing changes on either side. If the service is
    unreachable or times out, activation is refused with a 503 -- there's no
    way to confirm the model is usable (the admin page shows the outage via
    MLServiceStatusView).

    On success MLModelVersion.save() deactivates every other version.

    Only a version in status=ready can be activated: a 'training' row has
    no model file yet and a 'failed' row never will.
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

        if version.status != MLModelVersion.Status.READY:
            return StandardResponse.error(
                t('recommendations.model_not_ready', lang),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            response = httpx.post(
                f"{settings.ML_SERVICE_URL}/reload-model/",
                json={
                    'model_file_path': version.model_file_path,
                    'version_code': version.version_code,
                },
                # Generous: the service loads + smoke-tests the whole model
                # file before answering. Giving up early could leave it
                # serving the new model while this DB still says the old one.
                timeout=30.0,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # 422 from /reload-model/: {detail: {note, problems, ...}}
            message = t('recommendations.model_activation_rejected', lang)
            try:
                detail = exc.response.json().get('detail') or {}
                extra = ' '.join([detail.get('note', '')] + (detail.get('problems') or [])).strip()
                if extra:
                    message = f"{message} {extra}"
            except Exception:  # noqa: BLE001 -- body may not be JSON
                pass
            return StandardResponse.error(message, status_code=status.HTTP_400_BAD_REQUEST)
        except httpx.HTTPError:  # unreachable, timeout, etc.
            return StandardResponse.error(
                t('recommendations.model_activation_service_down', lang),
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        version.is_active = True
        version.save()  # triggers the model's own save() deactivation logic

        AuditService.log(
            user=request.user,
            action=AuditLog.Action.UPDATE,
            instance=version,
            request=request,
            changes={'activated_version': version.version_code},
        )

        return StandardResponse.success(
            data=MLModelVersionSerializer(version).data,
            message=t('recommendations.model_activated', lang),
        )


class MLServiceStatusView(APIView):
    """
    GET /api/admin/ml-models/service-status/
    Whether the FastAPI ML service is reachable right now, and which version
    it's serving. The ML models admin page polls this to show a warning above
    the table while the service is down (activation is refused then -- see
    MLModelVersionActivateView).
    """
    permission_classes = [IsAdmin]

    @extend_schema(tags=["Admin - ML Models"])
    def get(self, request, *args, **kwargs):
        try:
            response = httpx.get(f"{settings.ML_SERVICE_URL}/health", timeout=3.0)
            response.raise_for_status()
            data = {'reachable': True, 'served_version': response.json().get('model_version')}
        except (httpx.HTTPError, ValueError):
            data = {'reachable': False, 'served_version': None}
        return StandardResponse.success(
            data=data,
            message=t('recommendations.ml_service_status_retrieved', request.language),
        )


class _ModelTestSerializer(serializers.Serializer):
    """
    Hand-picked inputs for an admin test prediction. Zone, season and soil
    type values are checked strictly by the ML service (/predict/test/),
    which owns those vocabularies -- see MLModelTestOptionsView.
    """
    agro_zone = serializers.CharField()
    season = serializers.CharField()
    soil_type = serializers.CharField(required=False, allow_blank=True, default='')
    soil_ph = serializers.FloatField(required=False, allow_null=True, default=None, min_value=3.0, max_value=10.0)
    commodities = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    tier = serializers.ChoiceField(choices=['A', 'B', 'C', 'D'], required=False, allow_null=True, default=None)
    # Replace the zone's seasonal averages for this test only (e.g. with the
    # current weather from MLModelTestLocationView). No rainfall override:
    # the model's rainfall is a monthly total, current readings aren't.
    temperature_override = serializers.FloatField(
        required=False, allow_null=True, default=None, min_value=-10.0, max_value=50.0)
    humidity_override = serializers.FloatField(
        required=False, allow_null=True, default=None, min_value=0.0, max_value=100.0)


class MLModelTestView(APIView):
    """
    POST /api/admin/ml-models/{id}/test/
    Runs a crop prediction with this version and admin-chosen inputs, so a
    model can be tried before (or after) activating it. The live model FPOs
    use is not changed, and nothing is saved -- the result is only returned.

    The ML service loads a non-active version's file just for the request
    (a few seconds); testing the active version uses the loaded model.
    """
    permission_classes = [IsAdmin]

    @extend_schema(tags=["Admin - ML Models"], request=_ModelTestSerializer)
    def post(self, request, pk, *args, **kwargs):
        lang = request.language
        try:
            version = MLModelVersion.objects.get(pk=pk)
        except MLModelVersion.DoesNotExist:
            return StandardResponse.error(
                t('recommendations.model_not_found', lang),
                status_code=status.HTTP_404_NOT_FOUND,
            )
        if version.status != MLModelVersion.Status.READY:
            return StandardResponse.error(
                t('recommendations.model_not_ready', lang),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        serializer = _ModelTestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            response = httpx.post(
                f"{settings.ML_SERVICE_URL}/predict/test/",
                json={
                    **serializer.validated_data,
                    'soil_type': serializer.validated_data['soil_type'] or None,
                    'version_code': version.version_code,
                    'model_file_path': version.model_file_path,
                },
                timeout=60.0,  # may load the version's model file first
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # 422 from /predict/test/: {detail: {note, problems, ...}}
            message = t('recommendations.model_test_failed', lang)
            try:
                detail = exc.response.json().get('detail') or {}
                extra = ' '.join([detail.get('note', '')] + (detail.get('problems') or [])).strip()
                if extra:
                    message = f"{message} {extra}"
            except Exception:  # noqa: BLE001 -- body may not be JSON
                pass
            return StandardResponse.error(message, status_code=status.HTTP_400_BAD_REQUEST)
        except httpx.HTTPError:
            return StandardResponse.error(
                t('recommendations.service_unavailable', lang),
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return StandardResponse.success(
            data=response.json(),
            message=t('recommendations.model_test_completed', lang),
        )


class _TestLocationSerializer(serializers.Serializer):
    """A dropped pin (lat/lng) OR a drawn polygon (GeoJSON geometry)."""
    lat = serializers.FloatField(required=False, min_value=-90, max_value=90)
    lng = serializers.FloatField(required=False, min_value=-180, max_value=180)
    polygon = serializers.JSONField(required=False)

    def validate(self, attrs):
        if 'polygon' in attrs:
            try:
                geom = GEOSGeometry(json.dumps(attrs['polygon']), srid=4326)
            except (GEOSException, ValueError, TypeError) as exc:
                raise serializers.ValidationError({'polygon': f'Not a valid GeoJSON geometry: {exc}'})
            if geom.geom_type != 'Polygon' or not geom.valid:
                raise serializers.ValidationError({'polygon': 'Expected a single valid, non-self-intersecting polygon.'})
            attrs['point'] = geom.centroid  # same as resolve_fpo_location() does for a cultivation area
            attrs['geom'] = geom
        elif 'lat' in attrs and 'lng' in attrs:
            attrs['point'] = None
        else:
            raise serializers.ValidationError('Send either lat and lng, or a polygon.')
        return attrs


class MLModelTestLocationView(APIView):
    """
    POST /api/admin/ml-models/test-location/
    For the admin model-test page's map: given a dropped pin or a drawn
    polygon (its centroid is used, as for an FPO's cultivation area), returns
    what the FPO recommendation flow would derive for that spot -- GIS zone,
    GIS soil region and the soil category the model matches it to -- plus the
    current weather, address and season. Nothing is saved.
    """
    permission_classes = [IsAdmin]

    @extend_schema(tags=["Admin - ML Models"], request=_TestLocationSerializer)
    def post(self, request, *args, **kwargs):
        serializer = _TestLocationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        point = serializer.validated_data['point']
        if point is not None:
            lat, lng = point.y, point.x
        else:
            lat, lng = serializer.validated_data['lat'], serializer.validated_data['lng']

        geom = serializer.validated_data.get('geom')
        zone = find_zone_for_point(lat, lng)
        soil_region = find_soil_region_for_point(lat, lng)

        # The GIS soil wording differs from the model's soil categories; the
        # ML service owns that matching. None = unmatched (the zone's soil mix
        # is averaged, as for an FPO); checked=False = service unreachable.
        soil_category, soil_checked = None, False
        if soil_region:
            try:
                response = httpx.get(
                    f"{settings.ML_SERVICE_URL}/predict/resolve-soil/",
                    params={'soil_type': soil_region.soil_type},
                    timeout=5.0,
                )
                response.raise_for_status()
                soil_category, soil_checked = response.json().get('category'), True
            except (httpx.HTTPError, ValueError):
                pass

        data = {
            'lat': round(lat, 6),
            'lng': round(lng, 6),
            # Same calculation as an FPO's saved cultivation area; None for a pin.
            'area_hectares': _compute_hectares(geom) if geom else None,
            'address': reverse_geocode_address(lat, lng),
            'zone': {'code': zone.code, 'name': zone.name_en} if zone else None,
            'soil_region': {'soil_type': soil_region.soil_type, 'name': soil_region.name_en} if soil_region else None,
            'soil_category': soil_category,
            'soil_category_checked': soil_checked,
            'season': get_current_season(),
            'weather': get_weather_for_point(lat, lng),
        }
        return StandardResponse.success(
            data=data,
            message=t('recommendations.model_test_location_resolved', request.language),
        )


class MLModelTestOptionsView(APIView):
    """
    GET /api/admin/ml-models/test-options/
    Zones, seasons, soil types and tiers the ML service accepts, for the
    admin test form's dropdowns (straight from the service, so they can't
    drift from what the model was trained on).
    """
    permission_classes = [IsAdmin]

    @extend_schema(tags=["Admin - ML Models"])
    def get(self, request, *args, **kwargs):
        lang = request.language
        try:
            response = httpx.get(f"{settings.ML_SERVICE_URL}/predict/options/", timeout=5.0)
            response.raise_for_status()
        except httpx.HTTPError:
            return StandardResponse.error(
                t('recommendations.service_unavailable', lang),
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return StandardResponse.success(
            data=response.json(),
            message=t('recommendations.model_test_options_retrieved', lang),
        )


class MLModelActiveInternalView(APIView):
    """
    GET /api/recommendations/internal/active-model/
    Service-to-service, not for browsers: the ML service calls this after it
    (re)starts to learn which version is active here, so a restart doesn't
    leave it serving its built-in fallback while this DB says otherwise.

    Authenticated by the shared settings.ML_SERVICE_INTERNAL_TOKEN in the
    X-Internal-Token header instead of JWT. Answers 404 (not 401/403) on a
    missing/wrong token or when the setting is empty, so the endpoint isn't
    discoverable from outside.
    """
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(exclude=True)
    def get(self, request, *args, **kwargs):
        expected = settings.ML_SERVICE_INTERNAL_TOKEN
        supplied = request.headers.get('X-Internal-Token', '')
        if not expected or not hmac.compare_digest(supplied.encode(), expected.encode()):
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)

        version = MLModelVersion.objects.filter(
            is_active=True, status=MLModelVersion.Status.READY,
        ).first()
        data = None
        if version:
            data = {'version_code': version.version_code, 'model_file_path': version.model_file_path}
        return StandardResponse.success(data=data)


# ---------------------------------------------------------------------------
# Admin — recommendation feedback (read-only)
# ---------------------------------------------------------------------------

class RecommendationFeedbackSerializer(serializers.ModelSerializer):
    """
    Read-only view of one RecommendationFeedback submission for admin
    review. feedback_rating/feedback_comment keep the field names this
    endpoint returned when feedback lived on CropRecommendation itself.
    location_snapshot is the farm boundary ({lat, lng, area_polygon,
    address}) the rated recommendation was generated for.
    """
    fpo_name = serializers.CharField(source='fpo.name', read_only=True)
    model_version_code = serializers.CharField(source='model_version.version_code', read_only=True)
    feedback_rating = serializers.IntegerField(source='rating', read_only=True)
    feedback_comment = serializers.CharField(source='comment', read_only=True)

    class Meta:
        model = RecommendationFeedback
        fields = [
            'id', 'recommendation', 'fpo_name', 'model_version_code', 'financial_year',
            'feedback_rating', 'feedback_comment',
            'crops', 'location_snapshot', 'created_at',
        ]


class RecommendationFeedbackAdminViewSet(TranslatedViewSet):
    """
    GET /api/admin/recommendations/feedback/ — every feedback submission,
    most recent first (an FPO that rates several recommendations has one
    row per submission). Optional ?model_version=<id>.

    Read-only by design — admins review feedback here, they don't edit
    it (feedback belongs to the FPO who submitted it). Same MRO note as
    AgroClimaticZoneViewSet: TranslatedViewSet already provides list()
    via ModelViewSet, so no extra mixins are added as bases. Wired via
    an explicit GET-only path() in admin/urls.py, same reasoning as
    zones/districts — a full router would also expose create/update/
    delete, which isn't wanted here.
    """
    def get_queryset(self):
        queryset = (
            RecommendationFeedback.objects
            .select_related('fpo', 'model_version')
            .order_by('-created_at')
        )
        model_version = self.request.query_params.get('model_version')
        if model_version:
            queryset = queryset.filter(model_version_id=model_version)
        return queryset

    serializer_class = RecommendationFeedbackSerializer
    permission_classes = [IsAdmin]
    pagination_class = StandardPagination
    filter_backends = [filters.SearchFilter]
    search_fields = ['fpo__name', 'comment']

    list_message = 'recommendations.feedback_list_retrieved'

    @extend_schema(tags=["Admin - Recommendations"])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)