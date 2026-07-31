"""
FPO Dashboard API
==================
GET /api/fpo/dashboard/

Single endpoint returning everything the FPO dashboard needs in one call:
profile summary, tier badge, location (for map pin), team counts,
document counts, unread notification previews, and quick-link routes.

Only accessible to authenticated FPO primary or secondary users.
"""

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.views import APIView

from apps.core.permissions.rbac import IsFPOManager
from apps.core.utils.responses import StandardResponse
from apps.database.models.fpo import FPO, FPODocument, FPOUserMembership
from apps.database.models.notification import InAppNotification
from apps.core.utils.constants import REQUIRED_DOCUMENTS


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_fpo(user):
    """Return the FPO linked to this user (primary or secondary member)."""
    # Primary user
    fpo = getattr(user, 'fpo', None)
    if fpo:
        return fpo
    # Secondary user — membership
    membership = FPOUserMembership.objects.filter(user=user, is_deleted=False).select_related('fpo').first()
    if membership:
        return membership.fpo
    return None


def _tier_badge(fpo):
    latest = fpo.tier_history.order_by('-created_at').first()
    if not latest:
        return {'tier': None, 'financial_year': None}
    return {
        'tier':           latest.tier,
        'financial_year': latest.financial_year,
    }


def _profile_summary(fpo):
    return {
        'id':                  str(fpo.id),
        'name':                fpo.name,
        'application_id':      fpo.application_id or None,
        'status':              fpo.status,
        'legal_structure':     fpo.legal_structure,
        'primary_commodities': fpo.primary_commodities,
        'current_step':        fpo.current_step,
        'pan_number':          fpo.pan_number,
        'date_of_registration': str(fpo.date_of_registration) if fpo.date_of_registration else None,
        'total_members':       fpo.total_members,
    }


def _location(fpo):
    return {
        'district':     fpo.district,
        'block_taluk':  fpo.block_taluk,
        'address_line1': fpo.address_line1,
        'address_line2': fpo.address_line2,
        'pincode':       fpo.pincode,
        'latitude':      float(fpo.latitude)  if fpo.latitude  is not None else None,
        'longitude':     float(fpo.longitude) if fpo.longitude is not None else None,
    }


def _team_summary(fpo):
    qs = FPOUserMembership.objects.filter(fpo=fpo, is_deleted=False)
    total  = qs.count()
    active = qs.filter(is_active=True).count()
    return {'total': total, 'active': active}


def _documents_summary(fpo):
    docs = FPODocument.objects.filter(fpo=fpo, is_deleted=False)
    uploaded = docs.count()
    verified = docs.filter(is_verified=True).count()
    missing  = [dt for dt in REQUIRED_DOCUMENTS if not docs.filter(document_type=dt).exists()]
    return {
        'uploaded':         uploaded,
        'verified':         verified,
        'required_missing': missing,
        'ready_to_submit':  len(missing) == 0,
    }


def _render_notification(notif, lang: str):
    """Re-render a notification's title/body in the requested language.
    Falls back to the stored (frozen) text if no log/template link exists."""
    from apps.database.models.language import NotificationTemplate
    if not notif.log or not notif.log.template_code:
        return notif.title, notif.body
    template = (
        NotificationTemplate.objects.filter(
            template_code=notif.log.template_code, language__code=lang, is_active=True
        ).select_related('language').first()
        or NotificationTemplate.objects.filter(
            template_code=notif.log.template_code, language__code='en', is_active=True
        ).select_related('language').first()
    )
    if not template:
        return notif.title, notif.body
    rendered = template.render(notif.log.context or {})
    return rendered.get('subject') or notif.title, rendered.get('body') or notif.body
def _notifications_summary(user, lang: str):
    qs = InAppNotification.objects.filter(user=user).select_related(
        'log', 'log__template_code'
    ).order_by('-created_at')
    unread_count = qs.filter(is_read=False).count()
    previews = []
    for notif in qs[:3]:
        title, body = _render_notification(notif, lang)
        previews.append({
            'id':         notif.id,
            'title':      title,
            'body':       body,
            'is_read':    notif.is_read,
            'created_at': notif.created_at.isoformat(),
        })
    return {'unread_count': unread_count, 'recent': previews}


def _quick_links(fpo, is_primary):
    status = fpo.status

    if status == 'draft':
        links = [{'label': 'Continue Registration', 'path': '/fpo/register'}]
    elif status == 'info_required':
        links = [
            {'label': 'Update Application', 'path': '/fpo/register'},
            {'label': 'My Application',     'path': '/fpo/applications'},
        ]
    elif status in ('submitted', 'under_review'):
        links = [{'label': 'View Application Status', 'path': '/fpo/applications'}]
    else:
        # approved / rejected / suspended
        links = [
            {'label': 'My Application', 'path': '/fpo/applications'},
            {'label': 'My Profile',     'path': '/fpo/settings/profile'},
        ]
        if is_primary:
            links.append({'label': 'Team Members', 'path': '/fpo/team'})
        links.append({'label': 'Schemes & Subsidies', 'path': '/fpo/schemes'})

    return links


# ─────────────────────────────────────────────────────────────────────────────
# View
# ─────────────────────────────────────────────────────────────────────────────

class FPODashboardView(APIView):
    permission_classes = [IsFPOManager]

    @extend_schema(
        tags=['FPO - Dashboard'],
        summary='FPO dashboard',
        description=(
            'Returns all data needed to render the FPO dashboard in a single call: '
            'profile summary, tier badge, location (lat/lng for Leaflet map pin), '
            'team member counts, document upload status, unread notification previews, '
            'and quick-link frontend routes.\n\n'
            'Accessible to primary and secondary FPO users (`fpo_manager` role).'
        ),
        responses={200: None},
    )
    def get(self, request):
        fpo = _get_fpo(request.user)
        if not fpo:
            return StandardResponse.error(
                'No FPO profile found for this user.',
                status_code=status.HTTP_404_NOT_FOUND,
            )

        is_primary   = fpo.primary_user == request.user
        quick_links  = _quick_links(fpo, is_primary)
        lang = getattr(request, 'language', 'en')


        data = {
            'profile':       _profile_summary(fpo),
            'tier':          _tier_badge(fpo),
            'location':      _location(fpo),
            'team':          _team_summary(fpo),
            'documents':     _documents_summary(fpo),
            'notifications': _notifications_summary(request.user, lang),
            'quick_links':   quick_links,
            'is_primary':    is_primary,
        }
        return StandardResponse.success(data, 'Dashboard loaded.')
