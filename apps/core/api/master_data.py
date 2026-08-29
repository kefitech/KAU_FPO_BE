"""
Public Master Data API
======================
GET /api/public/master-data/

Returns MasterLookup entries for a given category, with translated names.
Used by FPO registration forms to populate dropdowns.

Query params:
    category (required) — e.g. legal_structure, commodity, block, bank_name
    district  (optional) — filter blocks by district code (e.g. TRS, EKM)
    lang      (optional) — language code, defaults to request language
"""

from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models.generic import MasterLookup


class PublicMasterDataView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['Public'],
        summary='Get master data options',
        description=(
            'Returns active lookup entries for a given category with translated names. '
            'Used by FPO registration wizard to populate all dropdown fields.\n\n'
            '**Available categories:**\n'
            '- `legal_structure` — FPO legal structures (FPC Act, Companies Act, etc.)\n'
            '- `state_csa_act` — State-specific CSA acts (Kerala CSA, Tamil Nadu CSA, etc.)\n'
            '- `signatory_designation` — Authorised signatory designations\n'
            '- `promoting_agency` — FPO promoting/facilitating agencies\n'
            '- `block` — Kerala administrative blocks. Use `district=<code>` to filter '
            '(e.g. `district=TRS`).\n'
            '- `commodity` — Agricultural commodities\n'
            '- `bank_name` — Bank names for FPO bank account details\n\n'
            '**District codes:** ALP, EKM, IDK, KNR, KSD, KTM, KZD, KLM, MLP, PKD, PTA, TVM, TRS, WYD'
        ),
        parameters=[
            OpenApiParameter('category', str, required=True,  description='Lookup category code'),
            OpenApiParameter('district', str, required=False, description='Filter blocks by district code (only for category=block)'),
            OpenApiParameter('lang',     str, required=False, description='Language code (en, ml, ...)'),
        ],
        responses={200: None, 400: None},
    )
    def get(self, request):
        category = request.query_params.get('category', '').strip()
        if not category:
            return Response(
                {'error': '`category` query parameter is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        lang     = request.query_params.get('lang', '').strip() or getattr(request, 'language', 'en')
        district = request.query_params.get('district', '').strip().upper()

        qs = MasterLookup.objects.filter(category=category, is_active=True).order_by('display_order', 'code')

        if district and category == 'block':
            qs = qs.filter(metadata__district=district)

        results = []
        for obj in qs:
            item = {
                'id':   obj.id,
                'code': obj.code,
                'name': obj.get_name(lang),
            }
            if obj.metadata:
                item['metadata'] = obj.metadata
            results.append(item)

        return Response({
            'category': category,
            'count':    len(results),
            'results':  results,
        })
