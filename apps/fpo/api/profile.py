"""
FPO User Profile API
=====================
GET   /api/fpo/me/profile/  — view personal profile
PATCH /api/fpo/me/profile/  — update personal profile

Editable fields: first_name, last_name, phone, preferred_language
"""

from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import serializers, status
from rest_framework.views import APIView

from apps.core.permissions.rbac import IsFPOManager
from apps.core.services.translation import t
from apps.core.utils.responses import StandardResponse
from apps.core.utils.validators import validate_indian_phone
from apps.database.models.user import UserProfile


class _ProfileSerializer(serializers.Serializer):
    first_name         = serializers.CharField(max_length=150, required=False)
    last_name          = serializers.CharField(max_length=150, required=False, allow_blank=True)
    phone              = serializers.CharField(max_length=20,  required=False, allow_blank=True)
    preferred_language = serializers.CharField(max_length=10,  required=False)

    def validate_phone(self, value):
        if value:
            validate_indian_phone(value)
        return value

    def validate_preferred_language(self, value):
        from apps.database.models.language import Language
        active_codes = [lang["code"] for lang in Language.get_active_languages()]
        if value not in active_codes:
            raise serializers.ValidationError(f'Language "{value}" is not supported.')
        return value


class FPOProfileView(APIView):
    """
    GET   /api/fpo/me/profile/ — personal profile for logged-in FPO user
    PATCH /api/fpo/me/profile/ — update first_name, last_name, phone, preferred_language
    """

    permission_classes = [IsFPOManager]

    @extend_schema(
        tags=['FPO - Profile'],
        summary='Get FPO user profile',
        description='Returns the personal profile of the logged-in FPO user.',
        responses={200: OpenApiResponse(description='Profile data')},
    )
    def get(self, request):
        lang    = getattr(request, 'language', 'en')
        user    = request.user
        profile = getattr(user, 'profile', None)

        data = {
            'id':                 user.id,
            'email':              user.email,
            'first_name':         user.first_name,
            'last_name':          user.last_name,
            'phone':              profile.phone if profile else '',
            'preferred_language': profile.preferred_language if profile else 'en',
        }

        return StandardResponse.success(data, t('auth.profile_retrieved', lang))

    @extend_schema(
        tags=['FPO - Profile'],
        summary='Update FPO user profile',
        description='Update first_name, last_name, phone, or preferred_language for the logged-in FPO user.',
        request=_ProfileSerializer,
        responses={200: OpenApiResponse(description='Updated profile')},
    )
    def patch(self, request):
        lang = getattr(request, 'language', 'en')
        user = request.user

        serializer = _ProfileSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return StandardResponse.validation_error(errors=serializer.errors)

        data    = serializer.validated_data
        profile, _ = UserProfile.objects.get_or_create(user=user)

        user_fields    = []
        profile_fields = []

        if 'first_name' in data:
            user.first_name = data['first_name']
            user_fields.append('first_name')

        if 'last_name' in data:
            user.last_name = data['last_name']
            user_fields.append('last_name')

        if user_fields:
            user.save(update_fields=user_fields)

        if 'phone' in data:
            profile.phone = data['phone']
            profile_fields.append('phone')

        if 'preferred_language' in data:
            profile.preferred_language = data['preferred_language']
            profile_fields.append('preferred_language')

        if profile_fields:
            profile.save(update_fields=profile_fields)

        return StandardResponse.success(
            {
                'id':                 user.id,
                'email':              user.email,
                'first_name':         user.first_name,
                'last_name':          user.last_name,
                'phone':              profile.phone,
                'preferred_language': profile.preferred_language,
            },
            t('auth.profile_updated', lang),
        )
