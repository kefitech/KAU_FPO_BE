"""
FPO Member Roles API
====================
Base Path: /api/admin/fpo-member-roles/

Manages FPO-internal role Groups (primary, secondary, treasurer, etc.).
These are the roles FPO members can hold within their own FPO — separate from
system roles (super_admin, sub_admin, fpo_manager, etc.) which are managed via
/api/auth/roles/.

When a new role is created here, default RoleActionPermission rows (all denied)
are seeded automatically for every active FPOAction.

Request shape for create:
    {
        "name": "treasurer",
        "translations": { "en": "Treasurer", "ml": "ട്രഷറർ" }
    }

Response shape:
    {
        "id": 1,
        "name": "treasurer",
        "translations": { "en": "Treasurer", "ml": "ട്രഷറർ" }
    }
"""

from django.contrib.auth.models import Group
from rest_framework import serializers, filters, status
from rest_framework.decorators import action
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiExample

from apps.core.views import TranslatedViewSet
from apps.core.permissions.rbac import IsSuperAdmin
from apps.core.utils.responses import StandardResponse
from apps.core.utils.pagination import StandardPagination
from apps.core.services.translation import t
from apps.database.models.fpo import FPOAction, RoleActionPermission

# System roles managed via /api/auth/roles/ — excluded from this ViewSet
SYSTEM_GROUPS = {
    'super_admin', 'sub_admin', 'fpo_manager',
    'government', 'cbbo', 'expert', 'viewer', 'admin',
}

TRANSLATION_CATEGORY = 'fpo_member_role'


def _save_translations(group, translations_data):
    """Save Translation rows for an FPO member role Group."""
    from apps.database.models import Language, Translation, TranslationCategory
    if not translations_data:
        return
    try:
        category = TranslationCategory.objects.get(code=TRANSLATION_CATEGORY)
    except TranslationCategory.DoesNotExist:
        return
    for lang_code, value in translations_data.items():
        if not value:
            continue
        lang = Language.objects.filter(code=lang_code, is_active=True).first()
        if not lang:
            continue
        Translation.objects.update_or_create(
            category=category, key=group.name, language=lang,
            defaults={'value': value},
        )


def _get_translations(group):
    """Read all Translation rows for an FPO member role Group."""
    from apps.database.models import Translation, TranslationCategory
    try:
        category = TranslationCategory.objects.get(code=TRANSLATION_CATEGORY)
        rows = Translation.objects.filter(
            category=category, key=group.name
        ).select_related('language').values('language__code', 'value')
        return {row['language__code']: row['value'] for row in rows}
    except TranslationCategory.DoesNotExist:
        return {}


class FPOMemberRoleListSerializer(serializers.ModelSerializer):
    translations = serializers.SerializerMethodField()

    class Meta:
        model  = Group
        fields = ['id', 'name', 'translations']

    def get_translations(self, instance):
        return list(_get_translations(instance).keys())


class FPOMemberRoleSerializer(serializers.ModelSerializer):
    translations = serializers.DictField(
        child=serializers.CharField(),
        required=False,
        help_text=(
            'Display names per language code. English ("en") is required on create. '
            'e.g. {"en": "Treasurer", "ml": "ട്രഷറർ"}'
        )
    )

    class Meta:
        model  = Group
        fields = ['id', 'name', 'translations']
        read_only_fields = ['id']

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep['translations'] = _get_translations(instance)
        return rep

    def validate_translations(self, value):
        if not self.instance and not value.get('en'):
            raise serializers.ValidationError('English translation ("en") is required.')
        return value

    def validate_name(self, value):
        value = value.lower().replace(' ', '_')
        if value in SYSTEM_GROUPS:
            raise serializers.ValidationError('This name is reserved for a system role.')
        qs = Group.objects.filter(name=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError('A role with this name already exists.')
        return value

    def create(self, validated_data):
        translations = validated_data.pop('translations', {})
        group = Group.objects.create(name=validated_data['name'])
        _save_translations(group, translations)
        # Seed default permission matrix rows (all denied) for every active action
        actions = FPOAction.objects.filter(is_active=True)
        RoleActionPermission.objects.bulk_create([
            RoleActionPermission(role=group, action=action, is_allowed=False)
            for action in actions
        ], ignore_conflicts=True)
        return group

    def update(self, instance, validated_data):
        translations = validated_data.pop('translations', {})
        instance.name = validated_data.get('name', instance.name)
        instance.save()
        _save_translations(instance, translations)
        return instance


_ROLE_EXAMPLE = OpenApiExample(
    'Create role (English required)',
    value={'name': 'treasurer', 'translations': {'en': 'Treasurer'}},
    request_only=True,
)

_ROLE_RESPONSE_EXAMPLE = OpenApiExample(
    'Response after create/retrieve',
    value={'id': 1, 'name': 'treasurer', 'translations': {'en': 'Treasurer'}},
    response_only=True,
)

_ROLE_DESCRIPTION = (
    'Manages FPO-internal role Groups — the member hierarchy within an FPO '
    '(e.g. primary user, secondary user, treasurer).\n\n'
    'System roles (super_admin, sub_admin, fpo_manager, etc.) are managed via '
    '`/api/auth/roles/` and are excluded from this endpoint.\n\n'
    'The `translations` field accepts any active language code '
    '(`en`, `ml`, `ta`, etc.).'
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
        description='Update name or translations.',
        examples=[_ROLE_EXAMPLE, _ROLE_RESPONSE_EXAMPLE],
    ),
    destroy=extend_schema(
        tags=['Admin - FPO Roles'],
        summary='Delete FPO member role',
        description='Cannot delete a role currently assigned to FPO members.',
    ),
)
class FPOMemberRoleViewSet(TranslatedViewSet):

    serializer_class   = FPOMemberRoleSerializer
    permission_classes = [IsSuperAdmin]
    pagination_class   = StandardPagination
    filter_backends    = [filters.SearchFilter, filters.OrderingFilter]
    search_fields      = ['name']
    ordering_fields    = ['name']

    def get_serializer_class(self):
        if self.action == 'list':
            return FPOMemberRoleListSerializer
        return FPOMemberRoleSerializer

    list_message    = 'admin.fpo_roles_retrieved'
    create_message  = 'admin.fpo_role_created'
    update_message  = 'admin.fpo_role_updated'
    destroy_message = 'admin.fpo_role_deleted'

    def get_queryset(self):
        return Group.objects.exclude(name__in=SYSTEM_GROUPS).order_by('name')

    def destroy(self, request, *args, **kwargs):
        role = self.get_object()
        if role.fpo_memberships.filter(is_deleted=False).exists():
            return StandardResponse.error(
                t('admin.fpo_role_has_members', request.language),
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        role.delete()
        return StandardResponse.success(message=t(self.destroy_message, request.language))
