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
from apps.database.models import BuyerDirectory, BuyerSellerMatch, MarketPrice, Product, ProductStock
from apps.marketplace.tasks import PRODUCT_GRACE_DAYS

CACHE_TTL = 60 * 60  # 1h — spec says shorter than CMS's 24h, since prices/stock change faster


# KAU suggestion #3 — "Validity is over" banner shown during the 3-day
# grace window after a listing's available_until passes.
_GRACE_MESSAGE_EN = 'Validity is over — but please contact the buyer to know if it\'s restocked.'
_GRACE_MESSAGE_ML = 'സാധുത കഴിഞ്ഞു — പക്ഷേ വീണ്ടും സ്റ്റോക്ക് വന്നിട്ടുണ്ടോ എന്നറിയാൻ വിൽപ്പനക്കാരനെ ബന്ധപ്പെടുക.'


def _grace_message(lang: str) -> str:
    return _GRACE_MESSAGE_ML if lang == 'ml' else _GRACE_MESSAGE_EN


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
        # ProductStock FK means a product with multiple batches is joined once
        # per batch — set() dedupes the commodity codes.
        commodity_codes = set(Product.objects.filter(
            stocks__is_public=True, stocks__status=ProductStock.Status.ACTIVE, is_deleted=False,
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
    """
    GET /api/public/market/products/ — publicly opted-in FPO product
    listings. One card per **stock batch** so a product with two batches
    live surfaces as two cards. FPO contact info never exposed.
    """
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
            from datetime import timedelta
            from django.db.models import Q
            from django.utils import timezone

            today = timezone.now().date()
            grace_cutoff = today - timedelta(days=PRODUCT_GRACE_DAYS)

            # KAU #3 — include ACTIVE stock + EXPIRED stock still within the
            # 3-day grace window so buyers see "Validity is over" listings.
            queryset = ProductStock.objects.filter(
                is_public=True, is_deleted=False,
                product__is_deleted=False,
            ).filter(
                Q(status=ProductStock.Status.ACTIVE)
                | Q(
                    status=ProductStock.Status.EXPIRED,
                    available_until__gte=grace_cutoff,
                )
            ).select_related('product', 'product__commodity', 'product__fpo').order_by('-created_at')

            if search:
                queryset = queryset.filter(
                    Q(product__name__en__icontains=search) | Q(product__name__ml__icontains=search)
                )
            if commodity:
                queryset = queryset.filter(product__commodity__code=commodity)

            cached = []
            for s in queryset:
                p = s.product
                in_grace = s.status == ProductStock.Status.EXPIRED
                cached.append({
                    'id': s.id,
                    'product_id': p.id,
                    'name': p.name,
                    'description': p.description,
                    'commodity_code': p.commodity.code,
                    'commodity_name': p.commodity.get_name(lang),
                    'quantity': s.quantity,
                    'unit': s.unit,
                    'price_per_unit': s.price_per_unit,
                    'quality_certification': s.quality_certification,
                    'available_from': s.available_from,
                    'available_until': s.available_until,
                    'contact_phone': s.contact_phone or '',
                    'image': p.image.url if p.image else None,
                    'in_grace_period': in_grace,
                    'grace_message':   _grace_message(lang) if in_grace else None,
                    # NOTE: fpo_name intentionally omitted per Business Rule #2 —
                    # "FPO contact details not exposed in public listing."
                })
            cache.set(cache_key, cached, timeout=CACHE_TTL)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(cached, request)
        return paginator.get_paginated_response(page)


class PublicProductDetailView(APIView):
    """
    GET /api/public/market/products/{id}/ — single public listing detail.
    `id` is a **ProductStock** id (matches the id surfaced by the public
    list endpoint). FPO contact info never exposed.
    """
    permission_classes = [AllowAny]

    @extend_schema(tags=['Public Market Hub'], summary='Public product detail')
    def get(self, request, pk):
        from datetime import timedelta
        from django.db.models import Q
        from django.utils import timezone

        lang = _lang(request)
        today = timezone.now().date()
        grace_cutoff = today - timedelta(days=PRODUCT_GRACE_DAYS)

        try:
            # KAU #3 — fetch ACTIVE or EXPIRED-in-grace stock.
            s = ProductStock.objects.select_related('product__commodity', 'product__fpo').filter(
                pk=pk, is_public=True, is_deleted=False, product__is_deleted=False,
            ).filter(
                Q(status=ProductStock.Status.ACTIVE)
                | Q(
                    status=ProductStock.Status.EXPIRED,
                    available_until__gte=grace_cutoff,
                )
            ).get()
        except ProductStock.DoesNotExist:
            return StandardResponse.error(message='Product not found', status_code=status.HTTP_404_NOT_FOUND)

        p = s.product
        in_grace = s.status == ProductStock.Status.EXPIRED
        data = {
            'id': s.id,
            'product_id': p.id,
            'name': p.name,
            'description': p.description,
            'commodity_code': p.commodity.code,
            'commodity_name': p.commodity.get_name(lang),
            'quantity': s.quantity,
            'unit': s.unit,
            'price_per_unit': s.price_per_unit,
            'quality_certification': s.quality_certification,
            'available_from': s.available_from,
            'available_until': s.available_until,
            'image': p.image.url if p.image else None,
            'in_grace_period': in_grace,
            'grace_message':   _grace_message(lang) if in_grace else None,
        }
        return StandardResponse.success(data=data, message='Product retrieved successfully')


import re

NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z\s'-]*$")
PHONE_PATTERN = re.compile(r"^\d{10}$")


class PublicInquirySerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    message = serializers.CharField(required=False, allow_blank=True)

    def validate_name(self, value):
        value = value.strip()
        if not NAME_PATTERN.match(value):
            raise serializers.ValidationError(
                'Name must contain only letters, spaces, apostrophes, or hyphens.'
            )
        return value

    def validate_phone(self, value):
        value = value.strip()
        if value and not PHONE_PATTERN.match(value):
            raise serializers.ValidationError('Enter a valid 10-digit phone number.')
        return value


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
        # `pk` here is a ProductStock id — the public list surfaces one
        # card per batch, so the inquiry locks onto the specific batch
        # the visitor saw.
        try:
            stock = ProductStock.objects.select_related('product__fpo', 'product__commodity').get(
                pk=pk, status=ProductStock.Status.ACTIVE, is_public=True,
                is_deleted=False, product__is_deleted=False,
            )
        except ProductStock.DoesNotExist:
            return StandardResponse.error(message='Product not found', status_code=status.HTTP_404_NOT_FOUND)
        product = stock.product

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
            message=data.get('message', ''),
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
