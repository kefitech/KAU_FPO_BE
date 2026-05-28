"""
Core Models
===========

Base classes and generic models for the KAU-FPO Platform.

Usage:
    from apps.core.models import BaseModel, StatusMixin, StatusHistory, AuditLog
"""

from .base import (
    TimeStampedModel,
    SoftDeleteModel,
    AuditModel,
    BaseModel,
)

from .mixins import (
    TranslatableMixin,
    StatusMixin,
    OrderedMixin,
    SlugMixin,
    ActiveMixin,
)

from .generic import (
    StatusHistory,
    AuditLog,
    MasterLookup,
)

__all__ = [
    # Base models
    'TimeStampedModel',
    'SoftDeleteModel',
    'AuditModel',
    'BaseModel',
    # Mixins
    'TranslatableMixin',
    'StatusMixin',
    'OrderedMixin',
    'SlugMixin',
    'ActiveMixin',
    # Generic models
    'StatusHistory',
    'AuditLog',
    'MasterLookup',
]
