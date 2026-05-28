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
Audit Service for KAU-FPO Platform
==================================

Service for logging audit events to the AuditLog table.

Features:
- Log CRUD operations
- Log authentication events
- Track field changes
- Capture request context

Usage:
    from apps.core.services.audit import AuditService

    AuditService.log_create(user=request.user, instance=fpo, request=request)
    AuditService.log_update(user=request.user, instance=fpo, changes={'name': {'old': 'A', 'new': 'B'}})
    AuditService.log_login(user=user, request=request)

Author:
    Athul Gopan
Created On:
    21-04-2026
"""

from typing import Dict, Any, Optional
from django.contrib.contenttypes.models import ContentType

from apps.core.models.generic import AuditLog
from apps.core.utils.helpers import get_client_ip, get_user_agent


class AuditService:
    """
    Service for audit logging.

    Provides convenience methods for common audit operations.
    """

    @classmethod
    def log(
        cls,
        user,
        action: str,
        instance=None,
        changes: Dict = None,
        request=None,
        extra_data: Dict = None
    ) -> AuditLog:
        """
        Log an audit event.

        Args:
            user: User performing the action
            action: Action type (use AuditLog.Action choices)
            instance: Model instance affected (optional)
            changes: Dictionary of changes (for updates)
            request: HTTP request (for context)
            extra_data: Additional data to store in changes

        Returns:
            Created AuditLog instance
        """
        content_type = None
        object_id = ''
        object_repr = ''

        if instance:
            content_type = ContentType.objects.get_for_model(instance)
            object_id = str(instance.pk)
            object_repr = str(instance)[:255]

        ip_address = None
        user_agent = ''
        request_path = ''
        request_method = ''

        if request:
            ip_address = get_client_ip(request)
            user_agent = get_user_agent(request)[:500]
            request_path = request.path[:500]
            request_method = request.method

        # Merge extra_data into changes
        final_changes = changes or {}
        if extra_data:
            final_changes['_extra'] = extra_data

        return AuditLog.objects.create(
            user=user,
            action=action,
            content_type=content_type,
            object_id=object_id,
            object_repr=object_repr,
            changes=final_changes,
            ip_address=ip_address,
            user_agent=user_agent,
            request_path=request_path,
            request_method=request_method
        )

    @classmethod
    def log_create(cls, user, instance, request=None, **kwargs) -> AuditLog:
        """Log a create operation."""
        return cls.log(
            user=user,
            action=AuditLog.Action.CREATE,
            instance=instance,
            request=request,
            **kwargs
        )

    @classmethod
    def log_update(cls, user, instance, changes: Dict, request=None, **kwargs) -> AuditLog:
        """
        Log an update operation.

        Args:
            user: User performing the update
            instance: Updated model instance
            changes: Dict of changed fields: {"field": {"old": x, "new": y}}
            request: HTTP request
        """
        return cls.log(
            user=user,
            action=AuditLog.Action.UPDATE,
            instance=instance,
            changes=changes,
            request=request,
            **kwargs
        )

    @classmethod
    def log_delete(cls, user, instance, request=None, **kwargs) -> AuditLog:
        """Log a delete operation."""
        return cls.log(
            user=user,
            action=AuditLog.Action.DELETE,
            instance=instance,
            request=request,
            **kwargs
        )

    @classmethod
    def log_soft_delete(cls, user, instance, request=None, **kwargs) -> AuditLog:
        """Log a soft delete operation."""
        return cls.log(
            user=user,
            action=AuditLog.Action.SOFT_DELETE,
            instance=instance,
            request=request,
            **kwargs
        )

    @classmethod
    def log_restore(cls, user, instance, request=None, **kwargs) -> AuditLog:
        """Log a restore operation."""
        return cls.log(
            user=user,
            action=AuditLog.Action.RESTORE,
            instance=instance,
            request=request,
            **kwargs
        )

    @classmethod
    def log_login(cls, user, request=None, success: bool = True, **kwargs) -> AuditLog:
        """Log a login attempt."""
        action = AuditLog.Action.LOGIN if success else AuditLog.Action.FAILED_LOGIN
        return cls.log(
            user=user,
            action=action,
            request=request,
            **kwargs
        )

    @classmethod
    def log_logout(cls, user, request=None, **kwargs) -> AuditLog:
        """Log a logout."""
        return cls.log(
            user=user,
            action=AuditLog.Action.LOGOUT,
            request=request,
            **kwargs
        )

    @classmethod
    def log_password_change(cls, user, request=None, **kwargs) -> AuditLog:
        """Log a password change."""
        return cls.log(
            user=user,
            action=AuditLog.Action.PASSWORD_CHANGE,
            request=request,
            **kwargs
        )

    @classmethod
    def log_password_reset(cls, user, request=None, **kwargs) -> AuditLog:
        """Log a password reset."""
        return cls.log(
            user=user,
            action=AuditLog.Action.PASSWORD_RESET,
            request=request,
            **kwargs
        )

    @classmethod
    def log_export(cls, user, instance=None, request=None, export_type: str = None, **kwargs) -> AuditLog:
        """Log a data export."""
        extra_data = {'export_type': export_type} if export_type else None
        return cls.log(
            user=user,
            action=AuditLog.Action.EXPORT,
            instance=instance,
            request=request,
            extra_data=extra_data,
            **kwargs
        )

    @classmethod
    def get_user_activity(cls, user, limit: int = 50):
        """
        Get recent activity for a user.

        Args:
            user: User to get activity for
            limit: Maximum number of entries

        Returns:
            QuerySet of AuditLog entries
        """
        return AuditLog.objects.filter(user=user).order_by('-created_at')[:limit]

    @classmethod
    def get_object_history(cls, instance, limit: int = 50):
        """
        Get audit history for a specific object.

        Args:
            instance: Model instance
            limit: Maximum number of entries

        Returns:
            QuerySet of AuditLog entries
        """
        content_type = ContentType.objects.get_for_model(instance)
        return AuditLog.objects.filter(
            content_type=content_type,
            object_id=str(instance.pk)
        ).order_by('-created_at')[:limit]

    @classmethod
    def track_changes(cls, instance, old_data: Dict, new_data: Dict) -> Dict:
        """
        Calculate changes between old and new data.

        Args:
            instance: Model instance (for field type info)
            old_data: Dictionary of old values
            new_data: Dictionary of new values

        Returns:
            Dict of changes: {"field": {"old": x, "new": y}}
        """
        changes = {}

        # Compare all fields in new_data
        for field, new_value in new_data.items():
            old_value = old_data.get(field)

            # Skip if values are the same
            if old_value == new_value:
                continue

            # Convert to string for storage (handles datetime, etc.)
            changes[field] = {
                'old': cls._serialize_value(old_value),
                'new': cls._serialize_value(new_value),
            }

        return changes

    @staticmethod
    def _serialize_value(value) -> Any:
        """Convert value to JSON-serializable format."""
        if value is None:
            return None
        if hasattr(value, 'isoformat'):  # datetime/date
            return value.isoformat()
        if hasattr(value, 'pk'):  # Model instance
            return str(value.pk)
        return str(value) if not isinstance(value, (str, int, float, bool, list, dict)) else value
