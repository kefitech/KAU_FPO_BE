"""
CBBO / Government-official visibility for admin users
=====================================================
Sub-admins are district-scoped (KAU suggestion #1). On the CBBO and
Government admin pages:

    super_admin                              → sees and manages everything
    sub_admin with can_view_all_cbbo_govt    → sees every record
    sub_admin                                → sees records in their district + state-wide ones
    sub_admin changing anything              → only records in their own district; anything
                                               else they can see is read-only
    sub_admin reactivating / deleting        → not an account a super admin deactivated
                                               (their own deactivations stay reversible)

"In their district" means: a CBBO with an active assignment for the district, or an
official whose districts include it. A record outside the caller's scope is a
404, same as scope_fpo_queryset.

Usage:
    qs = scope_cbbo_queryset(qs, request.user, manage=request.method not in SAFE_METHODS)
    error = super_admin_lock_error(request.user, account, lang)   # before activate / destroy
"""

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q

from apps.core.models.generic import AuditLog
from apps.core.permissions.fpo_scope import get_sub_admin_district, is_sub_admin, is_super_admin
from apps.core.services.audit import AuditService
from apps.core.utils.constants import District, UserRole
from apps.core.utils.messages import AdminMessages, msg
from apps.database.models.cbbo import CBBOAssignment

VIEW_ALL_PERM = 'accounts.can_view_all_cbbo_govt'


def _active_cbbo_ids(**kwargs):
    return CBBOAssignment.objects.filter(is_active=True, **kwargs).values('cbbo_id')


def _cbbo_in_district(district):
    return Q(pk__in=_active_cbbo_ids(level=CBBOAssignment.LEVEL_DISTRICT, district=district))


def _cbbo_state_wide():
    return Q(pk__in=_active_cbbo_ids(level=CBBOAssignment.LEVEL_STATE))


def _govt_in_district(district):
    return Q(govt_profile__jurisdiction_type='district', govt_profile__assigned_districts__contains=[district])


def _govt_state_wide():
    return Q(govt_profile__jurisdiction_type='state')


def _scope(qs, user, in_district, state_wide, manage):
    if is_super_admin(user):
        return qs
    if not is_sub_admin(user):
        return qs.none()
    if not manage and user.has_perm(VIEW_ALL_PERM):
        return qs

    district = get_sub_admin_district(user)
    q = in_district(district) if district else Q(pk__in=[])
    if not manage:
        q |= state_wide()
    return qs.filter(q)


def scope_cbbo_queryset(qs, user, manage=False):
    """CBBO users `user` may see — or, with manage=True, may change."""
    return _scope(qs, user, _cbbo_in_district, _cbbo_state_wide, manage)


def scope_govt_queryset(qs, user, manage=False):
    """Government officials `user` may see — or, with manage=True, may change."""
    return _scope(qs, user, _govt_in_district, _govt_state_wide, manage)


def _filter_by_district(qs, value, in_district, state_wide):
    code = (value or '').strip().upper()
    if code == 'STATE':
        return qs.filter(state_wide())
    if code in District.values:
        return qs.filter(in_district(code))
    return qs  # blank / unknown → no filter


def filter_cbbo_by_district(qs, value):
    """List filter: ?district=TSR → CBBOs actively assigned to TSR; ?district=state → state-wide ones."""
    return _filter_by_district(qs, value, _cbbo_in_district, _cbbo_state_wide)


def filter_govt_by_district(qs, value):
    """List filter: ?district=TSR → officials whose districts include TSR; ?district=state → state-level ones."""
    return _filter_by_district(qs, value, _govt_in_district, _govt_state_wide)


def can_manage(context, obj, scope_fn):
    """
    Whether the requesting admin may change `obj` — lets the UI hide edit/deactivate/
    delete on read-only rows. Cached on the serializer context, so a list costs one query.
    """
    request = context.get('request')
    if request is None:
        return False
    cache = context.setdefault('_can_manage', {})
    if 'all' not in cache:
        user = request.user
        cache['all'] = is_super_admin(user)
        if not cache['all']:
            cache['ids'] = set(scope_fn(User.objects.all(), user, manage=True).values_list('pk', flat=True))
    return cache['all'] or obj.pk in cache['ids']


def assignable_districts(user):
    """
    District codes `user` may assign accounts to — drives the create/edit form pickers.
    None means no restriction (super admin); a sub-admin gets only their own district.
    """
    if is_super_admin(user) or not is_sub_admin(user):
        return None
    own = get_sub_admin_district(user)
    return [own] if own else []


def own_district_error(user, *, state_wide=False, districts=()):
    """
    For creating accounts / assigning districts: a sub-admin may only target their
    own district. Returns the error message, or None when allowed.
    """
    if is_super_admin(user) or not is_sub_admin(user):
        return None
    own = get_sub_admin_district(user)
    if not own:
        return 'You have no district assigned, so you cannot assign accounts to a district.'
    if state_wide:
        return 'Only the super admin can create or assign state-wide accounts.'
    if any(d != own for d in districts):
        return f'You can only assign your own district ({own}).'
    return None


# ── Super-admin deactivation lock ────────────────────────────────────────────
# Same rule FPO primary users get for team members (apps/fpo/api/team.py,
# _last_deactivated_by_admin): who switched a login off is read back from the
# audit log, and a sub-admin may not reactivate or delete an account a super
# admin deactivated. A sub-admin's own deactivation stays reversible by sub-admins.

ACCOUNT_STATUS_ACTIONS = (AuditLog.Action.USER_ACTIVATE, AuditLog.Action.USER_DEACTIVATE)


def log_account_status(request, account, active):
    """Audit row for an admin switching `account`'s login on or off."""
    AuditService.log(
        user=request.user,
        action=AuditLog.Action.USER_ACTIVATE if active else AuditLog.Action.USER_DEACTIVATE,
        instance=account,
        request=request,
        changes={'activated_user' if active else 'deactivated_user': account.email},
    )


def super_admin_deactivated_ids(user_ids=None):
    """
    Ids of accounts whose most recent activate/deactivate audit row is a deactivation
    by a super admin. `user_ids` limits the lookup; None covers every account ever toggled.
    """
    rows = AuditLog.objects.filter(
        content_type=ContentType.objects.get_for_model(User), action__in=ACCOUNT_STATUS_ACTIONS,
    )
    if user_ids is not None:
        rows = rows.filter(object_id__in=[str(pk) for pk in user_ids])
    latest = (
        rows.order_by('object_id', '-created_at', '-pk').distinct('object_id')
            .values_list('object_id', 'action', 'user_id')
    )
    actor_by_account = {
        object_id: actor_id for object_id, action, actor_id in latest
        if action == AuditLog.Action.USER_DEACTIVATE and actor_id
    }
    if not actor_by_account:
        return set()
    super_admins = set(
        User.objects.filter(pk__in=set(actor_by_account.values()), groups__name=UserRole.SUPER_ADMIN)
            .values_list('pk', flat=True)
    )
    return {int(object_id) for object_id, actor_id in actor_by_account.items() if actor_id in super_admins}


def locked_by_super_admin(account):
    """Whether `account` is currently deactivated and a super admin was the one who did it."""
    return not account.is_active and account.pk in super_admin_deactivated_ids([account.pk])


def super_admin_lock_error(user, account, lang='en', *, deleting=False):
    """
    For reactivating or deleting an account: a sub-admin may not undo a super admin's
    deactivation. Returns the error message, or None when allowed.
    """
    if is_super_admin(user) or not locked_by_super_admin(account):
        return None
    text = AdminMessages.SUPER_ADMIN_DEACTIVATED_DELETE if deleting else AdminMessages.SUPER_ADMIN_DEACTIVATED_REACTIVATE
    return msg(text, lang)


def deactivated_by_super_admin(context, obj):
    """
    Serializer flag so the UI can hide activate/delete for sub-admins. Cached on the
    serializer context, so a list costs one lookup.
    """
    if '_super_admin_deactivated' not in context:
        context['_super_admin_deactivated'] = super_admin_deactivated_ids()
    return not obj.is_active and obj.pk in context['_super_admin_deactivated']
