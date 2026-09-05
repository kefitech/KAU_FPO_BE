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
    GET  /api/admin/recommendations/feedback/  — list recommendations that have farmer feedback
"""
import uuid
from pathlib import Path
from django.utils import timezone
import httpx
from django.conf import settings
from rest_framework import serializers, status, filters
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema

from django.db.models import Q

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
        # version is ready or write its own error text.
        read_only_fields = ['status', 'training_error', 'training_metrics']


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

        active_model = MLModelVersion.objects.filter(is_active=True).first()
        if not active_model:
            return StandardResponse.error(
                t('recommendations.no_active_model', lang),
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        fy = get_current_financial_year()

        # Create/reset the record as 'pending' immediately — the actual
        # FastAPI call happens in the Celery task, not here.
        rec, _created = CropRecommendation.objects.update_or_create(
            fpo=fpo,
            financial_year=fy,
            defaults={
                'model_version': active_model,
                'input_snapshot': {},
                'recommendations': [],
                'status': CropRecommendation.Status.PENDING,
            },
        )

        generate_crop_recommendation_task.delay(fpo.pk, active_model.pk, fy)

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

        data = request.data.copy()
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
        serializer.save()

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
        description = (request.data.get('description') or '').strip() or TRAINING_DESCRIPTION_PLACEHOLDER
        version = MLModelVersion.objects.create(
            version_code=version_code,
            description=description,
            is_active=False,
            deployed_at=timezone.now(),
            model_file_path='',  # set by the task when the ML service reports the file
            status=MLModelVersion.Status.TRAINING,
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

    /reload-model/ validates the file before swapping it in and returns
    HTTP 422 (with the reason) if it's missing, won't load, or doesn't fit
    the service's feature schema -- the previous model keeps serving on
    the ML side in that case. The reason is passed through in `warning`
    so the admin sees what actually went wrong.

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
        except httpx.HTTPStatusError as exc:
            # 422 from /reload-model/: {detail: {note, problems, ...}}
            reload_warning = t('recommendations.model_reload_failed', lang)
            try:
                detail = exc.response.json().get('detail') or {}
                extra = ' '.join([detail.get('note', '')] + (detail.get('problems') or [])).strip()
                if extra:
                    reload_warning = f"{reload_warning} {extra}"
            except Exception:  # noqa: BLE001 -- body may not be JSON
                pass
        except Exception:  # noqa: BLE001 -- unreachable, timeout, etc.
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
    it (feedback belongs to the FPO who submitted it). Same MRO note as
    AgroClimaticZoneViewSet: TranslatedViewSet already provides list()
    via ModelViewSet, so no extra mixins are added as bases. Wired via
    an explicit GET-only path() in admin/urls.py, same reasoning as
    zones/districts — a full router would also expose create/update/
    delete, which isn't wanted here.
    """
    def get_queryset(self):
        queryset = (
            CropRecommendation.objects
            .exclude(feedback_rating__isnull=True)
            .select_related('fpo')
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
    search_fields = ['fpo__name', 'feedback_comment']

    list_message = 'recommendations.feedback_list_retrieved'

    @extend_schema(tags=["Admin - Recommendations"])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)