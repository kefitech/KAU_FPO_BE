"""
Celery tasks — async crop recommendation generation and async model retraining.

Matches this project's existing pattern (see apps/notifications/tasks.py):
@shared_task with bind=True, explicit retry, structured logging.

generate_crop_recommendation_task reuses build_recommendation_payload()/
get_crop_recommendation() from services.py — the FastAPI-calling logic is
unchanged, just moved out of the request/response cycle.

retrain_model_task does the same for model training: MLModelRetrainView
validates and saves the uploaded dataset, creates the MLModelVersion row in
status=training, and hands off here. Nothing in the request path waits for
training, so no HTTP timeout (browser, nginx, Django, httpx) can lose a
result -- the only timeout on the training path is this task's own call to
the ML service (settings.ML_TRAIN_TIMEOUT_SECONDS).
"""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    name='recommendations.generate',
)
def generate_crop_recommendation_task(self, fpo_id, model_version_id, financial_year):
    """
    Args:
        fpo_id            : FPO.pk
        model_version_id  : MLModelVersion.pk (the active model at request time)
        financial_year    : e.g. '2026-27'

    Looks up the FPO and model, calls FastAPI (via the existing
    get_crop_recommendation), saves the result, and — on success —
    triggers email + in-app notifications via the project's existing
    notification dispatcher.
    """
    from apps.database.models import FPO, MLModelVersion, CropRecommendation
    from apps.recommendations.services import get_crop_recommendation, build_recommendation_payload
    from apps.notifications.services import send_notification

    try:
        fpo = FPO.objects.get(pk=fpo_id)
        model_version = MLModelVersion.objects.get(pk=model_version_id)
    except (FPO.DoesNotExist, MLModelVersion.DoesNotExist) as e:
        logger.error(f"generate_crop_recommendation_task: {e}")
        return

    # Mark as actively processing (was 'pending' since the view created it)
    CropRecommendation.objects.filter(
        fpo=fpo, financial_year=financial_year
    ).update(status=CropRecommendation.Status.PROCESSING)

    result = get_crop_recommendation(fpo, model_version, financial_year)
    input_snapshot = build_recommendation_payload(fpo, model_version, financial_year)
    recommendations_list = result.get('recommendations', [])

    new_status = (
        CropRecommendation.Status.COMPLETED if recommendations_list
        else CropRecommendation.Status.FAILED
    )

    rec, _created = CropRecommendation.objects.update_or_create(
        fpo=fpo,
        financial_year=financial_year,
        defaults={
            'model_version': model_version,
            'input_snapshot': input_snapshot,
            'recommendations': recommendations_list,
            'status': new_status,
        },
    )

    if new_status == CropRecommendation.Status.COMPLETED:
        _notify_recommendation_ready(fpo, recommendations_list, financial_year)

    return rec.id


def _notify_recommendation_ready(fpo, recommendations_list, financial_year):
    """
    Sends both email and in-app notifications via the project's shared
    dispatcher (apps.notifications.services.send_notification). Fails
    silently per-channel if a template/channel isn't configured yet —
    send_notification() already logs a warning in that case; we don't
    want a missing notification template to break the recommendation
    itself, which already succeeded.
    """
    from apps.notifications.services import send_notification

    user = fpo.primary_user
    if not user:
        logger.warning(f"FPO {fpo.pk} has no primary_user — skipping notification")
        return

    top_crop = recommendations_list[0].get('crop', '') if recommendations_list else ''
    context = {
        'user_name': getattr(user, 'first_name', '') or getattr(user, 'username', ''),
        'top_crop': top_crop,
        'financial_year': financial_year,
    }

    # TODO: pull the user's actual language preference once that's
    # readily available on the user/profile model — defaulting to 'en'.
    lang = 'en'

    send_notification(user=user, code='recommendation_ready', channel='email', context=context, lang=lang)
    send_notification(user=user, code='recommendation_ready', channel='in_app', context=context, lang=lang)


# ---------------------------------------------------------------------------
# Model retraining
# ---------------------------------------------------------------------------

# The description MLModelRetrainView writes when the admin leaves it blank.
# The task replaces it with the ML service's metrics-based description on
# success; an admin-provided description is never overwritten.
TRAINING_DESCRIPTION_PLACEHOLDER = 'Training in progress'

# Name of the dataset file Django saves beside the (future) model file. The
# task reads it from here; keeping it on disk also preserves exactly what
# each version was trained on.
DATASET_FILENAME = 'dataset.csv'


def _mark_failed(version, reason: str) -> None:
    from apps.database.models import MLModelVersion
    version.status = MLModelVersion.Status.FAILED
    version.training_error = reason[:4000]
    version.save()  # plain save: the model's is_active hook is a no-op for an inactive row
    logger.error(f"retrain_model_task: version {version.version_code} failed: {reason}")


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    name='recommendations.retrain_model',
)
def retrain_model_task(self, model_version_id):
    """
    Args:
        model_version_id : MLModelVersion.pk of a row in status=training,
                           whose dataset MLModelRetrainView already saved to
                           ML_MODELS_DIR/{version_code}/dataset.csv.

    Calls the ML service's POST /train/ with that dataset, then records the
    outcome on the row:
      ready  -> model_file_path, training_metrics, description (if blank)
      failed -> training_error with the reason

    Retry policy: a refused connection (service down / restarting) is retried
    with backoff (30s, 60s, 120s) and then marked failed. A *timeout* is NOT
    retried -- the service may still be training the first attempt, and a
    second run would race it for the same output folder -- it is marked
    failed with a pointer to ML_TRAIN_TIMEOUT_SECONDS.
    """
    from pathlib import Path

    import httpx
    from django.conf import settings

    from apps.database.models import MLModelVersion

    try:
        version = MLModelVersion.objects.get(pk=model_version_id)
    except MLModelVersion.DoesNotExist:
        logger.error(f"retrain_model_task: MLModelVersion {model_version_id} does not exist")
        return

    if version.status != MLModelVersion.Status.TRAINING:
        # Already resolved (e.g. duplicate delivery of the task message) --
        # never re-run training on a row that is ready or failed.
        logger.warning(f"retrain_model_task: version {version.version_code} is {version.status}, skipping")
        return version.pk

    dataset_path = Path(settings.ML_MODELS_DIR) / version.version_code / DATASET_FILENAME
    if not dataset_path.is_file():
        _mark_failed(version, (
            f"Dataset file not found at {dataset_path}. The Celery worker must see the same "
            f"ML_MODELS_DIR as the Django web process."
        ))
        return version.pk

    timeout = getattr(settings, 'ML_TRAIN_TIMEOUT_SECONDS', 900)
    try:
        with open(dataset_path, 'rb') as f:
            response = httpx.post(
                f"{settings.ML_SERVICE_URL}/train/",
                files={'dataset_file': (DATASET_FILENAME, f, 'text/csv')},
                data={'version_code': version.version_code},
                timeout=timeout,
            )
    except httpx.ConnectError as exc:
        if self.request.retries < self.max_retries:
            countdown = 30 * (2 ** self.request.retries)  # 30s, 60s, 120s
            logger.warning(
                f"retrain_model_task: ML service unreachable for {version.version_code} "
                f"(attempt {self.request.retries + 1}/{self.max_retries + 1}); retrying in {countdown}s"
            )
            raise self.retry(exc=exc, countdown=countdown)
        _mark_failed(version, f"ML service unreachable after {self.max_retries + 1} attempts: {exc}")
        return version.pk
    except httpx.TimeoutException:
        _mark_failed(version, (
            f"Training did not finish within {timeout}s (ML_TRAIN_TIMEOUT_SECONDS). "
            f"The dataset may be too large for the current limit; raise the setting and upload again."
        ))
        return version.pk
    except httpx.RequestError as exc:
        _mark_failed(version, f"Request to ML service failed: {type(exc).__name__}: {exc}")
        return version.pk

    if response.status_code != 200:
        try:
            detail = response.json().get('detail')
        except Exception:  # noqa: BLE001 -- body may not be JSON
            detail = None
        _mark_failed(version, f"ML service returned HTTP {response.status_code}: {detail or response.text[:500]}")
        return version.pk

    result = response.json()

    version.model_file_path = result['model_file_path']
    version.training_metrics = result['metrics']
    if not version.description or version.description == TRAINING_DESCRIPTION_PLACEHOLDER:
        version.description = result['suggested_description']
    version.status = MLModelVersion.Status.READY
    version.training_error = ''
    version.save()

    logger.info(
        f"retrain_model_task: version {version.version_code} ready "
        f"({result['metrics'].get('n_rows_total')} rows, "
        f"accuracy {result['metrics'].get('random_80_20_split', {}).get('accuracy', 0):.3f})"
    )
    return version.pk