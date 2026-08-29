"""
Celery task — async crop recommendation generation.

Matches this project's existing pattern (see apps/notifications/tasks.py):
@shared_task with bind=True, explicit retry, structured logging.

Reuses build_recommendation_payload()/get_crop_recommendation() from
services.py — the FastAPI-calling logic is unchanged, just moved out
of the request/response cycle.
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