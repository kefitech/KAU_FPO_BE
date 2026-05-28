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
Base Models for KAU-FPO Platform
================================

These abstract base classes provide common functionality for all models:
- TimeStampedModel: created_at, updated_at timestamps
- SoftDeleteModel: Soft delete with is_deleted flag
- AuditModel: created_by, updated_by tracking
- BaseModel: Combines all above + UUID field

Usage:
    from apps.core.models.base import BaseModel

    class MyModel(BaseModel):
        name = models.CharField(max_length=100)
Author:
    Athul Gopan

Created On:
    21-04-2026
"""

import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone


class TimeStampedModel(models.Model):
    """
    Abstract base model with automatic timestamp fields.

    Provides:
        - created_at: Auto-set on creation
        - updated_at: Auto-set on every save
    """

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="Timestamp when record was created"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp when record was last updated"
    )

    class Meta:
        abstract = True


class SoftDeleteModel(models.Model):
    """
    Abstract base model with soft delete support.

    Instead of actual deletion, records are marked as deleted.
    This allows for data recovery and audit compliance.

    Provides:
        - is_deleted: Boolean flag for soft delete status
        - deleted_at: Timestamp of deletion
        - deleted_by: User who deleted the record
        - soft_delete(): Method to soft delete
        - restore(): Method to restore deleted record
    """

    is_deleted = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Soft delete flag. True means record is deleted."
    )
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when record was soft deleted"
    )
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_deleted",
        help_text="User who deleted this record"
    )

    class Meta:
        abstract = True

    def soft_delete(self, user=None):
        """
        Mark record as deleted instead of actual deletion.

        Args:
            user: Optional user who is performing the deletion
        """
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.deleted_by = user
        self.save(update_fields=['is_deleted', 'deleted_at', 'deleted_by', 'updated_at'])

    def restore(self):
        """Restore a soft-deleted record."""
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None
        self.save(update_fields=['is_deleted', 'deleted_at', 'deleted_by', 'updated_at'])


class AuditModel(models.Model):
    """
    Abstract base model with audit fields.

    Tracks who created and last updated each record.

    Provides:
        - created_by: User who created the record
        - updated_by: User who last updated the record
    """

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_created",
        help_text="User who created this record"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_updated",
        help_text="User who last updated this record"
    )

    class Meta:
        abstract = True


class BaseModel(TimeStampedModel, SoftDeleteModel, AuditModel):
    """
    Standard base model for all application models.

    Combines:
        - TimeStampedModel: created_at, updated_at
        - SoftDeleteModel: is_deleted, deleted_at, deleted_by, soft_delete(), restore()
        - AuditModel: created_by, updated_by
        - UUID: Public-facing unique identifier (don't expose integer PKs)

    Usage:
        class FPO(BaseModel):
            name = models.CharField(max_length=255)
            # All base fields are automatically included
    """

    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
        help_text="Public UUID identifier (use this in APIs instead of PK)"
    )

    class Meta:
        abstract = True
        ordering = ['-created_at']

    def __str__(self):
        """Default string representation using UUID."""
        return str(self.uuid)
