#Arunima S


from rest_framework import serializers

from apps.database.models import (
    BuyerDirectory,
    BuyerSellerMatch,
    MarketPrice,
    Product,
)


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = [
            'id', 'fpo', 'name', 'commodity', 'description', 'quantity', 'unit',
            'price_per_unit', 'quality_certification', 'available_from', 'available_until',
            'is_ondc_listed', 'ondc_product_id', 'is_public', 'status',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'fpo', 'is_ondc_listed', 'ondc_product_id', 'status',
                             'created_at', 'updated_at']

    def create(self, validated_data):
        validated_data['fpo'] = self.context['request'].user.fpo
        return super().create(validated_data)


class BuyerDirectorySerializer(serializers.ModelSerializer):
    class Meta:
        model = BuyerDirectory
        fields = [
            'id', 'name', 'organisation', 'contact_email', 'contact_phone', 'location',
            'commodities_interested', 'min_quantity', 'max_quantity', 'unit', 'is_verified',
            'fpo', 'status', 'created_at', 'updated_at',
        ]
        # Admin manages this directly (ARUNIMA.md: "Buyer Directory (Admin only)"),
        # so is_verified is writable here — set explicitly via the /verify/ action instead
        # of raw PATCH, see BuyerDirectoryViewSet.
        read_only_fields = ['id', 'created_at', 'updated_at']


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