"""
FPO Row-Level Security (P2-01 + KAU suggestion #1)
==================================================
Restricts which FPOs an admin-side user can see.

    super_admin                                       → all FPOs
    sub_admin with a SubAdminDistrictAssignment       → every FPO in their district
    sub_admin without a district                      → nothing (until transferred to one)
    sub_admin with can_view_all_fpos, read_only=True  → all FPOs (read-only outside own district)
    anyone else                                       → nothing

Enforced at queryset level, so an FPO outside the caller's scope is a 404,
never a 403 — we don't confirm it exists.

Usage:
    qs = scope_fpo_queryset(FPO.objects.filter(is_deleted=False), request.user)
    mems = scope_fpo_queryset(FPOUserMembership.objects.all(), request.user, fpo_field='fpo')
    qs = scope_fpo_queryset(FPO.objects.all(), request.user, read_only=True)  # GET endpoints only
"""

from apps.core.utils.constants import UserRole

VIEW_ALL_PERM = 'accounts.can_view_all_fpos'


def is_super_admin(user):
    return user.groups.filter(name=UserRole.SUPER_ADMIN).exists()


def is_sub_admin(user):
    return user.groups.filter(name=UserRole.SUB_ADMIN).exists()


def get_sub_admin_district(user):
    """Return the district code (e.g. 'TSR') a sub-admin owns, or None if unassigned.

    Cheap read — SubAdminDistrictAssignment is OneToOne on User with a related_name.
    """
    assignment = getattr(user, 'district_assignment', None)
    return assignment.district if assignment else None


def scope_fpo_queryset(qs, user, fpo_field=None, read_only=False):
    """
    Filter `qs` down to the FPOs `user` is allowed to see.

    `fpo_field` is the lookup path from the queryset's model to FPO
    (e.g. 'fpo' for FPOUserMembership). Leave it None when `qs` is an FPO queryset.

    Sub-admins are scoped by district only; one without a district sees nothing.
    Pass read_only=True from endpoints that only read: a sub-admin holding
    can_view_all_fpos then sees every district. Anything that changes an FPO
    keeps the default, so they can only act on FPOs in their own district.
    """
    if is_super_admin(user):
        return qs

    if is_sub_admin(user):
        if read_only and user.has_perm(VIEW_ALL_PERM):
            return qs
        district = get_sub_admin_district(user)
        if district:
            key = f'{fpo_field}__district' if fpo_field else 'district'
            return qs.filter(**{key: district})

    return qs.none()


def can_manage_fpo(context, fpo):
    """
    Whether the requesting admin may act on `fpo` — lets the UI hide approve/reject/
    suspend etc. on FPOs a sub-admin can only view. Cached on the serializer context,
    so a list costs one query.
    """
    from apps.database.models import FPO

    request = context.get('request')
    if request is None:
        return False
    cache = context.setdefault('_can_manage_fpo', {})
    if 'all' not in cache:
        user = request.user
        cache['all'] = is_super_admin(user)
        if not cache['all']:
            cache['ids'] = set(scope_fpo_queryset(FPO.objects.all(), user).values_list('pk', flat=True))
    return cache['all'] or fpo.pk in cache['ids']
