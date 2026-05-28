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
Generic Models for KAU-FPO Platform
===================================

These models use Django's ContentType framework to provide
generic functionality across all models:

- StatusHistory: Track status changes for ANY model
- AuditLog: Track ALL CRUD operations across the system
- MasterLookup: Dynamic lookup data (cached in Redis)

Benefits:
- One table instead of many status_history tables
- Centralized audit logging
- Admin-editable lookup data with caching

Author:
    Athul Gopan

Created On:
    21-04-2026
"""

from django.db import models
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from .base import TimeStampedModel


class StatusHistory(TimeStampedModel):
    """
    Generic status history for ANY model.

    Uses Django's ContentType framework to track status changes
    across all models in a single table.

    Example:
        # Create status history entry
        StatusHistory.objects.create(
            content_object=fpo_application,
            from_status='submitted',
            to_status='under_review',
            changed_by=admin_user,
            remarks='Started review process'
        )

        # Get history for a model
        history = StatusHistory.objects.filter(
            content_type=ContentType.objects.get_for_model(fpo_application),
            object_id=fpo_application.pk
        )
    """

    # Generic relation to any model
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name='status_histories',
        help_text="The model type this status change belongs to"
    )
    object_id = models.PositiveIntegerField(
        help_text="Primary key of the related object"
    )
    content_object = GenericForeignKey('content_type', 'object_id')

    # Status change details
    from_status = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="Previous status (null for initial status)"
    )
    to_status = models.CharField(
        max_length=50,
        help_text="New status"
    )

    # Who made the change and why
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='status_changes',
        help_text="User who made the status change"
    )
    remarks = models.TextField(
        blank=True,
        help_text="Reason or notes for the status change"
    )

    # Request context for audit trail
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of the user"
    )
    user_agent = models.CharField(
        max_length=500,
        blank=True,
        help_text="Browser/client user agent"
    )

    class Meta:
        db_table = 'status_history'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['created_at']),
            models.Index(fields=['changed_by']),
        ]
        verbose_name = 'Status History'
        verbose_name_plural = 'Status Histories'

    def __str__(self):
        return f"{self.content_type.model}: {self.from_status or 'None'} → {self.to_status}"


class AuditLog(TimeStampedModel):
    """
    Generic audit log for ALL CRUD operations.

    Tracks who did what, when, and what changed across the entire system.
    Essential for compliance and debugging.

    Example:
        # Log an update
        AuditLog.log(
            user=request.user,
            action='update',
            instance=fpo,
            changes={'name': {'old': 'Old Name', 'new': 'New Name'}},
            request=request
        )

        # Log a login
        AuditLog.log(
            user=user,
            action='login',
            request=request
        )
    """

    class Action(models.TextChoices):
        """Types of auditable actions."""
        CREATE = 'create', 'Create'
        UPDATE = 'update', 'Update'
        DELETE = 'delete', 'Delete'
        SOFT_DELETE = 'soft_delete', 'Soft Delete'
        RESTORE = 'restore', 'Restore'
        LOGIN = 'login', 'Login'
        LOGOUT = 'logout', 'Logout'
        FAILED_LOGIN = 'failed_login', 'Failed Login'
        PASSWORD_CHANGE = 'password_change', 'Password Change'
        PASSWORD_RESET = 'password_reset', 'Password Reset'
        EXPORT = 'export', 'Data Export'
        IMPORT = 'import', 'Data Import'

    # Who performed the action
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='audit_logs',
        help_text="User who performed the action"
    )

    # What action was performed
    action = models.CharField(
        max_length=20,
        choices=Action.choices,
        help_text="Type of action performed"
    )

    # Which model/object was affected
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        related_name='audit_logs',
        help_text="Model type of the affected object"
    )
    object_id = models.CharField(
        max_length=50,
        blank=True,
        help_text="Primary key of the affected object"
    )
    object_repr = models.CharField(
        max_length=255,
        blank=True,
        help_text="String representation of the object"
    )

    # What changed (for updates)
    changes = models.JSONField(
        default=dict,
        help_text='Changed fields: {"field": {"old": x, "new": y}}'
    )

    # Request context
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="Client IP address"
    )
    location = models.JSONField(
        default=dict,
        blank=True,
        help_text='Location data from IP: {"city": "Thrissur", "region": "Kerala", "country": "India", ...}'
    )
    user_agent = models.CharField(
        max_length=500,
        blank=True,
        help_text="Browser/client user agent"
    )
    request_path = models.CharField(
        max_length=500,
        blank=True,
        help_text="API endpoint path"
    )
    request_method = models.CharField(
        max_length=10,
        blank=True,
        help_text="HTTP method (GET, POST, etc.)"
    )

    class Meta:
        db_table = 'audit_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['action']),
            models.Index(fields=['created_at']),
            models.Index(fields=['ip_address']),
        ]
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'

    def __str__(self):
        user_str = self.user.email if self.user else 'System'
        return f"{user_str} - {self.action} - {self.content_type or 'N/A'}"

    @classmethod
    def log(cls, user, action, instance=None, changes=None, request=None):
        """
        Helper method to create audit log entry.

        Args:
            user: User who performed the action
            action: Action type (use AuditLog.Action choices)
            instance: Optional model instance affected
            changes: Optional dict of changes {"field": {"old": x, "new": y}}
            request: Optional HTTP request for context

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
        location = {}
        user_agent = ''
        request_path = ''
        request_method = ''

        if request:
            ip_address = cls._get_client_ip(request)
            user_agent = request.headers.get('User-Agent', '')[:500]
            request_path = request.path[:500]
            request_method = request.method

            # Fetch geolocation data for the IP address
            if ip_address:
                from apps.core.utils.geolocation import get_ip_location
                location = get_ip_location(ip_address) or {}

        return cls.objects.create(
            user=user,
            action=action,
            content_type=content_type,
            object_id=object_id,
            object_repr=object_repr,
            changes=changes or {},
            ip_address=ip_address,
            location=location,
            user_agent=user_agent,
            request_path=request_path,
            request_method=request_method
        )

    @staticmethod
    def _get_client_ip(request):
        """Extract client IP from request headers."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')


class MasterLookup(TimeStampedModel):
    """
    Dynamic lookup table for admin-editable data.

    Use this for data that:
    - May change via admin panel
    - Doesn't fit in Python constants
    - Needs to be cached for performance

    Categories:
    - commodity: Crops, vegetables, etc.
    - expert_category: Expert specializations
    - etc.

    Example:
        # In admin, add commodities:
        MasterLookup(category='commodity', code='rice', name_en='Rice', name_ml='അരി')

        # In code, use LookupService (cached):
        commodities = LookupService.get_by_category('commodity')
    """

    category = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Category code (e.g., 'commodity', 'expert_category')"
    )
    code = models.CharField(
        max_length=50,
        help_text="Unique code within category"
    )
    description = models.TextField(
        blank=True,
        help_text="Optional description"
    )
    display_order = models.PositiveIntegerField(
        default=0,
        help_text="Order for display (lower = first)"
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether this lookup is active"
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        help_text="Parent lookup for hierarchical data"
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional metadata as JSON"
    )

    class Meta:
        db_table = 'master_lookup'
        unique_together = ['category', 'code']
        ordering = ['category', 'display_order', 'code']
        indexes = [
            models.Index(fields=['category', 'is_active']),
        ]
        verbose_name = 'Master Lookup'
        verbose_name_plural = 'Master Lookups'

    def __str__(self):
        return f"{self.category}: {self.code}"

    def get_name(self, language: str = 'en') -> str:
        from apps.core.services.translation import t
        key = f'{self.category}.{self.code}'
        result = t(key, language=language)
        if result != key:
            return result
        return self.code
