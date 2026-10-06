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

"In their district" means: a CBBO with an active assignment for the district, or an
official whose districts include it. A record outside the caller's scope is a
404, same as scope_fpo_queryset.

Usage:
    qs = scope_cbbo_queryset(qs, request.user, manage=request.method not in SAFE_METHODS)
"""

from django.contrib.auth.models import User
from django.db.models import Q

from apps.core.permissions.fpo_scope import get_sub_admin_district, is_sub_admin, is_super_admin
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
