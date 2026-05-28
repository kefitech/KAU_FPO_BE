"""
FPO Member Roles API
====================
Base Path: /api/admin/fpo-member-roles/

Manages MasterLookup entries with category='fpo_member_role'.
These are the roles FPO members can have within their FPO (primary, secondary, treasurer...).

Request shape for create/update:
    {
        "code": "treasurer",
        "translations": { "en": "Treasurer", "ml": "ട്രഷറർ" },
        "is_active": true
    }

Response shape:
    {
        "id": 1,
        "code": "treasurer",
        "translations": { "en": "Treasurer", "ml": "ട്രഷറർ" },
        "is_active": true,
        "created_at": "..."
    }
"""

from rest_framework import serializers, filters, status
from rest_framework.decorators import action
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiExample

from apps.core.views import TranslatedViewSet
from apps.core.permissions.rbac import IsSuperAdmin
from apps.core.utils.responses import StandardResponse
from apps.core.utils.pagination import StandardPagination
from apps.core.services.translation import t
from apps.core.models.generic import MasterLookup
from apps.database.models.fpo import FPOAction, FPOMemberPermission

CATEGORY = 'fpo_member_role'


def _save_translations(obj, translations_data):
    """Save Translation rows for a MasterLookup role."""
    from apps.database.models import Language, Translation, TranslationCategory
    if not translations_data:
        return
    try:
        category = TranslationCategory.objects.get(code=CATEGORY)
    except TranslationCategory.DoesNotExist:
        return
    for lang_code, value in translations_data.items():
        if not value:
            continue
        lang = Language.objects.filter(code=lang_code, is_active=True).first()
        if not lang:
            continue
        Translation.objects.update_or_create(
            category=category, key=obj.code, language=lang,
            defaults={'value': value},
        )


def _get_translations(obj):
    """Read all Translation rows for a MasterLookup role."""
    from apps.database.models import Translation, TranslationCategory
    try:
        category = TranslationCategory.objects.get(code=CATEGORY)
        rows = Translation.objects.filter(
            category=category, key=obj.code
        ).select_related('language').values('language__code', 'value')
        return {row['language__code']: row['value'] for row in rows}
    except TranslationCategory.DoesNotExist:
        return {}


class FPOMemberRoleListSerializer(serializers.ModelSerializer):
    """Used for list view — shows which languages are translated, not the values."""

    translations = serializers.SerializerMethodField()

    class Meta:
        model  = MasterLookup
        fields = ['id', 'code', 'translations', 'is_active', 'created_at']

    def get_translations(self, instance):
        return list(_get_translations(instance).keys())


class FPOMemberRoleSerializer(serializers.ModelSerializer):
    """Used for create / retrieve / update — full translation values."""

    translations = serializers.DictField(
        child=serializers.CharField(),
        required=False,
        help_text=(
            'Display names per language code. English ("en") is required on create. '
            'Other languages can be added later via PATCH or bulk Excel import. '
            'e.g. {"en": "Treasurer", "ml": "ട്രഷറർ"}'
        )
    )

    class Meta:
        model  = MasterLookup
        fields = ['id', 'code', 'translations', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep['translations'] = _get_translations(instance)
        return rep

    def validate_translations(self, value):
        if not self.instance and not value.get('en'):
            raise serializers.ValidationError('English translation ("en") is required.')
        return value

    def validate_code(self, value):
        value = value.lower().replace(' ', '_')
        qs = MasterLookup.objects.filter(category=CATEGORY, code=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError('A role with this code already exists.')
        return value

    def create(self, validated_data):
        translations = validated_data.pop('translations', {})
        validated_data['category'] = CATEGORY
        obj = super().create(validated_data)
        _save_translations(obj, translations)
        # Seed default permission matrix rows (all denied) for every existing active action
        actions = FPOAction.objects.filter(is_active=True)
        FPOMemberPermission.objects.bulk_create([
            FPOMemberPermission(role=obj, action=action, is_allowed=False)
            for action in actions
        ], ignore_conflicts=True)
        return obj

    def update(self, instance, validated_data):
        translations = validated_data.pop('translations', {})
        obj = super().update(instance, validated_data)
        _save_translations(obj, translations)
        return obj


_ROLE_EXAMPLE = OpenApiExample(
    'Create role (English only — required)',
    value={
        'code': 'treasurer',
        'translations': {'en': 'Treasurer'},
        'is_active': True,
    },
    request_only=True,
)

_ROLE_RESPONSE_EXAMPLE = OpenApiExample(
    'Response after create/retrieve',
    value={
        'id': 1,
        'code': 'treasurer',
        'translations': {'en': 'Treasurer'},
        'is_active': True,
        'created_at': '2026-05-20T12:55:22+0530',
    },
    response_only=True,
)

_ROLE_DESCRIPTION = (
    'Manages FPO member roles — internal hierarchy within an FPO '
    '(e.g. primary user, secondary user, treasurer).\n\n'
    'The `translations` field accepts any active language code as a key '
    '(`en`, `ml`, `ta`, etc.). New languages added via the Languages API '
    'are automatically supported here.'
)


@extend_schema_view(
    list=extend_schema(
        tags=['Admin - FPO Roles'],
        summary='List FPO member roles',
        description=_ROLE_DESCRIPTION,
        examples=[_ROLE_RESPONSE_EXAMPLE],
    ),
    create=extend_schema(
        tags=['Admin - FPO Roles'],
        summary='Create FPO member role',
        description=_ROLE_DESCRIPTION,
        examples=[_ROLE_EXAMPLE, _ROLE_RESPONSE_EXAMPLE],
    ),
    retrieve=extend_schema(
        tags=['Admin - FPO Roles'],
        summary='Retrieve FPO member role',
        description=_ROLE_DESCRIPTION,
        examples=[_ROLE_RESPONSE_EXAMPLE],
    ),
    partial_update=extend_schema(
        tags=['Admin - FPO Roles'],
        summary='Update FPO member role',
        description='Update translations or active status. Code cannot be changed after creation.',
        examples=[_ROLE_EXAMPLE, _ROLE_RESPONSE_EXAMPLE],
    ),
    destroy=extend_schema(
        tags=['Admin - FPO Roles'],
        summary='Delete FPO member role',
        description='Cannot delete a role that is currently assigned to FPO members.',
    ),
)
class FPOMemberRoleViewSet(TranslatedViewSet):

    serializer_class   = FPOMemberRoleSerializer
    permission_classes = [IsSuperAdmin]
    pagination_class   = StandardPagination
    filter_backends    = [filters.SearchFilter, filters.OrderingFilter]
    search_fields      = ['code']
    ordering_fields    = ['code', 'created_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return FPOMemberRoleListSerializer
        return FPOMemberRoleSerializer

    list_message    = 'admin.fpo_roles_retrieved'
    create_message  = 'admin.fpo_role_created'
    update_message  = 'admin.fpo_role_updated'
    destroy_message = 'admin.fpo_role_deleted'

    def get_queryset(self):
        return MasterLookup.objects.filter(category=CATEGORY).order_by('code')

    def destroy(self, request, *args, **kwargs):
        role = self.get_object()
        if role.fpo_memberships.filter(is_deleted=False).exists():
            return StandardResponse.error(
                t('admin.fpo_role_has_members', request.language),
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        role.delete()
        return StandardResponse.success(message=t(self.destroy_message, request.language))

    @extend_schema(tags=['Admin - FPO Roles'], summary='Activate FPO member role')
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        role = self.get_object()
        role.is_active = True
        role.save(update_fields=['is_active'])
        return StandardResponse.success(
            data=self.get_serializer(role).data,
            message=t('admin.fpo_role_activated', request.language),
        )

    @extend_schema(tags=['Admin - FPO Roles'], summary='Deactivate FPO member role')
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        role = self.get_object()
        role.is_active = False
        role.save(update_fields=['is_active'])
        return StandardResponse.success(
            data=self.get_serializer(role).data,
            message=t('admin.fpo_role_deactivated', request.language),
        )
