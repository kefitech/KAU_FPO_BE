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
Custom Exceptions for KAU-FPO Platform
======================================

Application-specific exceptions that provide:
- Consistent error structure
- Bilingual error messages
- HTTP status code mapping
- Error codes for frontend handling

Usage:
    from apps.core.exceptions import ValidationError, NotFoundError

    raise ValidationError(
        message=t('invalid_email', language),
        field='email'
    )
Author:
    Athul Gopan
Created On:
    21-04-2026
"""

from typing import Optional, Dict, Any
from rest_framework import status


class BaseAPIException(Exception):
    """
    Base exception for all API errors.

    Provides consistent structure for error responses.
    """

    default_message = "An error occurred"
    default_code = "error"
    default_status_code = status.HTTP_400_BAD_REQUEST

    def __init__(
        self,
        message: str = None,
        code: str = None,
        status_code: int = None,
        errors: Dict = None,
        data: Any = None,
    ):
        self.message = message or self.default_message
        self.code = code or self.default_code
        self.status_code = status_code or self.default_status_code
        self.errors = errors  # Field-level errors
        self.data = data  # Additional data

        super().__init__(self.message)

    def to_dict(self) -> Dict:
        """Convert exception to dictionary for response."""
        result = {
            "status": "error",
            "message": self.message,
            "code": self.code,
        }

        if self.errors:
            result["errors"] = self.errors

        if self.data:
            result["data"] = self.data

        return result


# =============================================================================
# VALIDATION ERRORS
# =============================================================================

class ValidationError(BaseAPIException):
    """Raised when input validation fails."""

    default_message = "Validation failed"
    default_code = "validation_error"
    default_status_code = status.HTTP_400_BAD_REQUEST

    def __init__(
        self,
        message: str = None,
        field: str = None,
        errors: Dict = None,
        **kwargs
    ):
        # If single field error, convert to errors dict
        if field and not errors:
            errors = {field: [message or self.default_message]}

        super().__init__(message=message, errors=errors, **kwargs)


class InvalidInputError(ValidationError):
    """Raised for invalid user input."""

    default_message = "Invalid input provided"
    default_code = "invalid_input"


class MissingFieldError(ValidationError):
    """Raised when required field is missing."""

    default_message = "Required field is missing"
    default_code = "missing_field"


# =============================================================================
# AUTHENTICATION ERRORS
# =============================================================================

class AuthenticationError(BaseAPIException):
    """Base class for authentication errors."""

    default_message = "Authentication failed"
    default_code = "authentication_error"
    default_status_code = status.HTTP_401_UNAUTHORIZED


class InvalidCredentialsError(AuthenticationError):
    """Raised for invalid login credentials."""

    default_message = "Invalid email or password"
    default_code = "invalid_credentials"


class TokenExpiredError(AuthenticationError):
    """Raised when auth token has expired."""

    default_message = "Session expired. Please login again."
    default_code = "token_expired"


class TokenInvalidError(AuthenticationError):
    """Raised when auth token is invalid."""

    default_message = "Invalid authentication token"
    default_code = "token_invalid"


class AccountDisabledError(AuthenticationError):
    """Raised when user account is disabled."""

    default_message = "Your account has been disabled"
    default_code = "account_disabled"
    default_status_code = status.HTTP_403_FORBIDDEN


class AccountLockedError(AuthenticationError):
    """Raised when account is locked due to failed attempts."""

    default_message = "Account locked. Please try again later."
    default_code = "account_locked"
    default_status_code = status.HTTP_429_TOO_MANY_REQUESTS


# =============================================================================
# AUTHORIZATION ERRORS
# =============================================================================

class PermissionDeniedError(BaseAPIException):
    """Raised when user lacks required permission."""

    default_message = "You do not have permission to perform this action"
    default_code = "permission_denied"
    default_status_code = status.HTTP_403_FORBIDDEN


class ForbiddenError(BaseAPIException):
    """Raised for forbidden operations."""

    default_message = "Access forbidden"
    default_code = "forbidden"
    default_status_code = status.HTTP_403_FORBIDDEN


# =============================================================================
# RESOURCE ERRORS
# =============================================================================

class NotFoundError(BaseAPIException):
    """Raised when requested resource is not found."""

    default_message = "Resource not found"
    default_code = "not_found"
    default_status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, resource: str = None, **kwargs):
        if resource:
            kwargs['message'] = f"{resource} not found"
        super().__init__(**kwargs)


class AlreadyExistsError(BaseAPIException):
    """Raised when trying to create a duplicate resource."""

    default_message = "Resource already exists"
    default_code = "already_exists"
    default_status_code = status.HTTP_409_CONFLICT


class ResourceConflictError(BaseAPIException):
    """Raised when there's a conflict with current state."""

    default_message = "Operation conflicts with current state"
    default_code = "conflict"
    default_status_code = status.HTTP_409_CONFLICT


# =============================================================================
# BUSINESS LOGIC ERRORS
# =============================================================================

class BusinessLogicError(BaseAPIException):
    """Raised for business rule violations."""

    default_message = "Operation not allowed"
    default_code = "business_error"
    default_status_code = status.HTTP_422_UNPROCESSABLE_ENTITY


class InvalidStateTransitionError(BusinessLogicError):
    """Raised for invalid status transitions."""

    default_message = "Invalid status transition"
    default_code = "invalid_transition"

    def __init__(self, from_status: str, to_status: str, **kwargs):
        message = f"Cannot transition from '{from_status}' to '{to_status}'"
        super().__init__(message=message, **kwargs)


class EligibilityError(BusinessLogicError):
    """Raised when eligibility criteria not met."""

    default_message = "Eligibility criteria not met"
    default_code = "eligibility_failed"


class QuotaExceededError(BusinessLogicError):
    """Raised when quota/limit is exceeded."""

    default_message = "Quota exceeded"
    default_code = "quota_exceeded"


# =============================================================================
# EXTERNAL SERVICE ERRORS
# =============================================================================

class ExternalServiceError(BaseAPIException):
    """Raised when external service fails."""

    default_message = "External service error"
    default_code = "external_service_error"
    default_status_code = status.HTTP_502_BAD_GATEWAY


class EmailServiceError(ExternalServiceError):
    """Raised when email service fails."""

    default_message = "Failed to send email"
    default_code = "email_service_error"


class SMSServiceError(ExternalServiceError):
    """Raised when SMS service fails."""

    default_message = "Failed to send SMS"
    default_code = "sms_service_error"


class StorageServiceError(ExternalServiceError):
    """Raised when file storage service fails."""

    default_message = "File storage error"
    default_code = "storage_service_error"


# =============================================================================
# SERVER ERRORS
# =============================================================================

class ServerError(BaseAPIException):
    """Raised for internal server errors."""

    default_message = "An unexpected error occurred"
    default_code = "server_error"
    default_status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


class DatabaseError(ServerError):
    """Raised for database errors."""

    default_message = "Database error occurred"
    default_code = "database_error"


class ConfigurationError(ServerError):
    """Raised for configuration errors."""

    default_message = "Configuration error"
    default_code = "configuration_error"


# =============================================================================
# RATE LIMITING
# =============================================================================

class RateLimitError(BaseAPIException):
    """Raised when rate limit is exceeded."""

    default_message = "Too many requests. Please try again later."
    default_code = "rate_limit_exceeded"
    default_status_code = status.HTTP_429_TOO_MANY_REQUESTS

    def __init__(self, retry_after: int = None, **kwargs):
        super().__init__(**kwargs)
        self.retry_after = retry_after  # Seconds until retry
