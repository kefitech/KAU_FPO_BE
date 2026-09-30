"""
Sub-admin district-cap helper — KAU suggestion #1.

Cheap cache-aware access to the SubAdminConfig table for the two hot reads:
  - effective cap for a given district (global default vs per-district override)
  - current count of active sub-admins in a district

Both cached in Redis for 30s to avoid hammering the config table during a
bulk-invite loop. Config writes bust the cache directly.
"""

from django.contrib.auth.models import Group
from django.core.cache import cache

from apps.core.utils.constants import UserRole


CACHE_KEY_CONFIG      = 'subadmin:config'
CACHE_TTL_CONFIG      = 30       # 30s — bulk-invite loop shouldn't churn the DB
CACHE_TTL_DISTRICT    = 30

DEFAULT_GLOBAL_CAP    = 30


def _config_map():
    """Return {key: value} from SubAdminConfig, cached."""
    cached = cache.get(CACHE_KEY_CONFIG)
    if cached is not None:
        return cached
    from apps.database.models import SubAdminConfig
    result = dict(SubAdminConfig.objects.values_list('key', 'value'))
    cache.set(CACHE_KEY_CONFIG, result, CACHE_TTL_CONFIG)
    return result


def bust_config_cache():
    """Call after any SubAdminConfig write."""
    cache.delete(CACHE_KEY_CONFIG)


def get_effective_cap(district_code: str) -> int:
    """Effective sub-admin cap for a district = per-district override or global default."""
    cfg = _config_map()
    override = cfg.get(f'district_cap_{district_code}')
    if override is not None:
        return int(override)
    return int(cfg.get('global_cap', DEFAULT_GLOBAL_CAP))


def count_active_in_district(district_code: str) -> int:
    """Count active sub-admins currently assigned to `district_code`."""
    key = f'subadmin:district_count:{district_code}'
    cached = cache.get(key)
    if cached is not None:
        return cached

    from apps.database.models import SubAdminDistrictAssignment
    try:
        sub_admin_group = Group.objects.get(name=UserRole.SUB_ADMIN)
    except Group.DoesNotExist:
        return 0

    count = SubAdminDistrictAssignment.objects.filter(
        district=district_code,
        subadmin__groups=sub_admin_group,
        subadmin__is_active=True,
        is_deleted=False,
    ).count()
    cache.set(key, count, CACHE_TTL_DISTRICT)
    return count


def bust_district_count_cache(district_code: str):
    """Call after any assignment/transfer/deactivation in this district."""
    cache.delete(f'subadmin:district_count:{district_code}')


def check_cap(district_code: str, extra: int = 1):
    """Raise ValueError if adding `extra` more sub-admins would exceed the cap.

    `extra` defaults to 1 (single create). Bulk-invite calls this with each row
    individually so a partial file still gets the first N-30 through.
    """
    cap     = get_effective_cap(district_code)
    current = count_active_in_district(district_code)
    if current + extra > cap:
        raise ValueError(
            f'District {district_code} is at capacity ({current}/{cap}). '
            f'Deactivate an existing sub-admin or raise the cap.'
        )


def get_all_district_counts() -> dict:
    """Return {district_code: current_count} for every district that has ≥1 sub-admin.

    Used by the list endpoint to show `Thrissur (28 / 30)` chips.
    """
    from apps.database.models import SubAdminDistrictAssignment
    from django.db.models import Count

    try:
        sub_admin_group = Group.objects.get(name=UserRole.SUB_ADMIN)
    except Group.DoesNotExist:
        return {}

    rows = (
        SubAdminDistrictAssignment.objects
        .filter(
            subadmin__groups=sub_admin_group,
            subadmin__is_active=True,
            is_deleted=False,
        )
        .values('district')
        .annotate(count=Count('id'))
    )
    return {r['district']: r['count'] for r in rows}
