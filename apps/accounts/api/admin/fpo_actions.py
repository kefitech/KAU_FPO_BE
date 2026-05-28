"""
FPO Actions API
===============
Base Path: /api/admin/fpo-actions/

Manages FPOAction registry — the set of actions that can be performed within an FPO.
Actions are seeded by developers. Admin can edit translations/description and toggle is_active.
Action code is immutable once set — used in permission checks throughout the codebase.

Request shape for create:
    {
        "code": "can_view_financials",
        "translations": { "en": "View Financials", "ml": "സാമ്പത്തിക വിവരങ്ങൾ കാണുക" },
        "description": "View financial reports and bank details"
    }

Request shape for update (PATCH):
    {
        "translations": { "en": "View Financial Reports", "ml": "..." },
        "description": "Updated description"
    }
    Note: code cannot be changed after creation.
"""

from rest_framework import serializers, filters, status
from rest_framework.decorators import action
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiExample

from apps.core.views import TranslatedViewSet
from apps.core.permissions.rbac import IsSuperAdmin
from apps.core.utils.responses import StandardResponse
from apps.core.utils.pagination import StandardPagination
from apps.core.services.translation import t
from apps.database.models.fpo import FPOAction, FPOMemberPermission
from apps.core.models.generic import MasterLookup

TRANSLATION_CATEGORY = 'fpo_action'


def _save_translations(obj, translations_data):
    """Save Translation rows for an FPOAction."""
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
            category=category, key=obj.code, language=lang,
            defaults={'value': value},
        )


def _get_translations(obj):
    """Read all Translation rows for an FPOAction."""
    from apps.database.models import Translation, TranslationCategory
    try:
        category = TranslationCategory.objects.get(code=TRANSLATION_CATEGORY)
        rows = Translation.objects.filter(
            category=category, key=obj.code
        ).select_related('language').values('language__code', 'value')
        return {row['language__code']: row['value'] for row in rows}
    except TranslationCategory.DoesNotExist:
        return {}


class FPOActionListSerializer(serializers.ModelSerializer):
    """
    Used for list view.
    Default: translations = ["en", "ml"]  (which languages exist)
    With ?labels=true: translations = "Delete Documents"  (resolved label for X-Language)
    """

    translations = serializers.SerializerMethodField()

    class Meta:
        model  = FPOAction
        fields = ['id', 'code', 'translations', 'description', 'is_active', 'created_at']

    def get_translations(self, instance):
        request = self.context.get('request')
        if request and request.GET.get('labels') == 'true':
            language = getattr(request, 'language', 'en')
            return instance.get_label(language)
        return list(_get_translations(instance).keys())


class FPOActionSerializer(serializers.ModelSerializer):
    """Used for create / retrieve / update — full translation values."""

    translations = serializers.DictField(
        child=serializers.CharField(),
        required=False,
        help_text=(
            'Display labels per language code. English ("en") is required on create. '
            'Other languages can be added later via PATCH or bulk Excel import. '
            'e.g. {"en": "Submit Application", "ml": "അപേക്ഷ സമർപ്പിക്കുക"}'
        )
    )

    class Meta:
        model  = FPOAction
        fields = ['id', 'code', 'translations', 'description', 'is_active', 'created_at']
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
        if self.instance:
            return self.instance.code
        value = value.lower().replace(' ', '_')
        if FPOAction.objects.filter(code=value).exists():
            raise serializers.ValidationError('An action with this code already exists.')
        return value

    def create(self, validated_data):
        translations = validated_data.pop('translations', {})
        obj = super().create(validated_data)
        _save_translations(obj, translations)
        # Seed default permission matrix rows (all denied) for every existing role
        roles = MasterLookup.objects.filter(category='fpo_member_role', is_active=True)
        FPOMemberPermission.objects.bulk_create([
            FPOMemberPermission(role=role, action=obj, is_allowed=False)
            for role in roles
        ], ignore_conflicts=True)
        return obj

    def update(self, instance, validated_data):
        validated_data.pop('code', None)
        translations = validated_data.pop('translations', {})
        obj = super().update(instance, validated_data)
        _save_translations(obj, translations)
        return obj


_TRANSLATIONS_EXAMPLE = OpenApiExample(
    'Create action (English only — required)',
    value={
        'code': 'can_view_financials',
        'translations': {'en': 'View Financials'},
        'description': 'View financial reports and bank details',
    },
    request_only=True,
)

_TRANSLATIONS_RESPONSE_EXAMPLE = OpenApiExample(
    'Response after create/retrieve',
    value={
        'id': 1,
        'code': 'can_view_financials',
        'translations': {'en': 'View Financials'},
        'description': 'View financial reports and bank details',
        'is_active': True,
        'created_at': '2026-05-20T12:55:22+0530',
    },
    response_only=True,
)

_SCHEMA_DESCRIPTION = (
    'Manages FPO actions — the set of operations that can be performed within an FPO.\n\n'
    'Actions are seeded by developers. Admin can edit translations and description, '
    'and toggle active status. **Action code is immutable after creation.**\n\n'
    'The `translations` field accepts any active language code as a key '
    '(e.g. `en`, `ml`, `ta`). Adding a new language via the Languages API '
    'automatically makes it available here — no code change needed.'
)


@extend_schema_view(
    list=extend_schema(
        tags=['Admin - FPO Actions'],
        summary='List FPO actions',
        description=_SCHEMA_DESCRIPTION,
        examples=[_TRANSLATIONS_RESPONSE_EXAMPLE],
    ),
    create=extend_schema(
        tags=['Admin - FPO Actions'],
        summary='Create FPO action',
        description=_SCHEMA_DESCRIPTION,
        examples=[_TRANSLATIONS_EXAMPLE, _TRANSLATIONS_RESPONSE_EXAMPLE],
    ),
    retrieve=extend_schema(
        tags=['Admin - FPO Actions'],
        summary='Retrieve FPO action',
        description=_SCHEMA_DESCRIPTION,
        examples=[_TRANSLATIONS_RESPONSE_EXAMPLE],
    ),
    partial_update=extend_schema(
        tags=['Admin - FPO Actions'],
        summary='Update FPO action',
        description='Update translations or description. Code cannot be changed after creation.',
        examples=[_TRANSLATIONS_EXAMPLE, _TRANSLATIONS_RESPONSE_EXAMPLE],
    ),
    destroy=extend_schema(
        tags=['Admin - FPO Actions'],
        summary='Delete FPO action',
        description='Cannot delete an action that is assigned in the permission matrix.',
    ),
)
class FPOActionViewSet(TranslatedViewSet):

    queryset           = FPOAction.objects.all().order_by('code')
    serializer_class   = FPOActionSerializer
    permission_classes = [IsSuperAdmin]

    def get_serializer_class(self):
        if self.action == 'list':
            return FPOActionListSerializer
        return FPOActionSerializer
    pagination_class   = StandardPagination
    filter_backends    = [filters.SearchFilter, filters.OrderingFilter]
    search_fields      = ['code', 'description']
    ordering_fields    = ['code', 'created_at']
    http_method_names  = ['get', 'post', 'patch', 'delete', 'head', 'options']

    list_message    = 'admin.fpo_actions_retrieved'
    create_message  = 'admin.fpo_action_created'
    update_message  = 'admin.fpo_action_updated'
    destroy_message = 'admin.fpo_action_deleted'

    def destroy(self, request, *args, **kwargs):
        fpo_action = self.get_object()
        if fpo_action.role_permissions.exists():
            return StandardResponse.error(
                t('admin.fpo_action_has_permissions', request.language),
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        fpo_action.delete()
        return StandardResponse.success(message=t(self.destroy_message, request.language))

    @extend_schema(tags=['Admin - FPO Actions'], summary='Activate FPO action')
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        fpo_action = self.get_object()
        fpo_action.is_active = True
        fpo_action.save(update_fields=['is_active'])
        return StandardResponse.success(
            data=self.get_serializer(fpo_action).data,
            message=t('admin.fpo_action_activated', request.language),
        )

    @extend_schema(tags=['Admin - FPO Actions'], summary='Deactivate FPO action')
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        fpo_action = self.get_object()
        fpo_action.is_active = False
        fpo_action.save(update_fields=['is_active'])
        return StandardResponse.success(
            data=self.get_serializer(fpo_action).data,
            message=t('admin.fpo_action_deactivated', request.language),
        )
