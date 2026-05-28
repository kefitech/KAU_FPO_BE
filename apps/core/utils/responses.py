"""
Standardized API Response Format for KAU-FPO Platform
=====================================================

All API responses follow a consistent structure:
{
    "status": "success" | "error",
    "message": "Human-readable message",
    "data": { ... } | null,
    "errors": { ... } | null,  # For validation errors
    "meta": { ... } | null,    # For pagination, etc.
}

Usage:
    from apps.core.utils.responses import success_response, error_response

    return success_response(data={'user': user_data}, message='User created')
    return error_response(message='Validation failed', errors=errors, status_code=400)
"""

from typing import Any, Optional, Dict
from rest_framework.response import Response
from rest_framework import status as http_status


class StandardResponse:
    """
    Standard response builder for consistent API responses.

    Ensures all API endpoints return the same structure.
    """

    @staticmethod
    def success(
        data: Optional[Any] = None,
        message: str = "Success",
        meta: Optional[Dict] = None,
        status_code: int = http_status.HTTP_200_OK
    ) -> Response:
        """
        Create a success response.

        Args:
            data: Response data (any JSON-serializable object)
            message: Success message
            meta: Optional metadata (pagination, etc.)
            status_code: HTTP status code (default: 200)

        Returns:
            DRF Response object
        """
        response_body = {
            "status": "success",
            "message": message,
            "data": data,
        }

        if meta:
            response_body["meta"] = meta

        return Response(response_body, status=status_code)

    @staticmethod
    def error(
        message: str = "An error occurred",
        errors: Optional[Dict] = None,
        data: Optional[Any] = None,
        status_code: int = http_status.HTTP_400_BAD_REQUEST
    ) -> Response:
        """
        Create an error response.

        Args:
            message: Error message
            errors: Field-level errors for validation
            data: Optional additional data
            status_code: HTTP status code (default: 400)

        Returns:
            DRF Response object
        """
        response_body = {
            "status": "error",
            "message": message,
            "data": data,
        }

        if errors:
            response_body["errors"] = errors

        return Response(response_body, status=status_code)

    @staticmethod
    def created(
        data: Optional[Any] = None,
        message: str = "Created successfully",
        meta: Optional[Dict] = None
    ) -> Response:
        """Create a 201 Created response."""
        return StandardResponse.success(
            data=data,
            message=message,
            meta=meta,
            status_code=http_status.HTTP_201_CREATED
        )

    @staticmethod
    def no_content(message: str = "Deleted successfully") -> Response:
        """Create a 204 No Content response."""
        return Response(
            {"status": "success", "message": message},
            status=http_status.HTTP_204_NO_CONTENT
        )

    @staticmethod
    def not_found(message: str = "Resource not found") -> Response:
        """Create a 404 Not Found response."""
        return StandardResponse.error(
            message=message,
            status_code=http_status.HTTP_404_NOT_FOUND
        )

    @staticmethod
    def unauthorized(message: str = "Authentication required") -> Response:
        """Create a 401 Unauthorized response."""
        return StandardResponse.error(
            message=message,
            status_code=http_status.HTTP_401_UNAUTHORIZED
        )

    @staticmethod
    def forbidden(message: str = "Permission denied") -> Response:
        """Create a 403 Forbidden response."""
        return StandardResponse.error(
            message=message,
            status_code=http_status.HTTP_403_FORBIDDEN
        )

    @staticmethod
    def validation_error(
        errors: Dict,
        message: str = "Validation failed"
    ) -> Response:
        """Create a 400 validation error response."""
        return StandardResponse.error(
            message=message,
            errors=errors,
            status_code=http_status.HTTP_400_BAD_REQUEST
        )

    @staticmethod
    def server_error(
        message: str = "An unexpected error occurred"
    ) -> Response:
        """Create a 500 Internal Server Error response."""
        return StandardResponse.error(
            message=message,
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    @staticmethod
    def paginated(
        data: list,
        page: int,
        page_size: int,
        total_count: int,
        message: str = "Success"
    ) -> Response:
        """
        Create a paginated success response.

        Args:
            data: List of items for current page
            page: Current page number
            page_size: Number of items per page
            total_count: Total number of items
            message: Success message

        Returns:
            DRF Response with pagination meta
        """
        total_pages = (total_count + page_size - 1) // page_size  # Ceiling division

        meta = {
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_count": total_count,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_previous": page > 1,
            }
        }

        return StandardResponse.success(data=data, message=message, meta=meta)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def success_response(
    data: Optional[Any] = None,
    message: str = "Success",
    meta: Optional[Dict] = None,
    status_code: int = http_status.HTTP_200_OK
) -> Response:
    """Shorthand for StandardResponse.success()"""
    return StandardResponse.success(data, message, meta, status_code)


def error_response(
    message: str = "An error occurred",
    errors: Optional[Dict] = None,
    data: Optional[Any] = None,
    status_code: int = http_status.HTTP_400_BAD_REQUEST
) -> Response:
    """Shorthand for StandardResponse.error()"""
    return StandardResponse.error(message, errors, data, status_code)


def created_response(
    data: Optional[Any] = None,
    message: str = "Created successfully"
) -> Response:
    """Shorthand for StandardResponse.created()"""
    return StandardResponse.created(data, message)


def not_found_response(message: str = "Resource not found") -> Response:
    """Shorthand for StandardResponse.not_found()"""
    return StandardResponse.not_found(message)


def validation_error_response(
    errors: Dict,
    message: str = "Validation failed"
) -> Response:
    """Shorthand for StandardResponse.validation_error()"""
    return StandardResponse.validation_error(errors, message)
