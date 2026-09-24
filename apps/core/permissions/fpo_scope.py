"""
FPO Row-Level Security (P2-01)
==============================
Restricts which FPOs an admin-side user can see.

    super_admin → all FPOs
    sub_admin   → only FPOs assigned to them via SubAdminFPOAssignment
    anyone else → nothing

Enforced at queryset level, so an FPO outside the caller's scope is a 404,
never a 403 — we don't confirm it exists.

Usage:
    qs = scope_fpo_queryset(FPO.objects.filter(is_deleted=False), request.user)
    mems = scope_fpo_queryset(FPOUserMembership.objects.all(), request.user, fpo_field='fpo')
"""

from apps.core.utils.constants import UserRole


def is_super_admin(user):
    return user.groups.filter(name=UserRole.SUPER_ADMIN).exists()


def scope_fpo_queryset(qs, user, fpo_field=None):
    """
    Filter `qs` down to the FPOs `user` is allowed to see.

    `fpo_field` is the lookup path from the queryset's model to FPO
    (e.g. 'fpo' for FPOUserMembership). Leave it None when `qs` is an FPO queryset.
    """
    if is_super_admin(user):
        return qs
    if user.groups.filter(name=UserRole.SUB_ADMIN).exists():
        lookup = 'subadmin_assignment__subadmin'
        if fpo_field:
            lookup = f'{fpo_field}__{lookup}'
        return qs.filter(**{lookup: user})
    return qs.none()
