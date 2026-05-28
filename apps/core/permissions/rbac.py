"""
█╗  ██╗ ███████╗███████╗██╗    ████████╗███████╗ ██████╗██╗  ██╗
██║ ██╔╝██╔════╝██╔════╝██║    ╚══██╔══╝██╔════╝██╔════╝██║  ██║
█████╔╝ █████╗  █████╗  ██║       ██║   █████╗  ██║     ███████║
██╔═██╗ ██╔══╝  ██╔══╝  ██║       ██║   ██╔══╝  ██║     ██╔══██║
██║  ██╗███████╗██║     ██║       ██║   ███████╗╚██████╗██║  ██║
╚═╝  ╚═╝╚══════╝╚═╝     ╚═╝       ╚═╝   ╚══════╝ ╚═════╝╚═╝  ╚═╝

                KEFI TECH

 █████╗ ████████╗██╗  ██╗██╗   ██╗██╗     
██╔══██╗╚══██╔══╝██║  ██║██║   ██║██║     
███████║   ██║   ███████║██║   ██║██║     
██╔══██║   ██║   ██╔══██║██║   ██║██║     
██║  ██║   ██║   ██║  ██║╚██████╔╝███████╗
╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝ ╚═════╝ ╚══════╝

        ATHUL GOPAN

-----------------------------------------------------
Role-Based Access Control (RBAC) for KAU-FPO Platform
=====================================================

Defines permissions for each user role and provides
permission checking utilities.

Roles:
- super_admin: Full system access
- admin: System administration
- fpo_manager: FPO management
- government: Government portal access
- cbbo: CBBO/NGO portal access
- expert: Expert services
- viewer: Read-only access

Usage:
    from apps.core.permissions.rbac import has_permission, IsAdminUser

    # In views
    @permission_required('fpo.approve')
    def approve_fpo(request):
        ...

    # In DRF views
    class FPOViewSet(ModelViewSet):
        permission_classes = [IsAuthenticated, IsFPOManager]

Author:
    Athul Gopan
Created On:
    21-04-2026
"""

from typing import List, Set
from functools import wraps

from rest_framework import permissions
from rest_framework.permissions import BasePermission
from django.core.exceptions import PermissionDenied

from apps.core.utils.constants import UserRole, ROLE_HIERARCHY
from apps.core.services.translation import t


# =============================================================================
# PERMISSION DEFINITIONS
# =============================================================================

# Permission format: 'resource.action'
# Resources: user, fpo, document, notification, expert, marketplace, analytics, government, cbbo
# Actions: view, create, update, delete, approve, reject, export, manage

ROLE_PERMISSIONS = {
    UserRole.SUPER_ADMIN: {
        # Super admin has all permissions
        '*',  # Wildcard for all permissions
    },

    UserRole.ADMIN: {
        # User management
        'user.view', 'user.create', 'user.update', 'user.delete',
        'user.manage', 'user.view_all',
        # FPO management
        'fpo.view', 'fpo.view_all', 'fpo.create', 'fpo.update',
        'fpo.approve', 'fpo.reject', 'fpo.suspend', 'fpo.delete',
        # Document management
        'document.view', 'document.create', 'document.delete',
        'document.verify',
        # Notification management
        'notification.view', 'notification.create', 'notification.manage',
        # Analytics
        'analytics.view', 'analytics.export',
        # System settings
        'settings.view', 'settings.update',
        # Audit logs
        'audit.view',
    },

    UserRole.FPO_MANAGER: {
        # Own FPO management
        'fpo.view_own', 'fpo.create', 'fpo.update_own',
        # Own documents
        'document.view_own', 'document.create', 'document.delete_own',
        # Notifications (own)
        'notification.view_own',
        # Basic analytics (own FPO)
        'analytics.view_own',
        # Expert consultation
        'expert.view', 'expert.contact',
        # Marketplace
        'marketplace.view', 'marketplace.create', 'marketplace.update_own',
    },

    UserRole.GOVERNMENT: {
        # View all FPOs
        'fpo.view', 'fpo.view_all',
        # Documents (view only)
        'document.view',
        # Analytics (full)
        'analytics.view', 'analytics.export',
        # Government reports
        'government.view', 'government.export',
        # Audit logs (view)
        'audit.view',
    },

    UserRole.CBBO: {
        # FPO verification
        'fpo.view', 'fpo.view_assigned', 'fpo.verify',
        # Documents (view for verification)
        'document.view',
        # CBBO reports
        'cbbo.view', 'cbbo.report',
        # Analytics (limited)
        'analytics.view_assigned',
    },

    UserRole.EXPERT: {
        # Expert profile
        'expert.view_own', 'expert.update_own',
        # Contact requests
        'expert.view_requests', 'expert.respond',
        # FPO view (limited)
        'fpo.view_assigned',
    },

    UserRole.VIEWER: {
        # Read-only access to public data
        'fpo.view_public',
        'analytics.view_public',
    },
}


# =============================================================================
# PERMISSION CHECKING FUNCTIONS
# =============================================================================

def get_user_permissions(user) -> Set[str]:
    """
    Get all permissions for a user.

    Args:
        user: User instance

    Returns:
        Set of permission strings
    """
    if not user or not user.is_authenticated:
        return set()

    # Get all user's roles (groups)
    user_roles = user.groups.values_list('name', flat=True)

    # Collect permissions from all assigned roles
    all_permissions = set()
    for role in user_roles:
        role_perms = ROLE_PERMISSIONS.get(role, set())
        all_permissions.update(role_perms)

    # Super admin has all permissions
    if '*' in all_permissions:
        return {'*'}

    return all_permissions


def has_permission(user, permission: str) -> bool:
    """
    Check if user has a specific permission.

    Args:
        user: User instance
        permission: Permission string (e.g., 'fpo.approve')

    Returns:
        True if user has permission
    """
    user_permissions = get_user_permissions(user)

    # Super admin check
    if '*' in user_permissions:
        return True

    # Check for wildcard resource permission (e.g., 'fpo.*')
    resource = permission.split('.')[0]
    if f'{resource}.*' in user_permissions:
        return True

    return permission in user_permissions


def has_any_permission(user, permissions: List[str]) -> bool:
    """
    Check if user has any of the specified permissions.

    Args:
        user: User instance
        permissions: List of permission strings

    Returns:
        True if user has at least one permission
    """
    return any(has_permission(user, p) for p in permissions)


def has_all_permissions(user, permissions: List[str]) -> bool:
    """
    Check if user has all of the specified permissions.

    Args:
        user: User instance
        permissions: List of permission strings

    Returns:
        True if user has all permissions
    """
    return all(has_permission(user, p) for p in permissions)


def get_role_level(role: str) -> int:
    """
    Get hierarchical level for a role.

    Args:
        role: Role string

    Returns:
        Role level (higher = more privileged)
    """
    return ROLE_HIERARCHY.get(role, 0)


def is_role_higher_or_equal(user_role: str, target_role: str) -> bool:
    """
    Check if user_role is higher or equal to target_role.

    Args:
        user_role: User's role
        target_role: Target role to compare

    Returns:
        True if user_role is higher or equal
    """
    return get_role_level(user_role) >= get_role_level(target_role)


# =============================================================================
# DJANGO/DRF PERMISSION CLASSES
# =============================================================================

class IsAuthenticated(BasePermission):
    """Ensure user is authenticated."""
    message = t('common.unauthorized')

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)


class IsSuperAdmin(BasePermission):
    """Only super admins allowed."""
    message = t('common.permission_denied')

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.groups.filter(name=UserRole.SUPER_ADMIN).exists()
        )


class IsAdmin(BasePermission):
    """Admin or super admin allowed."""
    message = t('common.permission_denied')

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.groups.filter(name__in=[UserRole.SUPER_ADMIN, UserRole.ADMIN]).exists()
        )


class IsSubAdmin(BasePermission):
    """Only sub-admins allowed."""
    message = t('common.permission_denied')

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.groups.filter(name=UserRole.SUB_ADMIN).exists()
        )


class IsSubAdminOrSuperAdmin(BasePermission):
    """Sub-admin or super admin allowed."""
    message = t('common.permission_denied')

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.groups.filter(
                name__in=[UserRole.SUPER_ADMIN, UserRole.SUB_ADMIN]
            ).exists()
        )


class HasSubAdminPermission(BasePermission):
    """
    Check that a sub-admin has a specific configured permission.
    Super admin always passes. Sub-admin must have the Django user permission.

    Usage:
        class MyView(APIView):
            permission_classes = [HasSubAdminPermission]
            required_sub_admin_permission = 'can_approve_fpo'
    """
    message = t('common.permission_denied')

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        # Super admin always allowed
        if request.user.groups.filter(name=UserRole.SUPER_ADMIN).exists():
            return True

        # Sub-admin must have the specific permission assigned
        if request.user.groups.filter(name=UserRole.SUB_ADMIN).exists():
            perm = getattr(view, 'required_sub_admin_permission', None)
            if not perm:
                return True
            return request.user.has_perm(f'accounts.{perm}')

        return False


class IsFPOManager(BasePermission):
    """FPO manager, admin, or super admin allowed."""
    message = t('common.permission_denied')

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.groups.filter(
                name__in=[UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.FPO_MANAGER]
            ).exists()
        )


class IsGovernmentOfficial(BasePermission):
    """Government officials allowed."""
    message = t('common.permission_denied')

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.groups.filter(
                name__in=[UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.GOVERNMENT]
            ).exists()
        )


class IsCBBO(BasePermission):
    """CBBO users allowed."""
    message = t('common.permission_denied')

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.groups.filter(
                name__in=[UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.CBBO]
            ).exists()
        )


class IsExpert(BasePermission):
    """Expert users allowed."""
    message = t('common.permission_denied')

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.groups.filter(
                name__in=[UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.EXPERT]
            ).exists()
        )


class HasPermission(BasePermission):
    """
    Check for specific permission.

    Usage:
        class MyView(APIView):
            permission_classes = [HasPermission]
            required_permission = 'fpo.approve'
    """
    message = t('common.permission_denied')

    def has_permission(self, request, view):
        required_permission = getattr(view, 'required_permission', None)
        if not required_permission:
            return True

        return has_permission(request.user, required_permission)


class HasAnyPermission(BasePermission):
    """
    Check for any of multiple permissions.

    Usage:
        class MyView(APIView):
            permission_classes = [HasAnyPermission]
            required_permissions = ['fpo.approve', 'fpo.reject']
    """
    message = t('common.permission_denied')

    def has_permission(self, request, view):
        required_permissions = getattr(view, 'required_permissions', [])
        if not required_permissions:
            return True

        return has_any_permission(request.user, required_permissions)


class IsOwnerOrAdmin(BasePermission):
    """
    Object-level permission to allow owners or admins.

    Usage:
        class MyViewSet(ModelViewSet):
            permission_classes = [IsOwnerOrAdmin]
            owner_field = 'created_by'  # Field that references the owner
    """
    message = t('common.permission_denied')

    def has_object_permission(self, request, view, obj):
        # Admins can access anything
        if request.user.groups.filter(
            name__in=[UserRole.SUPER_ADMIN, UserRole.ADMIN]
        ).exists():
            return True

        # Check owner field
        owner_field = getattr(view, 'owner_field', 'created_by')
        owner = getattr(obj, owner_field, None)

        if owner:
            return owner == request.user

        return False


class IsSuperAdminOrReadOnly(BasePermission):
    """
    Super Admin: Full access (GET, POST, PUT, PATCH, DELETE)
    Other authenticated users: Read-only access (GET, HEAD, OPTIONS)

    Usage:
        class RoleViewSet(ModelViewSet):
            permission_classes = [IsAuthenticated, IsSuperAdminOrReadOnly]
    """
    message = t('common.permission_denied')

    def has_permission(self, request, view):
        # Ensure user is authenticated
        if not request.user or not request.user.is_authenticated:
            return False

        # Allow safe methods (GET, HEAD, OPTIONS) for any authenticated user
        if request.method in permissions.SAFE_METHODS:
            return True

        # Only super_admin can perform write operations (POST, PUT, PATCH, DELETE)
        return request.user.groups.filter(name=UserRole.SUPER_ADMIN).exists()


class IsSuperAdminOrFirstUser(BasePermission):
    """
    Allow super_admin to perform action, OR allow if no super_admin exists yet (bootstrap mode).

    This is used for registering the first super admin without authentication.
    Once at least one super_admin exists, only authenticated super_admins can perform the action.

    Usage:
        class RegisterSuperAdminView(APIView):
            permission_classes = [IsSuperAdminOrFirstUser]
    """
    message = t('common.permission_denied')

    def has_permission(self, request, view):
        from django.contrib.auth.models import User, Group

        # Check if any super_admin exists
        try:
            super_admin_group = Group.objects.get(name=UserRole.SUPER_ADMIN)
            has_super_admin = User.objects.filter(groups=super_admin_group).exists()
        except Group.DoesNotExist:
            # If super_admin group doesn't exist, allow (bootstrap mode)
            has_super_admin = False

        # If no super_admin exists, allow the request (first registration)
        if not has_super_admin:
            return True

        # Otherwise, require authenticated super_admin
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.groups.filter(name=UserRole.SUPER_ADMIN).exists()
        )


class HasFPOPermission(BasePermission):
    """
    FPO-internal permission check using the two-tier matrix.

    Tier 1: KAU Admin system matrix (role x action ceiling)
    Tier 2: FPO Primary user per-member overrides

    Usage:
        class SubmitFPOView(APIView):
            permission_classes = [IsAuthenticated, IsFPOManager, HasFPOPermission]
            required_fpo_action = 'can_submit'

    The view must have `required_fpo_action` set.
    The FPO is resolved from request.user.fpo (primary) or user.fpo_membership.fpo (member).
    """
    message = t('common.permission_denied')

    def has_permission(self, request, view):
        action_code = getattr(view, 'required_fpo_action', None)
        if not action_code:
            return True

        fpo = self._get_fpo(request.user)
        if not fpo:
            return False

        from apps.core.services.fpo_permission import has_fpo_permission
        return has_fpo_permission(request.user, fpo, action_code)

    def _get_fpo(self, user):
        try:
            return user.fpo
        except Exception:
            pass
        try:
            return user.fpo_membership.fpo
        except Exception:
            return None


# =============================================================================
# PERMISSION DECORATOR
# =============================================================================

def permission_required(permission: str, language: str = 'en'):
    """
    Decorator to check permission before function execution.

    Usage:
        @permission_required('fpo.approve')
        def approve_fpo(request, fpo_id):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            if not has_permission(request.user, permission):
                raise PermissionDenied(t('common.permission_denied', language))
            return func(request, *args, **kwargs)
        return wrapper
    return decorator


def any_permission_required(permissions: List[str], language: str = 'en'):
    """
    Decorator to check for any of multiple permissions.

    Usage:
        @any_permission_required(['fpo.approve', 'fpo.reject'])
        def handle_fpo_application(request, fpo_id):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            if not has_any_permission(request.user, permissions):
                raise PermissionDenied(t('common.permission_denied', language))
            return func(request, *args, **kwargs)
        return wrapper
    return decorator
