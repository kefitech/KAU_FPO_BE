"""
Public Market Hub APIs — no auth required
============================================
P2-12: Public-facing discovery layer on top of the Marketplace.

GET  /api/public/market/commodities/              — commodity list + price ranges
GET  /api/public/market/opportunities/             — demand signals by commodity
GET  /api/public/market/products/                  — publicly opted-in FPO products
GET  /api/public/market/products/{id}/              — single product detail
POST /api/public/market/products/{id}/inquire/       — public buyer inquiry

Business rules:
- Product visible only if product.is_public=True
- FPO contact details never exposed — inquiries go through the platform
- Inquiry creates a new BuyerDirectory row (status=pending, no user) + a
  BuyerSellerMatch (status=suggested); FPO's primary user is notified
- Responses Redis-cached 1h — same pattern as apps/core/api/cms_public.py
"""
from django.core.cache import cache

from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.core.utils.pagination import StandardPagination
from apps.core.utils.responses import StandardResponse
from apps.database.models import BuyerDirectory, BuyerSellerMatch, MarketPrice, Product

CACHE_TTL = 60 * 60  # 1h — spec says shorter than CMS's 24h, since prices/stock change faster


def _lang(request):
    return request.headers.get('X-Language', 'en')


class PublicCommodityListView(APIView):
    """GET /api/public/market/commodities/ — commodity list with current price range from e-NAM."""
    permission_classes = [AllowAny]

    @extend_schema(tags=['Public Market Hub'], summary='Commodity list with price ranges')
    def get(self, request):
        lang = _lang(request)
        cache_key = f'public:market:commodities:{lang}'
        cached = cache.get(cache_key)
        if cached is not None:
            return StandardResponse.success(data=cached, message='Commodities retrieved successfully')


        # One commodity per public product currently listed, with its latest price.
        commodity_codes = set(Product.objects.filter(
            is_public=True, status=Product.Status.ACTIVE, is_deleted=False,
        ).values_list('commodity__code', flat=True))

        data = []
        for code in commodity_codes:
            prices = MarketPrice.objects.filter(commodity__code=code, is_deleted=False).order_by('-date')
            latest = prices.first()
            data.append({
                'commodity_code': code,
                'latest_price': {
                    'date': latest.date,
                    'min_price': latest.min_price,
                    'max_price': latest.max_price,
                    'modal_price': latest.modal_price,
                    'market_name': latest.market_name,
                    'source': latest.source,
                } if latest else None,
            })

        cache.set(cache_key, data, timeout=CACHE_TTL)
        return StandardResponse.success(data=data, message='Commodities retrieved successfully')


class PublicOpportunitiesView(APIView):
    """GET /api/public/market/opportunities/ — reuses the existing compute_opportunities() service."""
    permission_classes = [AllowAny]

    @extend_schema(tags=['Public Market Hub'], summary='Demand signals by commodity')
    def get(self, request):
        cache_key = 'public:market:opportunities'
        cached = cache.get(cache_key)
        if cached is not None:
            return StandardResponse.success(data=cached, message='Opportunities retrieved successfully')

        from apps.marketplace.services import compute_opportunities
        data = compute_opportunities()

        cache.set(cache_key, data, timeout=CACHE_TTL)
        return StandardResponse.success(data=data, message='Opportunities retrieved successfully')


class PublicProductListView(APIView):
    """GET /api/public/market/products/ — publicly opted-in FPO product listings. FPO contact info never exposed."""
    permission_classes = [AllowAny]
    pagination_class = StandardPagination

    @extend_schema(tags=['Public Market Hub'], summary='Public product listings')
    def get(self, request):
        lang = _lang(request)
        search = request.query_params.get('search', '').strip()
        commodity = request.query_params.get('commodity', '').strip()

        cache_key = f'public:market:products:{lang}:{search or "-"}:{commodity or "-"}'
        cached = cache.get(cache_key)
        if cached is None:
            queryset = Product.objects.filter(
                status=Product.Status.ACTIVE, is_public=True, is_deleted=False,
            ).select_related('commodity', 'fpo').order_by('-created_at')

            if search:
                from django.db.models import Q
                queryset = queryset.filter(Q(name__en__icontains=search) | Q(name__ml__icontains=search))
            if commodity:
                queryset = queryset.filter(commodity__code=commodity)

            cached = [
                {
                    'id': p.id,
                    'name': p.name,
                    'description': p.description,
                    'commodity_code': p.commodity.code,
                    'quantity': p.quantity,
                    'unit': p.unit,
                    'price_per_unit': p.price_per_unit,
                    'quality_certification': p.quality_certification,
                    'available_from': p.available_from,
                    'available_until': p.available_until,
                    # NOTE: fpo_name intentionally omitted per Business Rule #2 —
                    # "FPO contact details not exposed in public listing."
                }
                for p in queryset
            ]
            cache.set(cache_key, cached, timeout=CACHE_TTL)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(cached, request)
        return paginator.get_paginated_response(page)


class PublicProductDetailView(APIView):
    """GET /api/public/market/products/{id}/ — single public product detail."""
    permission_classes = [AllowAny]

    @extend_schema(tags=['Public Market Hub'], summary='Public product detail')
    def get(self, request, pk):
        try:
            p = Product.objects.select_related('commodity').get(
                pk=pk, status=Product.Status.ACTIVE, is_public=True, is_deleted=False,
            )
        except Product.DoesNotExist:
            return StandardResponse.error(message='Product not found', status_code=status.HTTP_404_NOT_FOUND)

        data = {
            'id': p.id,
            'name': p.name,
            'description': p.description,
            'commodity_code': p.commodity.code,
            'quantity': p.quantity,
            'unit': p.unit,
            'price_per_unit': p.price_per_unit,
            'quality_certification': p.quality_certification,
            'available_from': p.available_from,
            'available_until': p.available_until,
        }
        return StandardResponse.success(data=data, message='Product retrieved successfully')


class PublicInquirySerializer(serializers.Serializer):
    name = serializers.CharField(max_length=300)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    message = serializers.CharField(required=False, allow_blank=True)


class PublicProductInquireView(APIView):
    """
    POST /api/public/market/products/{id}/inquire/ — anonymous buyer submits a purchase inquiry.

    Creates a new BuyerDirectory row (status=pending, no user link) and a
    BuyerSellerMatch (status=suggested). FPO's primary user is notified.
    A new BuyerDirectory row is created per inquiry — no dedup by email.
    """
    permission_classes = [AllowAny]

    @extend_schema(tags=['Public Market Hub'], summary='Submit purchase inquiry', request=PublicInquirySerializer)
    def post(self, request, pk):
        try:
            product = Product.objects.select_related('fpo', 'commodity').get(
                pk=pk, status=Product.Status.ACTIVE, is_public=True, is_deleted=False,
            )
        except Product.DoesNotExist:
            return StandardResponse.error(message='Product not found', status_code=status.HTTP_404_NOT_FOUND)

        serializer = PublicInquirySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        buyer = BuyerDirectory.objects.create(
            name=data['name'],
            contact_email=data['email'],
            contact_phone=data.get('phone', ''),
            commodities_interested=[product.commodity.code],
            status=BuyerDirectory.Status.PENDING,
        )

        match = BuyerSellerMatch.objects.create(
            product=product,
            buyer=buyer,
            match_score=1,
            status=BuyerSellerMatch.Status.SUGGESTED,
        )

        # Notify the FPO's primary user, if one exists.
        primary_user = getattr(product.fpo, 'primary_user', None)
        if primary_user:
            from apps.notifications.services import send_notification
            try:
                send_notification(
                    user=primary_user,
                    code='buyer_inquiry',
                    channel='email',
                    context={
                        'fpo_name': product.fpo.name,
                        'product_name': product.name.get('en', ''),
                        'buyer_name': data['name'],
                        'buyer_email': data['email'],
                        'buyer_phone': data.get('phone', ''),
                        'buyer_message': data.get('message', ''),
                    },
                )
            except Exception:
                pass  # Inquiry already saved — don't fail the request if notification dispatch fails

        return StandardResponse.success(
            data={'inquiry_id': match.id},
            message='Inquiry submitted successfully',
            status_code=status.HTTP_201_CREATED,
        )