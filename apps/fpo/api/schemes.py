"""
FPO-facing — Schemes & Subsidies Browse
==========================================
GET  /api/fpo/schemes/         — list active schemes (with filter by category)
GET  /api/fpo/schemes/{id}/    — scheme detail
"""

from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from django.db.models import Q
from apps.core.utils.pagination import StandardPagination
from apps.core.utils.responses import StandardResponse
from apps.database.models.schemes import Scheme


class SchemePublicSerializer(serializers.ModelSerializer):
    category_display = serializers.SerializerMethodField()
    name             = serializers.SerializerMethodField()

    class Meta:
        model = Scheme
        fields = [
            'id', 'name', 'name_en', 'name_ml', 'administering_body', 'category',
            'category_display', 'objective', 'eligibility', 'benefit_details',
            'application_process', 'official_link', 'last_updated',
        ]

    def get_category_display(self, obj):
        return obj.get_category_display()

    def get_name(self, obj):
        lang = self.context.get('language', 'en')
        if lang == 'ml' and obj.name_ml:
            return obj.name_ml
        return obj.name_en


class SchemeListPublicView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['Schemes'],
        summary='Browse schemes & subsidies',
        description=(
            'Returns all active government schemes available to FPOs.\n\n'
            '**Filters:**\n'
            '- `category` — credit / insurance / marketing / infrastructure / capacity_building\n\n'
            '**Language:** Send `X-Language: ml` header for Malayalam scheme names.'
        ),
    )
    def get(self, request):
        qs = Scheme.objects.filter(is_deleted=False, is_active=True).order_by('order', 'name_en')

        category = request.query_params.get('category')
        if category:
            qs = qs.filter(category=category)

        search = request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(name_en__icontains=search) |
                Q(name_ml__icontains=search) |
                Q(administering_body__icontains=search) |
                Q(objective__icontains=search)
            )    

        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = SchemePublicSerializer(
            page, many=True, context={'language': getattr(request, 'language', 'en')}
        )
        return paginator.get_paginated_response(serializer.data)


class SchemeDetailPublicView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['Schemes'],
        summary='Scheme detail',
    )
    def get(self, request, pk):
        try:
            scheme = Scheme.objects.get(pk=pk, is_deleted=False, is_active=True)
        except Scheme.DoesNotExist:
            return StandardResponse.error('Scheme not found.', status_code=status.HTTP_404_NOT_FOUND)

        serializer = SchemePublicSerializer(
            scheme, context={'language': getattr(request, 'language', 'en')}
        )
        return StandardResponse.success(data=serializer.data)
