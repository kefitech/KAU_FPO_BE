#Arunima S


from rest_framework import serializers

from apps.core.services.fpo_permission import get_member_fpo
from apps.database.models import (
    BuyerDirectory,
    BuyerSellerMatch,
    Inquiry,
    MarketPrice,
    Product,
    ProductStock,
)

_PRODUCT_IMAGE_MAX_SIZE  = 2 * 1024 * 1024  # 2 MB — hard limit before compression is even attempted
_PRODUCT_IMAGE_MAX_DIM   = 1200             # resize to max 1200×1200 px
_PRODUCT_IMAGE_QUALITY   = 85               # JPEG/PNG compression quality
_PRODUCT_IMAGE_ALLOWED_MIME = {'image/jpeg', 'image/png', 'image/webp'}


def _compress_product_image(file):
    """
    Resize and compress an uploaded product photo (JPG/PNG/WebP only, max 2 MB
    on upload). Matches the pattern used for gallery photos — see
    apps/accounts/api/admin/cms.py:_compress_photo().
    """
    import magic
    import io
    from PIL import Image
    from django.core.files.uploadedfile import InMemoryUploadedFile

    if file.size > _PRODUCT_IMAGE_MAX_SIZE:
        raise serializers.ValidationError('Image must not exceed 2 MB.')

    mime = magic.from_buffer(file.read(2048), mime=True)
    file.seek(0)

    if mime not in _PRODUCT_IMAGE_ALLOWED_MIME:
        raise serializers.ValidationError(
            f'Only JPG, PNG, and WebP images are allowed. Got: {mime}'
        )

    img = Image.open(file)
    if img.mode not in ('RGB', 'RGBA'):
        img = img.convert('RGB')

    img.thumbnail((_PRODUCT_IMAGE_MAX_DIM, _PRODUCT_IMAGE_MAX_DIM), Image.LANCZOS)

    output = io.BytesIO()
    save_format = 'PNG' if mime == 'image/png' else 'JPEG'
    img.save(output, format=save_format, quality=_PRODUCT_IMAGE_QUALITY, optimize=True)
    output.seek(0)

    ext = '.png' if save_format == 'PNG' else '.jpg'
    return InMemoryUploadedFile(
        output, 'ImageField',
        file.name.rsplit('.', 1)[0] + ext,
        f'image/{"png" if save_format == "PNG" else "jpeg"}',
        output.getbuffer().nbytes,
        None,
    )


class ProductStockSerializer(serializers.ModelSerializer):
    """
    One stock/listing batch under a Product. Managed via the nested
    /api/marketplace/products/{product_id}/stocks/ endpoint — a product can
    have multiple batches live at the same time (e.g. 100kg @ ₹85 + 500kg
    @ ₹82).

    `status` and `is_public` are writable so the FPO can create a batch
    directly in ACTIVE state ("publish immediately") and/or opt the batch
    into the public Market Hub in one request. Sold/expired transitions
    still go through the dedicated mark-sold / expiry task — this
    serializer validates status to {draft, active} only.
    """

    class Meta:
        model = ProductStock
        fields = [
            'id', 'product', 'quantity', 'unit', 'price_per_unit',
            'quality_certification', 'available_from', 'available_until',
            'is_ondc_listed', 'ondc_product_id', 'is_public', 'status',
            'contact_phone',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'product', 'is_ondc_listed', 'ondc_product_id',
            'created_at', 'updated_at',
        ]

    def validate_status(self, value):
        # Sold/expired are set via dedicated actions (publish/mark-sold) or
        # the daily expiry task — not through raw PATCH. Restricting the
        # choices here keeps the lifecycle predictable even though the
        # underlying field accepts all four values.
        allowed = [ProductStock.Status.DRAFT.value, ProductStock.Status.ACTIVE.value]
        if value not in allowed:
            raise serializers.ValidationError(
                f"status must be one of {allowed} — use the mark-sold action "
                "or wait for the expiry task for other transitions."
            )
        return value


class ProductSerializer(serializers.ModelSerializer):
    """
    FPO's own product CRUD. A product is now PURELY the master identity
    (name, commodity, image, description). Its sellable stock batches live
    on ProductStock — one Product can have many stocks — and are managed
    through the nested /products/{id}/stocks/ endpoint.

    For backward compat with the pre-multi-batch frontend, the "latest"
    stock batch's fields are also surfaced flat on the product payload:
      - On READ: flat fields reflect `product.latest_stock` (most recent
        ACTIVE batch; fallback to most recent of any status).
      - On POST (product create): flat stock fields are accepted and used
        to create the FIRST batch alongside the product in one request —
        preserves the old "Add Product" wizard UX.
      - On PATCH (product update): flat stock fields are IGNORED. Stock
        edits go through /products/{id}/stocks/{stock_id}/.

    `stocks` (nested array) is the authoritative list of batches for the
    new multi-batch UI.
    """
    # Nested, authoritative list of batches — soft-deleted stocks are
    # filtered out so a removed draft doesn't inflate total_batches or
    # resurface anywhere on the FPO UI.
    stocks = serializers.SerializerMethodField()

    # Backward-compat flat fields — writable only during product create
    # (used to seed the first batch).
    quantity = serializers.DecimalField(
        max_digits=12, decimal_places=2,
        required=False, allow_null=True, write_only=True,
    )
    unit = serializers.ChoiceField(
        choices=ProductStock.Unit.choices,
        required=False, allow_null=True, write_only=True,
    )
    price_per_unit = serializers.DecimalField(
        max_digits=10, decimal_places=2,
        required=False, allow_null=True, write_only=True,
    )
    quality_certification = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, write_only=True,
    )
    available_from = serializers.DateField(
        required=False, allow_null=True, write_only=True,
    )
    available_until = serializers.DateField(
        required=False, allow_null=True, write_only=True,
    )
    # Lifecycle + visibility shortcuts for the first batch — let the FPO
    # create a product with a batch already in ACTIVE state and/or opted
    # into the public Market Hub in one request.
    is_public = serializers.BooleanField(required=False, write_only=True)
    status = serializers.ChoiceField(
        choices=[ProductStock.Status.DRAFT, ProductStock.Status.ACTIVE],
        required=False, write_only=True,
    )

    # Read-only flat view of the latest batch (keeps the old FE working).
    latest_stock = serializers.SerializerMethodField()
    has_stock = serializers.SerializerMethodField()
    # Human-readable commodity labels so the FE doesn't have to resolve
    # MasterLookup ids against a separate dropdown fetch just to render a
    # product row. Language-sensitive — uses MasterLookup.get_name().
    commodity_code = serializers.CharField(source='commodity.code', read_only=True)
    commodity_name = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'fpo', 'name', 'commodity', 'commodity_code', 'commodity_name',
            'description', 'image',
            'stocks', 'latest_stock', 'has_stock',
            # Write-only shortcut fields for creating the first batch
            'quantity', 'unit', 'price_per_unit', 'quality_certification',
            'available_from', 'available_until', 'is_public', 'status',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'fpo', 'created_at', 'updated_at']

    def get_commodity_name(self, obj):
        if not obj.commodity_id:
            return ''
        lang = self.context.get('lang') or getattr(self.context.get('request'), 'language', 'en')
        return obj.commodity.get_name(lang) or obj.commodity.code

    def get_stocks(self, obj):
        cache = getattr(obj, '_prefetched_objects_cache', None)
        if cache and 'stocks' in cache:
            stocks = [s for s in cache['stocks'] if not s.is_deleted]
        else:
            stocks = obj.stocks.filter(is_deleted=False).order_by('-created_at')
        return ProductStockSerializer(stocks, many=True, context=self.context).data

    def get_latest_stock(self, obj):
        s = obj.latest_stock
        return ProductStockSerializer(s).data if s else None

    def get_has_stock(self, obj):
        cache = getattr(obj, '_prefetched_objects_cache', None)
        if cache and 'stocks' in cache:
            return len(cache['stocks']) > 0
        return obj.stocks.exists()

    def validate_image(self, value):
        if value is None:
            return value
        return _compress_product_image(value)

    def _pop_initial_stock_fields(self, validated_data):
        """Pop the write-only flat stock fields out of validated_data so
        they don't get passed to Product.objects.create()."""
        return {
            field: validated_data.pop(field)
            for field in (
                'quantity', 'unit', 'price_per_unit', 'quality_certification',
                'available_from', 'available_until', 'is_public', 'status',
            )
            if field in validated_data
        }

    def create(self, validated_data):
        stock_data = self._pop_initial_stock_fields(validated_data)
        validated_data['fpo'] = get_member_fpo(self.context['request'].user)
        product = super().create(validated_data)
        # Only create the first batch if the FPO actually sent stock details.
        # Omitting them is fine — the product sits as "No active stock" until
        # a batch is added via POST /products/{id}/stocks/.
        if stock_data.get('quantity') is not None and stock_data.get('price_per_unit') is not None:
            ProductStock.objects.create(product=product, **stock_data)
        return product

    def update(self, instance, validated_data):
        # Stock edits don't flow through the product endpoint anymore —
        # drop any flat stock fields silently so an old FE's PATCH still
        # updates the master fields instead of 400'ing on them.
        self._pop_initial_stock_fields(validated_data)
        return super().update(instance, validated_data)


class BuyerDirectorySerializer(serializers.ModelSerializer):
    account_active = serializers.SerializerMethodField()

    class Meta:
        model = BuyerDirectory
        fields = [
            'id', 'name', 'organisation', 'contact_email', 'contact_phone', 'location',
            'commodities_interested', 'min_quantity', 'max_quantity', 'unit', 'is_verified',
            'fpo', 'user', 'status', 'account_active', 'created_at', 'updated_at',
        ]
        # Admin manages this directly (ARUNIMA.md: "Buyer Directory (Admin only)"),
        # so is_verified is writable here — set explicitly via the /verify/ action instead
        # of raw PATCH, see BuyerDirectoryViewSet.
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_account_active(self, obj):
        """
        True/False if the buyer has a linked login account (external buyer.user,
        or FPO-as-buyer's fpo.primary_user). None if there's no linked account
        at all (e.g. admin-added buyer with no login) — frontend should hide
        the Activate/Deactivate action entirely in that case.
        """
        if obj.user_id:
            return obj.user.is_active
        if obj.fpo_id and obj.fpo.primary_user_id:
            return obj.fpo.primary_user.is_active
        return None


class BuyerSellerMatchSerializer(serializers.ModelSerializer):
    product_detail = ProductSerializer(source='product', read_only=True)
    buyer_detail = BuyerDirectorySerializer(source='buyer', read_only=True)

    class Meta:
        model = BuyerSellerMatch
        fields = [
            'id', 'product', 'buyer', 'product_detail', 'buyer_detail',
            'match_score', 'status', 'suggested_at',
        ]
        read_only_fields = ['id', 'match_score', 'status', 'suggested_at']


class MarketPriceSerializer(serializers.ModelSerializer):
    class Meta:
        model = MarketPrice
        fields = [
            'id', 'commodity', 'market_name', 'date',
            'min_price', 'max_price', 'modal_price', 'source',
        ]
        read_only_fields = ['id']

class BuyerProductSerializer(serializers.ModelSerializer):
    """
    One card per **stock batch** on the buyer-facing catalog (NOT per
    Product). A single Product with two active batches surfaces as two
    cards — different quantities/prices/validity — so buyers can inquire
    on the specific batch they want.

    `id` is the ProductStock id (what the inquiry endpoint expects).
    `product_id` is kept alongside for buyer-side "view all batches of
    this product" navigation.
    """
    product_id   = serializers.IntegerField(source='product.id', read_only=True)
    name         = serializers.JSONField(source='product.name', read_only=True)
    description  = serializers.JSONField(source='product.description', read_only=True)
    image        = serializers.ImageField(source='product.image', read_only=True)
    fpo          = serializers.IntegerField(source='product.fpo_id', read_only=True)
    fpo_name     = serializers.CharField(source='product.fpo.name', read_only=True)
    commodity_code = serializers.CharField(source='product.commodity.code', read_only=True)
    commodity_name = serializers.SerializerMethodField()
    # KAU #3 — "Validity is over" grace window flags for the buyer UI.
    in_grace_period = serializers.SerializerMethodField()
    grace_message   = serializers.SerializerMethodField()

    class Meta:
        model = ProductStock
        fields = [
            'id', 'product_id', 'name', 'description',
            'commodity_code', 'commodity_name',
            'quantity', 'unit', 'price_per_unit', 'quality_certification',
            'available_from', 'available_until',
            'fpo', 'fpo_name', 'image',
            'contact_phone',
            'in_grace_period', 'grace_message',
        ]
        read_only_fields = fields

    def get_commodity_name(self, obj):
        lang = self.context.get('lang', 'en')
        commodity = obj.product.commodity if obj.product_id else None
        return commodity.get_name(lang) if commodity else ''

    def get_in_grace_period(self, obj):
        return obj.status == ProductStock.Status.EXPIRED

    def get_grace_message(self, obj):
        if not self.get_in_grace_period(obj):
            return None
        lang = self.context.get('lang', 'en')
        if lang == 'ml':
            return 'സാധുത കഴിഞ്ഞു — പക്ഷേ വീണ്ടും സ്റ്റോക്ക് വന്നിട്ടുണ്ടോ എന്നറിയാൻ വിൽപ്പനക്കാരനെ ബന്ധപ്പെടുക.'
        return "Validity is over — but please contact the buyer to know if it's restocked."


class InquiryCreateSerializer(serializers.ModelSerializer):
    """
    Used when a verified buyer (FPO-as-buyer or external buyer) submits a
    purchase inquiry on a specific stock batch of a product. `stock` comes
    from the URL (the `pk` is a ProductStock id), not the request body —
    same reasoning as `buyer`/`contact_user` being resolved server-side
    rather than trusted from client input. The stock batch is passed via
    serializer context so we can validate requested quantity against its
    available quantity.
    """
    class Meta:
        model = Inquiry
        fields = ['id', 'quantity_requested', 'message']
        read_only_fields = ['id']
        # The model's TextField is unbounded; the inquiry dialog caps it at 500 chars.
        extra_kwargs = {'message': {'max_length': 500}}

    def validate_quantity_requested(self, value):
        if value <= 0:
            raise serializers.ValidationError('Quantity requested must be greater than 0.')
        stock = self.context.get('stock')
        if stock is not None and value > stock.quantity:
            raise serializers.ValidationError(
                f'Quantity requested cannot exceed available stock ({stock.quantity} {stock.unit}).'
            )
        return value


class InquirySerializer(serializers.ModelSerializer):
    """
    Used on the seller's Inquiries list (/fpo/products "View Inquiries" toggle).
    Read-only — status changes go through dedicated mark-contacted/mark-resolved
    actions, not raw PATCH (same pattern as BuyerDirectorySerializer.is_verified).

    contact_name/phone/email are resolved LIVE from Inquiry.contact_user at
    request time — never stored/snapshotted on the Inquiry itself. If
    contact_user is null (account was later deleted), all three resolve to
    None — frontend displays "Contact no longer available" in that case.
    """
    product_name = serializers.SerializerMethodField()
    buyer_name = serializers.SerializerMethodField()
    contact_name = serializers.SerializerMethodField()
    contact_phone = serializers.SerializerMethodField()
    contact_email = serializers.SerializerMethodField()

    class Meta:
        model = Inquiry
        fields = [
            'id', 'product', 'product_name', 'buyer', 'buyer_name',
            'quantity_requested', 'message', 'status',
            'contact_name', 'contact_phone', 'contact_email',
            'created_at',
        ]
        read_only_fields = fields

    def get_product_name(self, obj):
        return obj.product.name.get('en', '') if obj.product and obj.product.name else ''

    def get_buyer_name(self, obj):
        """FPO's name if this is an FPO-as-buyer inquiry, else the external
        buyer's own name — same fpo-vs-external distinction used elsewhere
        (see BuyerDirectorySerializer.get_account_active)."""
        if obj.buyer.fpo_id:
            return obj.buyer.fpo.name
        return obj.buyer.name

    def get_contact_name(self, obj):
        if not obj.contact_user_id:
            return None
        u = obj.contact_user
        return f'{u.first_name} {u.last_name}'.strip() or u.username

    def get_contact_phone(self, obj):
        if not obj.contact_user_id:
            return None
        return getattr(getattr(obj.contact_user, 'profile', None), 'phone', '') or None

    def get_contact_email(self, obj):
        if not obj.contact_user_id:
            return None
        return obj.contact_user.email or None

class MarketHubInquirySerializer(serializers.ModelSerializer):
    """
    Used on the seller's Market Hub Inquiries list (separate from the
    verified-buyer InquirySerializer above). Reads directly off
    BuyerSellerMatch + its linked (anonymous) BuyerDirectory row — no
    contact_user resolution needed here, since the buyer's name/email/phone
    were entered directly on the public form and stored on BuyerDirectory
    itself, not linked to any login account.

    status reuses BuyerSellerMatch's existing Suggested/Accepted/Rejected/
    Completed choices (shared with the algorithmic run_matching() feature)
    — displayed to the seller as Pending/Accepted/Rejected/Completed
    respectively; the frontend maps "suggested" -> "Pending" for display.
    """
    product_name = serializers.SerializerMethodField()
    name = serializers.CharField(source='buyer.name', read_only=True)
    email = serializers.CharField(source='buyer.contact_email', read_only=True)
    phone = serializers.CharField(source='buyer.contact_phone', read_only=True)
    created_at = serializers.DateTimeField(source='suggested_at', read_only=True)

    class Meta:
        model = BuyerSellerMatch
        fields = ['id', 'product', 'product_name', 'name', 'email', 'phone', 'message', 'status', 'created_at']
        read_only_fields = fields

    def get_product_name(self, obj):
        return obj.product.name.get('en', '') if obj.product and obj.product.name else ''