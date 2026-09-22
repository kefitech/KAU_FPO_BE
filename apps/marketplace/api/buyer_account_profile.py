"""
Buyer Personal Account Profile API
=====================================
GET   /api/marketplace/buyer/me/profile/  — view personal profile
PATCH /api/marketplace/buyer/me/profile/  — update personal profile

Editable fields: first_name, last_name, phone, preferred_language

Mirrors apps/fpo/api/profile.py (FPOProfileView) exactly — same shared
UserProfile-based personal account fields (name, phone, language). The
only difference is the permission class: any authenticated external
buyer can use this, not just FPO managers. This is the buyer's PERSONAL
account profile (their own name/phone/login), separate from
BuyerProfileView (buyer/profile/), which manages their BUSINESS profile
(BuyerDirectory: location, commodities_interested, etc).
"""

from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.services.translation import t
from apps.core.utils.responses import StandardResponse
from apps.core.utils.validators import validate_indian_phone
from apps.database.models.user import UserProfile
from apps.marketplace.services import _get_buyer_row


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


class BuyerAccountProfileView(APIView):
    """
    GET   /api/marketplace/buyer/me/profile/ — personal profile for logged-in buyer
    PATCH /api/marketplace/buyer/me/profile/ — update first_name, last_name, phone, preferred_language
    """

    permission_classes = [IsAuthenticated]

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

    def patch(self, request):
        lang = getattr(request, 'language', 'en')
        user = request.user

        serializer = _ProfileSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return StandardResponse.validation_error(errors=serializer.errors)

        data       = serializer.validated_data
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

        # Keep BuyerDirectory (shown in Admin > Buyer Directory) in sync
        # whenever the buyer updates their personal name or phone here.
        # This is the one place the buyer is allowed to change these
        # indirectly — BuyerProfileView (business profile) still keeps
        # name/contact_phone locked from direct edits there.
        if user_fields or 'phone' in data:
            buyer_row = _get_buyer_row(user)
        else:
            buyer_row = None

        if user_fields and buyer_row is not None:
            buyer_row.name = f"{user.first_name} {user.last_name}".strip()
            buyer_row.save(update_fields=['name'])

        if 'phone' in data:
            profile.phone = data['phone']
            profile_fields.append('phone')

            if buyer_row is not None:
                buyer_row.contact_phone = data['phone']
                buyer_row.save(update_fields=['contact_phone'])

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