"""
Market Linkage — shared read-only product directory for oversight roles.

Used by:
    apps/accounts/api/admin/market_linkage.py  — super admin / sub-admin
    apps/cbbo/api/market_linkage.py            — CBBO (assigned districts)

Each caller scopes the FPO queryset for its own role; everything below the
scoping (which FPOs appear, how batches are filtered, the response shape)
lives here so both portals stay identical.

One card per stock batch (ProductStock), every status — oversight roles see
drafts / sold / expired batches too, unlike the buyer catalogue.
"""
from django.db.models import Count, Q

from apps.core.services.translation import t
from apps.core.utils.pagination import StandardPagination
from apps.core.utils.responses import StandardResponse
from apps.database.models import ProductStock
from apps.marketplace.serializers import BuyerProductSerializer


class LinkageProductSerializer(BuyerProductSerializer):
    """Buyer catalogue card shape, plus status / visibility."""

    class Meta(BuyerProductSerializer.Meta):
        fields = BuyerProductSerializer.Meta.fields + ['status', 'is_public']
        read_only_fields = fields


_LIVE_BATCH = Q(products__is_deleted=False, products__stocks__is_deleted=False)


def linkage_fpo_queryset(scoped_fpo_qs):
    """FPOs (already scoped to the caller) that have at least one listed batch."""
    return (
        scoped_fpo_qs.filter(is_deleted=False)
        .filter(_LIVE_BATCH)
        .annotate(product_count=Count('products__stocks', filter=_LIVE_BATCH, distinct=True))
        .order_by('name')
    )


def _district_display(fpo, lang):
    if not fpo.district:
        return ''
    if lang != 'en':
        key = f'ui.districts.district_{fpo.district}'
        translated = t(key, language=lang, fallback_to_default=False)
        if translated != key:
            return translated
    return fpo.get_district_display()


def linkage_fpos_response(request, scoped_fpo_qs):
    """Paginated `{id, name, name_ml, district, district_display, product_count}` list."""
    lang = getattr(request, 'language', 'en')
    qs = linkage_fpo_queryset(scoped_fpo_qs)

    search = request.query_params.get('search', '').strip()
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(name_ml__icontains=search))

    paginator = StandardPagination()
    page = paginator.paginate_queryset(qs, request)
    data = [
        {
            'id': fpo.id,
            'name': fpo.name,
            'name_ml': fpo.name_ml,
            'district': fpo.district,
            'district_display': _district_display(fpo, lang),
            'product_count': fpo.product_count,
        }
        for fpo in (page if page is not None else qs)
    ]
    if page is not None:
        return paginator.get_paginated_response(data)
    return StandardResponse.success(data=data, message=t('marketplace.linkage_fpos_retrieved', lang))


def linkage_products_response(request, fpo_id):
    """
    Paginated batch cards for one FPO. The caller must already have checked
    the FPO is within its scope.

    Query params: search (product name en/ml), commodity (comma-separated
    codes), status (draft / active / sold / expired).
    """
    lang = getattr(request, 'language', 'en')
    qs = (
        ProductStock.objects.filter(
            product__fpo_id=fpo_id, product__is_deleted=False, is_deleted=False,
        )
        .select_related('product', 'product__commodity', 'product__fpo')
        .order_by('-created_at')
    )

    search = request.query_params.get('search', '').strip()
    if search:
        qs = qs.filter(Q(product__name__en__icontains=search) | Q(product__name__ml__icontains=search))

    codes = [c.strip() for c in request.query_params.get('commodity', '').split(',') if c.strip()]
    if codes:
        qs = qs.filter(product__commodity__code__in=codes)

    status_filter = request.query_params.get('status', '').strip()
    if status_filter:
        qs = qs.filter(status=status_filter)

    paginator = StandardPagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = LinkageProductSerializer(page if page is not None else qs, many=True, context={'lang': lang})
    if page is not None:
        return paginator.get_paginated_response(serializer.data)
    return StandardResponse.success(data=serializer.data, message=t('marketplace.linkage_products_retrieved', lang))
