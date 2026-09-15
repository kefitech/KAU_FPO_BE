#Arunima S


from rest_framework import serializers

from apps.database.models import (
    BuyerDirectory,
    BuyerSellerMatch,
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
            'available_from', 'available_until', 'fpo_name', 'image',
        ]
        read_only_fields = fields