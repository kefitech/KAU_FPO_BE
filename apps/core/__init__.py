"""
Core Module for KAU-FPO Platform
================================

This module provides the foundation for the entire application:

- **models**: Base models, mixins, and generic models (StatusHistory, AuditLog)
- **utils**: Constants, messages, validators, helpers (NO DB queries)
- **services**: Business logic services (Audit, Status, Lookup)
- **permissions**: Role-based access control
- **exceptions**: Custom exception classes
- **middleware**: Language detection, audit logging

Usage:
    # Models
    from apps.core.models import BaseModel, StatusMixin

    # Utils
    from apps.core.utils import District, FPOStatus, msg, AuthMessages

    # Services
    from apps.core.services import AuditService, StatusService

    # Permissions
    from apps.core.permissions import has_permission, IsAdmin

    # Exceptions
    from apps.core.exceptions import NotFoundError, ValidationError
"""

default_app_config = 'apps.core.apps.CoreConfig'
