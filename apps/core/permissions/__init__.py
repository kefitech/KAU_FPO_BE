"""
Permissions Module
==================

Role-based access control for the KAU-FPO Platform.

Usage:
    from apps.core.permissions import has_permission, IsAdmin, IsFPOManager
"""

from .rbac import (
    # Permission functions
    get_user_permissions,
    has_permission,
    has_any_permission,
    has_all_permissions,
    get_role_level,
    is_role_higher_or_equal,
    # Permission classes
    IsAuthenticated,
    IsSuperAdmin,
    IsAdmin,
    IsFPOManager,
    IsGovernmentOfficial,
    IsCBBO,
    IsExpert,
    HasPermission,
    HasAnyPermission,
    IsOwnerOrAdmin,
    HasFPOPermission,
    # Decorators
    permission_required,
    any_permission_required,
    # Constants
    ROLE_PERMISSIONS,
)

__all__ = [
    'get_user_permissions',
    'has_permission',
    'has_any_permission',
    'has_all_permissions',
    'get_role_level',
    'is_role_higher_or_equal',
    'IsAuthenticated',
    'IsSuperAdmin',
    'IsAdmin',
    'IsFPOManager',
    'IsGovernmentOfficial',
    'IsCBBO',
    'IsExpert',
    'HasPermission',
    'HasAnyPermission',
    'IsOwnerOrAdmin',
    'HasFPOPermission',
    'permission_required',
    'any_permission_required',
    'ROLE_PERMISSIONS',
]
