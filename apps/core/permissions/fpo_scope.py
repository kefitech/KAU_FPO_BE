"""
FPO Row-Level Security (P2-01 + KAU suggestion #1)
==================================================
Restricts which FPOs an admin-side user can see.

    super_admin                                       → all FPOs
    sub_admin with a SubAdminDistrictAssignment       → every FPO in their district
    sub_admin without a district (legacy)             → FPOs from SubAdminFPOAssignment
    anyone else                                       → nothing

Enforced at queryset level, so an FPO outside the caller's scope is a 404,
never a 403 — we don't confirm it exists.

Usage:
    qs = scope_fpo_queryset(FPO.objects.filter(is_deleted=False), request.user)
    mems = scope_fpo_queryset(FPOUserMembership.objects.all(), request.user, fpo_field='fpo')
"""

from apps.core.utils.constants import UserRole


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


def scope_fpo_queryset(qs, user, fpo_field=None):
    """
    Filter `qs` down to the FPOs `user` is allowed to see.

    `fpo_field` is the lookup path from the queryset's model to FPO
    (e.g. 'fpo' for FPOUserMembership). Leave it None when `qs` is an FPO queryset.

    Layered logic — new district-based scoping is the default; legacy per-FPO
    assignment kicks in for sub-admins that haven't been given a district yet.
    """
    if is_super_admin(user):
        return qs

    if is_sub_admin(user):
        # 1. District-based (post-KAU default)
        district = get_sub_admin_district(user)
        if district:
            key = f'{fpo_field}__district' if fpo_field else 'district'
            return qs.filter(**{key: district})

        # 2. Legacy per-FPO assignment (backward compat until every sub-admin
        # has a district). Same behaviour as the previous version of this fn.
        lookup = f'{fpo_field}__subadmin_assignment__subadmin' if fpo_field else 'subadmin_assignment__subadmin'
        return qs.filter(**{lookup: user})

    return qs.none()
