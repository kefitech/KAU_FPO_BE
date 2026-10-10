"""
Notifications for AI results — crop recommendation and business plan.
=====================================================================
Both results belong to the FPO, but a team member with the right permission
may be the one who asked for them. So every result is announced (email +
in-app) to the FPO's primary user and, when it was someone else, to the
member who requested it. Each send is isolated: a missing template or a
broken channel never fails the result itself.
"""
import logging

logger = logging.getLogger(__name__)

RECOMMENDATIONS_LINK = '/fpo/recommendations'


def result_recipients(fpo, requested_by=None):
    """The FPO's primary user plus the requesting member, without duplicates or Nones."""
    recipients = []
    for user in (fpo.primary_user, requested_by):
        if user and all(user.pk != r.pk for r in recipients):
            recipients.append(user)
    return recipients


def _display_name(user):
    return user.get_full_name() or user.username


def _send_both(user, code, context):
    from apps.notifications.services import send_notification

    for channel in ('email', 'in_app'):
        try:
            send_notification(user=user, code=code, channel=channel, context=context)
        except Exception:
            logger.exception(f"Failed to queue {code}/{channel} for user {user.pk}")


def notify_recommendation_ready(fpo, recommendations_list, financial_year, requested_by=None):
    recipients = result_recipients(fpo, requested_by)
    if not recipients:
        logger.warning(f"FPO {fpo.pk} has no primary_user — skipping notification")
        return
    top_crop = recommendations_list[0].get('crop', '') if recommendations_list else ''
    for user in recipients:
        _send_both(user, 'recommendation_ready', {
            'user_name': _display_name(user),
            'top_crop': top_crop,
            'financial_year': financial_year,
            'link': RECOMMENDATIONS_LINK,
        })


def notify_business_plan_ready(fpo, plan, requested_by):
    for user in result_recipients(fpo, requested_by):
        _send_both(user, 'business_plan_ready', {
            'user_name': _display_name(user),
            'fpo_name': fpo.name,
            'financial_year': plan.financial_year,
            'generated_by': _display_name(requested_by),
            'link': RECOMMENDATIONS_LINK,
        })
