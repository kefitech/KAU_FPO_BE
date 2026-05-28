"""
FPO Permission Service
======================

Two-tier permission check for FPO-internal actions:

  Tier 1 (KAU Admin): FPOMemberPermission matrix — role x action ceiling
  Tier 2 (FPO Primary): FPOMemberOverride — per-member overrides within the ceiling

Check order:
  1. Get user's membership role in the given FPO
  2. Check system matrix — does this role allow this action? No -> DENY (hard ceiling)
  3. Check member override — explicit override present? Use it
  4. Fall back to role default from system matrix

Usage:
    from apps.core.services.fpo_permission import has_fpo_permission

    if not has_fpo_permission(request.user, fpo, 'can_submit'):
        return Response({'detail': 'Permission denied'}, status=403)
"""

from django.core.cache import cache


def get_user_membership(user, fpo):
    """Return FPOUserMembership for user in fpo, or None."""
    from apps.database.models.fpo import FPOUserMembership
    return (
        FPOUserMembership.objects
        .select_related('role')
        .filter(fpo=fpo, user=user, is_active=True, is_deleted=False)
        .first()
    )


def get_role_permission(role, action_code):
    """
    Return FPOMemberPermission.is_allowed for (role, action_code).
    Cached per role+action for 5 minutes.
    """
    cache_key = f'fpo_perm:{role.id}:{action_code}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    from apps.database.models.fpo import FPOMemberPermission
    perm = FPOMemberPermission.objects.filter(
        role=role,
        action__code=action_code,
        action__is_active=True,
    ).first()

    result = perm.is_allowed if perm else False
    cache.set(cache_key, result, timeout=300)
    return result


def get_member_override(membership, action_code):
    """
    Return (is_allowed, has_override) for a specific membership + action.
    Returns (None, False) if no override row exists.
    """
    from apps.database.models.fpo import FPOMemberOverride
    override = FPOMemberOverride.objects.filter(
        membership=membership,
        action__code=action_code,
        action__is_active=True,
    ).first()

    if override is None:
        return None, False
    return override.is_allowed, True


def has_fpo_permission(user, fpo, action_code):
    """
    Main permission check — two-tier with ceiling enforcement.

    Returns True if user is allowed to perform action_code within fpo.
    Primary users always pass (they own the FPO).
    """
    if not user or not user.is_authenticated:
        return False

    membership = get_user_membership(user, fpo)
    if not membership or not membership.role:
        return False

    # Primary role bypasses the matrix — they own the FPO
    if membership.role.code == 'primary':
        from apps.database.models.fpo import FPOAction
        return FPOAction.objects.filter(code=action_code, is_active=True).exists()

    # Step 1: check system ceiling
    ceiling_allows = get_role_permission(membership.role, action_code)
    if not ceiling_allows:
        return False  # hard ceiling — primary cannot override this

    # Step 2: check per-member override
    override_value, has_override = get_member_override(membership, action_code)
    if has_override:
        return override_value

    # Step 3: fall back to role default (ceiling already True here)
    return True


def invalidate_role_permission_cache(role_id, action_code):
    """Call this after updating FPOMemberPermission rows."""
    cache.delete(f'fpo_perm:{role_id}:{action_code}')


def get_effective_permissions(membership):
    """
    Return dict of {action_code: is_allowed} for a membership,
    applying ceiling + overrides. Used by team permission API.
    """
    from apps.database.models.fpo import FPOMemberPermission, FPOMemberOverride, FPOAction

    if not membership.role:
        return {}

    # All active actions
    actions = FPOAction.objects.filter(is_active=True).values_list('id', 'code')

    # Role ceiling
    ceiling_map = {
        p['action__code']: p['is_allowed']
        for p in FPOMemberPermission.objects.filter(
            role=membership.role
        ).select_related('action').values('action__code', 'is_allowed')
    }

    # Member overrides
    override_map = {
        o['action__code']: o['is_allowed']
        for o in FPOMemberOverride.objects.filter(
            membership=membership
        ).select_related('action').values('action__code', 'is_allowed')
    }

    result = {}
    for _, code in actions:
        ceiling = ceiling_map.get(code, False)
        if not ceiling:
            result[code] = False
            continue
        result[code] = override_map.get(code, True)

    return result
