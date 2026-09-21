#Arunima S


from rest_framework import serializers

from apps.database.models import (
    BuyerDirectory,
    BuyerSellerMatch,
    Inquiry,
    MarketPrice,
    Product,
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


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = [
            'id', 'fpo', 'name', 'commodity', 'description', 'quantity', 'unit',
            'price_per_unit', 'quality_certification', 'available_from', 'available_until',
            'is_ondc_listed', 'ondc_product_id', 'is_public', 'status', 'image',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'fpo', 'is_ondc_listed', 'ondc_product_id', 'status',
                             'created_at', 'updated_at']

    def validate_image(self, value):
        if value is None:
            return value
        return _compress_product_image(value)

    def create(self, validated_data):
        validated_data['fpo'] = self.context['request'].user.fpo
        return super().create(validated_data)


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
    fpo_name = serializers.CharField(source='fpo.name', read_only=True)
    commodity_code = serializers.CharField(source='commodity.code', read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'description', 'commodity_code',
            'quantity', 'unit', 'price_per_unit', 'quality_certification',
            'available_from', 'available_until', 'fpo', 'fpo_name', 'image',
        ]
        read_only_fields = fields


class InquiryCreateSerializer(serializers.ModelSerializer):
    """
    Used when a verified buyer (FPO-as-buyer or external buyer) submits a
    purchase inquiry on a product. `product` comes from the URL, not the
    request body — same reasoning as `buyer`/`contact_user` being resolved
    server-side rather than trusted from client input. The product itself
    is passed via serializer context (not validated_data) so we can check
    the requested quantity against its available stock.
    """
    class Meta:
        model = Inquiry
        fields = ['id', 'quantity_requested', 'message']
        read_only_fields = ['id']

    def validate_quantity_requested(self, value):
        if value <= 0:
            raise serializers.ValidationError('Quantity requested must be greater than 0.')
        product = self.context.get('product')
        if product is not None and value > product.quantity:
            raise serializers.ValidationError(
                f'Quantity requested cannot exceed available stock ({product.quantity} {product.unit}).'
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