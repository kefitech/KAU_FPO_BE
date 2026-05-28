"""
Custom Pagination for KAU-FPO Platform
======================================

Standard pagination class for all API endpoints.
Returns consistent pagination metadata.

Usage:
    In views:
        from apps.core.utils.pagination import StandardPagination

        class MyViewSet(ModelViewSet):
            pagination_class = StandardPagination
"""

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from collections import OrderedDict

from .constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE


class StandardPagination(PageNumberPagination):
    """
    Standard pagination with customizable page size.

    Query parameters:
        - page: Page number (default: 1)
        - page_size: Items per page (default: 20, max: 100)

    Response format:
        {
            "status": "success",
            "message": "Success",
            "data": [...],
            "meta": {
                "pagination": {
                    "page": 1,
                    "page_size": 20,
                    "total_count": 100,
                    "total_pages": 5,
                    "has_next": true,
                    "has_previous": false
                }
            }
        }
    """

    page_size = DEFAULT_PAGE_SIZE
    page_size_query_param = 'page_size'
    max_page_size = MAX_PAGE_SIZE
    page_query_param = 'page'

    def get_paginated_response(self, data):
        """Return paginated response with standard format."""
        return Response(OrderedDict([
            ('status', 'success'),
            ('message', 'Success'),
            ('data', data),
            ('meta', OrderedDict([
                ('pagination', OrderedDict([
                    ('page', self.page.number),
                    ('page_size', self.page.paginator.per_page),
                    ('total_count', self.page.paginator.count),
                    ('total_pages', self.page.paginator.num_pages),
                    ('has_next', self.page.has_next()),
                    ('has_previous', self.page.has_previous()),
                ]))
            ]))
        ]))

    def get_paginated_response_schema(self, schema):
        """Schema for OpenAPI documentation."""
        return {
            'type': 'object',
            'properties': {
                'status': {'type': 'string', 'example': 'success'},
                'message': {'type': 'string', 'example': 'Success'},
                'data': schema,
                'meta': {
                    'type': 'object',
                    'properties': {
                        'pagination': {
                            'type': 'object',
                            'properties': {
                                'page': {'type': 'integer', 'example': 1},
                                'page_size': {'type': 'integer', 'example': 20},
                                'total_count': {'type': 'integer', 'example': 100},
                                'total_pages': {'type': 'integer', 'example': 5},
                                'has_next': {'type': 'boolean', 'example': True},
                                'has_previous': {'type': 'boolean', 'example': False},
                            }
                        }
                    }
                }
            }
        }


class LargeResultsPagination(StandardPagination):
    """Pagination for endpoints with large result sets."""
    page_size = 50
    max_page_size = 200


class SmallResultsPagination(StandardPagination):
    """Pagination for endpoints with small result sets (e.g., notifications)."""
    page_size = 10
    max_page_size = 50


class NoPagination(PageNumberPagination):
    """
    No pagination - returns all results.

    Use sparingly and only for endpoints with guaranteed small datasets.
    """
    page_size = None

    def paginate_queryset(self, queryset, request, view=None):
        # Return None to disable pagination
        return None
