"""
Admin API Serializers for Multilingual System
=============================================

Serializers for managing languages, translation categories, and translations.

Author: Athul Gopan (Kefi Tech Solutions)
Created: 28-04-2026
SRS Reference: Section 3.1.7 (Multilingual Support)
"""

from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from apps.database.models import (
    Language,
    TranslationCategory,
    Translation,
)


class LanguageSerializer(serializers.ModelSerializer):
    """
    Language serializer for admin management.

    Allows KAU Admin to add new languages (Tamil, Hindi, etc.)
    """

    translation_count = serializers.SerializerMethodField()

    class Meta:
        model = Language
        fields = [
            'id',
            'code',
            'name',
            'native_name',
            'is_active',
            'is_default',
            'display_order',
            'is_rtl',
            'locale',
            'translation_count',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'translation_count']

    @extend_schema_field(serializers.IntegerField())
    def get_translation_count(self, obj):
        return obj.translations.count()

    def validate_code(self, value):
        """Validate language code format"""
        if not value.islower():
            raise serializers.ValidationError("Language code must be lowercase (e.g., 'en', 'ml', 'ta')")
        if len(value) < 2 or len(value) > 10:
            raise serializers.ValidationError("Language code must be 2-10 characters")
        return value


class TranslationCategorySerializer(serializers.ModelSerializer):
    """
    Translation category serializer.

    For organizing translations into logical groups.
    """

    translation_count = serializers.SerializerMethodField()

    class Meta:
        model = TranslationCategory
        fields = [
            'id',
            'code',
            'name',
            'description',
            'display_order',
            'translation_count',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'translation_count']

    @extend_schema_field(serializers.IntegerField())
    def get_translation_count(self, obj):
        return obj.translations.count()


class TranslationSerializer(serializers.ModelSerializer):
    """
    Translation serializer for admin management.

    Allows KAU Admin to add/edit translations for any language.
    """

    category_code = serializers.CharField(source='category.code', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    language_code = serializers.CharField(source='language.code', read_only=True)
    language_name = serializers.CharField(source='language.native_name', read_only=True)
    full_key = serializers.CharField(read_only=True)
    verified_by_name = serializers.CharField(source='verified_by.get_full_name', read_only=True)

    class Meta:
        model = Translation
        fields = [
            'id',
            'category',
            'category_code',
            'category_name',
            'key',
            'full_key',
            'language',
            'language_code',
            'language_name',
            'value',
            'context',
            'variables',
            'is_verified',
            'verified_by',
            'verified_by_name',
            'verified_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'full_key',
            'category_code',
            'category_name',
            'language_code',
            'language_name',
            'verified_by',
            'verified_by_name',
            'verified_at',
            'created_at',
            'updated_at',
        ]

    def validate(self, data):
        """Validate translation data"""
        # Check for duplicate (category + key + language)
        category = data.get('category')
        key = data.get('key')
        language = data.get('language')

        if category and key and language:
            # Check if translation already exists (excluding current instance in updates)
            query = Translation.objects.filter(
                category=category,
                key=key,
                language=language
            )

            if self.instance:
                query = query.exclude(pk=self.instance.pk)

            if query.exists():
                raise serializers.ValidationError(
                    f"Translation already exists for {category.code}.{key} in {language.code}"
                )

        return data


class TranslationCreateSerializer(serializers.ModelSerializer):
    """
    Simplified serializer for creating translations.

    Accepts category_code and language_code instead of IDs.
    """

    category_code = serializers.CharField(write_only=True)
    language_code = serializers.CharField(write_only=True)

    class Meta:
        model = Translation
        fields = [
            'category_code',
            'language_code',
            'key',
            'value',
            'context',
            'variables',
        ]

    def validate(self, data):
        """Validate and convert codes to objects"""
        # Convert category_code to category object
        category_code = data.pop('category_code')
        try:
            category = TranslationCategory.objects.get(code=category_code)
            data['category'] = category
        except TranslationCategory.DoesNotExist:
            raise serializers.ValidationError({
                'category_code': f"Category '{category_code}' does not exist"
            })

        # Convert language_code to language object
        language_code = data.pop('language_code')
        try:
            language = Language.objects.get(code=language_code, is_active=True)
            data['language'] = language
        except Language.DoesNotExist:
            raise serializers.ValidationError({
                'language_code': f"Language '{language_code}' does not exist or is inactive"
            })

        # Check for duplicate
        if Translation.objects.filter(
            category=data['category'],
            key=data['key'],
            language=data['language']
        ).exists():
            raise serializers.ValidationError(
                f"Translation already exists for {category_code}.{data['key']} in {language_code}"
            )

        return data

    def create(self, validated_data):
        """Create translation with is_verified=False by default"""
        validated_data['is_verified'] = False
        return super().create(validated_data)


class BulkTranslationSerializer(serializers.Serializer):
    """
    Serializer for bulk translation import.

    Accepts CSV/Excel data and creates multiple translations.
    """

    category_code = serializers.CharField()
    language_code = serializers.CharField()
    translations = serializers.ListField(
        child=serializers.DictField(),
        help_text="List of {key: 'translation_key', value: 'translated text'}"
    )

    def validate(self, data):
        """Validate bulk import data"""
        # Validate category exists
        category_code = data['category_code']
        try:
            category = TranslationCategory.objects.get(code=category_code)
            data['category'] = category
        except TranslationCategory.DoesNotExist:
            raise serializers.ValidationError({
                'category_code': f"Category '{category_code}' does not exist"
            })

        # Validate language exists
        language_code = data['language_code']
        try:
            language = Language.objects.get(code=language_code, is_active=True)
            data['language'] = language
        except Language.DoesNotExist:
            raise serializers.ValidationError({
                'language_code': f"Language '{language_code}' does not exist or is inactive"
            })

        # Validate translations list
        translations = data['translations']
        if not translations:
            raise serializers.ValidationError({
                'translations': 'At least one translation is required'
            })

        for trans in translations:
            if 'key' not in trans or 'value' not in trans:
                raise serializers.ValidationError({
                    'translations': 'Each translation must have "key" and "value" fields'
                })

        return data
