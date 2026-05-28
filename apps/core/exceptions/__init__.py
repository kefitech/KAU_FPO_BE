"""
Exceptions Module
=================

Custom exceptions for the KAU-FPO Platform.

Usage:
    from apps.core.exceptions import ValidationError, NotFoundError

    raise ValidationError(message="Invalid email", field="email")
    raise NotFoundError(resource="FPO")
"""

from .base import (
    # Base
    BaseAPIException,
    # Validation
    ValidationError,
    InvalidInputError,
    MissingFieldError,
    # Authentication
    AuthenticationError,
    InvalidCredentialsError,
    TokenExpiredError,
    TokenInvalidError,
    AccountDisabledError,
    AccountLockedError,
    # Authorization
    PermissionDeniedError,
    ForbiddenError,
    # Resource
    NotFoundError,
    AlreadyExistsError,
    ResourceConflictError,
    # Business Logic
    BusinessLogicError,
    InvalidStateTransitionError,
    EligibilityError,
    QuotaExceededError,
    # External Services
    ExternalServiceError,
    EmailServiceError,
    SMSServiceError,
    StorageServiceError,
    # Server
    ServerError,
    DatabaseError,
    ConfigurationError,
    # Rate Limiting
    RateLimitError,
)

from .handlers import custom_exception_handler

__all__ = [
    # Base
    'BaseAPIException',
    # Validation
    'ValidationError',
    'InvalidInputError',
    'MissingFieldError',
    # Authentication
    'AuthenticationError',
    'InvalidCredentialsError',
    'TokenExpiredError',
    'TokenInvalidError',
    'AccountDisabledError',
    'AccountLockedError',
    # Authorization
    'PermissionDeniedError',
    'ForbiddenError',
    # Resource
    'NotFoundError',
    'AlreadyExistsError',
    'ResourceConflictError',
    # Business Logic
    'BusinessLogicError',
    'InvalidStateTransitionError',
    'EligibilityError',
    'QuotaExceededError',
    # External Services
    'ExternalServiceError',
    'EmailServiceError',
    'SMSServiceError',
    'StorageServiceError',
    # Server
    'ServerError',
    'DatabaseError',
    'ConfigurationError',
    # Rate Limiting
    'RateLimitError',
    # Handler
    'custom_exception_handler',
]
