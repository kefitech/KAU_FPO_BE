"""
Master Lookup Create APIs
=========================
For each of /api/admin/commodities/, /api/admin/promoting-agencies/ and /api/admin/banks/:

GET    <base>/                    — paginated list, including inactive
                                    (?page, ?page_size, ?search, ?is_active=true|false, ?ordering=[-]code|display_order|is_active|updated_at)
POST   <base>/                    — add an entry
GET    <base>/<id>/               — one entry
PATCH  <base>/<id>/               — edit names, description, order, active flag (and section for commodities)
POST   <base>/<id>/deactivate/    — hide from dropdowns; existing records stay valid
POST   <base>/<id>/activate/      — show in dropdowns again
DELETE <base>/<id>/               — permanent; refused with 409 if anything still uses the entry

Each entry lives in MasterLookup (category=<category>); its display names are
Translation rows in the matching translation category, keyed by the entry code.
The endpoints create both, so the entry shows up immediately in
GET /api/public/master-data/?category=<category>.

Request shape (commodities also take a required "section"):
    {
        "code": "black_pepper",
        "name_en": "Black Pepper",
        "name_ml": "കുരുമുളക്",
        "description": "optional",
        "display_order": 63,
        "is_active": true
    }
    name_ml defaults to name_en. display_order defaults to the end of the list —
    or just before the trailing "Other(s)" entry for categories that have one,
    so "Other" always stays last in the dropdown.
"""

from django.db import transaction
from django.db.models import F, Max, Q
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.views import APIView

from apps.core.models.generic import MasterLookup
from apps.core.permissions.rbac import IsSuperAdmin
from apps.core.utils.pagination import StandardPagination
from apps.core.utils.responses import StandardResponse
import re

from apps.database.models import (
    FPO, CropPackageOfPractices, CropZoneProfile, Language, Translation, TranslationCategory,
)

# Same sections used by the seeded commodities (scripts/seed_fpo_master_data.py)
COMMODITY_SECTIONS = [
    'agricultural',
    'horticultural_fruits',
    'horticultural_vegetables',
    'horticultural_tubers',
    'value_added',
]


class LookupCreateSerializer(serializers.Serializer):
    code          = serializers.RegexField(
        r'^[a-z0-9_]+$', max_length=50,
        help_text='Unique lowercase code — letters, digits and underscores (e.g. state_bank_of_india)',
    )
    name_en       = serializers.CharField(max_length=255)
    name_ml       = serializers.CharField(max_length=255, required=False, allow_blank=True)
    description   = serializers.CharField(required=False, allow_blank=True, default='')
    display_order = serializers.IntegerField(required=False, min_value=0)
    is_active     = serializers.BooleanField(required=False, default=True)

    def validate_code(self, value):
        if MasterLookup.objects.filter(category=self.context['category'], code=value).exists():
            raise serializers.ValidationError('An entry with this code already exists.')
        return value


class CommodityCreateSerializer(LookupCreateSerializer):
    section = serializers.ChoiceField(choices=COMMODITY_SECTIONS)


def slugify_code(name):
    return re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')[:50]


def name_taken(category, name, exclude_code=None):
    """True if another entry in this category already has this English name (case-insensitive)."""
    qs = Translation.objects.filter(category__code=category, language__code='en', value__iexact=name.strip())
    if exclude_code:
        qs = qs.exclude(key=exclude_code)
    return qs.exists()


class CropLookupCreateSerializer(LookupCreateSerializer):
    """
    Crop names and groups: the English name is what other tables store, so it must
    be unique; the code is optional and derived from the name when left out.
    """
    code = serializers.RegexField(r'^[a-z0-9_]+$', max_length=50, required=False)

    def validate(self, attrs):
        category = self.context['category']
        name = attrs['name_en'].strip()
        if name_taken(category, name):
            raise serializers.ValidationError({'name_en': 'An entry with this name already exists.'})
        if not attrs.get('code'):
            code = slugify_code(name)
            if not code:
                raise serializers.ValidationError({'name_en': 'Name must contain letters or digits.'})
            if MasterLookup.objects.filter(category=category, code=code).exists():
                raise serializers.ValidationError({'name_en': 'An entry with this name already exists.'})
            attrs['code'] = code
        return attrs


class LookupUpdateSerializer(serializers.Serializer):
    """PATCH body. The code is immutable — other tables reference it."""
    name_en       = serializers.CharField(max_length=255, required=False)
    name_ml       = serializers.CharField(max_length=255, required=False)
    description   = serializers.CharField(required=False, allow_blank=True)
    display_order = serializers.IntegerField(required=False, min_value=0)
    is_active     = serializers.BooleanField(required=False)

    def validate(self, attrs):
        if 'code' in self.initial_data:
            raise serializers.ValidationError({'code': 'The code cannot be changed.'})
        return attrs


class CommodityUpdateSerializer(LookupUpdateSerializer):
    section = serializers.ChoiceField(choices=COMMODITY_SECTIONS, required=False)


# FPO stores these categories' codes as plain text / JSON lists rather than foreign keys
FPO_CODE_FIELDS = {
    'commodity':        [('primary_commodities', 'list'), ('secondary_commodities', 'list')],
    'bank_name':        [('bank_name', 'text')],
    'promoting_agency': [('promoting_agency', 'text')],
}


# Crop names/groups are stored by their English name (not code) on the crop tables
NAME_REFERENCED_FIELDS = {
    'crop_name':  [(CropPackageOfPractices, 'crop_name'), (CropZoneProfile, 'crop_name')],
    'crop_group': [(CropPackageOfPractices, 'crop_group'), (CropZoneProfile, 'crop_group')],
}


def english_name(entry):
    return (
        Translation.objects.filter(category__code=entry.category, key=entry.code, language__code='en')
        .values_list('value', flat=True).first() or ''
    )


def find_name_usages(entry, name=None):
    """Rows on the crop tables whose crop_name/crop_group equals this entry's English name."""
    usages = {}
    name = name if name is not None else english_name(entry)
    if not name:
        return usages
    for model, field in NAME_REFERENCED_FIELDS.get(entry.category, []):
        count = model._base_manager.filter(**{f'{field}__iexact': name}).count()
        if count:
            usages[f'{model.__name__}.{field}'] = count
    return usages


def find_usages(entry):
    """Return {description: count} for everything that still references this entry."""
    usages = {}
    for rel in MasterLookup._meta.related_objects:
        count = rel.related_model._base_manager.filter(**{rel.field.name: entry}).count()
        if count:
            label = 'child entries' if rel.related_model is MasterLookup else rel.related_model.__name__
            usages[label] = count

    for field, kind in FPO_CODE_FIELDS.get(entry.category, []):
        lookup = f'{field}__contains' if kind == 'list' else field
        value = [entry.code] if kind == 'list' else entry.code
        count = FPO._base_manager.filter(**{lookup: value}).count()
        if count:
            usages[f'FPO.{field}'] = count
    usages.update(find_name_usages(entry))
    return usages


def serialize_entry(entry):
    names = {
        t.language.code: t.value
        for t in Translation.objects.filter(category__code=entry.category, key=entry.code)
                                    .select_related('language')
    }
    return {
        'id':            entry.id,
        'code':          entry.code,
        'name_en':       names.get('en', ''),
        'name_ml':       names.get('ml', ''),
        'description':   entry.description,
        'display_order': entry.display_order,
        'is_active':     entry.is_active,
        'metadata':      entry.metadata,
    }


def save_names(category, code, name_en=None, name_ml=None, label='', desc=''):
    tcat, _ = TranslationCategory.objects.get_or_create(
        code=category, defaults={'name': label, 'description': desc},
    )
    for lang_code, value in (('en', name_en), ('ml', name_ml)):
        if value is None:
            continue
        lang = Language.objects.filter(code=lang_code, is_active=True).first()
        if lang:
            Translation.objects.update_or_create(
                category=tcat, key=code, language=lang, defaults={'value': value},
            )


class LookupCreateView(APIView):
    """Base view — subclasses set the category and the serializer."""

    permission_classes = [IsSuperAdmin]

    category           = None
    serializer_class   = LookupCreateSerializer
    translation_label  = ''       # TranslationCategory.name if the category doesn't exist yet
    translation_desc   = ''
    trailing_code      = None     # code of the "Other" entry that must stay last, if any

    def get_metadata(self, data):
        return {}

    def _next_display_order(self):
        qs = MasterLookup.objects.filter(category=self.category)
        trailing = qs.filter(code=self.trailing_code).first() if self.trailing_code else None
        if trailing:
            # Take the trailing entry's slot and push it (and anything after) down one
            slot = trailing.display_order
            qs.filter(display_order__gte=slot).update(display_order=F('display_order') + 1)
            return slot
        last = qs.aggregate(m=Max('display_order'))['m']
        return 0 if last is None else last + 1

    def create_entry(self, request):
        serializer = self.serializer_class(data=request.data, context={'category': self.category})
        if not serializer.is_valid():
            return StandardResponse.validation_error(errors=serializer.errors)
        data = serializer.validated_data

        name_en = data['name_en'].strip()
        name_ml = (data.get('name_ml') or '').strip() or name_en

        with transaction.atomic():
            display_order = data.get('display_order')
            if display_order is None:
                display_order = self._next_display_order()

            entry = MasterLookup.objects.create(
                category=self.category,
                code=data['code'],
                description=data.get('description', ''),
                display_order=display_order,
                is_active=data.get('is_active', True),
                metadata=self.get_metadata(data),
            )

            save_names(self.category, entry.code, name_en, name_ml,
                       self.translation_label, self.translation_desc)

        return StandardResponse.created(data=serialize_entry(entry), message='Added.')

    def list_entries(self, request):
        qs = MasterLookup.objects.filter(category=self.category).order_by('display_order', 'code')
        is_active = request.query_params.get('is_active')
        if is_active in ('true', 'false'):
            qs = qs.filter(is_active=(is_active == 'true'))
        search = request.query_params.get('search', '').strip()
        if search:
            codes = Translation.objects.filter(
                category__code=self.category, value__icontains=search,
            ).values_list('key', flat=True)
            qs = qs.filter(Q(code__icontains=search) | Q(code__in=list(codes)))
        ordering = request.query_params.get('ordering', '').strip()
        if ordering.lstrip('-') in ('code', 'display_order', 'is_active', 'updated_at'):
            qs = qs.order_by(ordering, 'code')

        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response([serialize_entry(e) for e in page])


class LookupDetailView(APIView):
    """
    GET / PATCH / DELETE /<base>/<id>/ — one entry.
    Configured per category through as_view(category=..., ...) in urls.py.
    """

    permission_classes = [IsSuperAdmin]

    category          = None
    update_serializer = LookupUpdateSerializer
    translation_label = ''
    translation_desc  = ''
    has_section       = False

    def _get(self, pk):
        return MasterLookup.objects.filter(category=self.category, pk=pk).first()

    def _not_found(self):
        return StandardResponse.error('Not found.', status_code=404)

    @extend_schema(tags=['Admin - Master Data'], summary='Get one entry', responses={200: None, 404: None})
    def get(self, request, pk):
        entry = self._get(pk)
        if not entry:
            return self._not_found()
        return StandardResponse.success(data=serialize_entry(entry))

    @extend_schema(
        tags=['Admin - Master Data'],
        summary='Edit an entry',
        description='Partial update of names, description, display order and active flag '
                    '(and section for commodities). The code cannot be changed.',
        responses={200: None, 400: None, 404: None},
    )
    def patch(self, request, pk):
        entry = self._get(pk)
        if not entry:
            return self._not_found()
        serializer = self.update_serializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return StandardResponse.validation_error(errors=serializer.errors)
        data = serializer.validated_data

        # Crop names/groups are stored by name on other tables: keep names unique, and don't
        # rename one that rows still use (they would be left pointing at the old name)
        if 'name_en' in data and self.category in NAME_REFERENCED_FIELDS:
            new_name = data['name_en'].strip()
            if name_taken(self.category, new_name, exclude_code=entry.code):
                return StandardResponse.validation_error(
                    errors={'name_en': ['An entry with this name already exists.']},
                )
            if new_name != english_name(entry):
                usages = find_name_usages(entry)
                if usages:
                    return StandardResponse.error(
                        'This name is in use and cannot be changed. Add a new entry and deactivate this one instead.',
                        errors={'in_use': usages},
                        status_code=409,
                    )

        with transaction.atomic():
            fields = []
            for attr in ('description', 'display_order', 'is_active'):
                if attr in data:
                    setattr(entry, attr, data[attr])
                    fields.append(attr)
            if 'section' in data:
                entry.metadata = {**(entry.metadata or {}), 'section': data['section']}
                fields.append('metadata')
            if fields:
                entry.save(update_fields=fields + ['updated_at'])
            save_names(
                self.category, entry.code,
                data['name_en'].strip() if 'name_en' in data else None,
                data['name_ml'].strip() if 'name_ml' in data else None,
                self.translation_label, self.translation_desc,
            )
        return StandardResponse.success(data=serialize_entry(entry), message='Updated.')

    @extend_schema(
        tags=['Admin - Master Data'],
        summary='Delete an entry',
        description='Permanently deletes the entry and its names. Refused with 409 if anything '
                    'still uses it — deactivate it instead.',
        responses={200: None, 404: None, 409: None},
    )
    def delete(self, request, pk):
        entry = self._get(pk)
        if not entry:
            return self._not_found()
        usages = find_usages(entry)
        if usages:
            return StandardResponse.error(
                'This entry is in use and cannot be deleted. Deactivate it instead.',
                errors={'in_use': usages},
                status_code=409,
            )
        with transaction.atomic():
            Translation.objects.filter(category__code=self.category, key=entry.code).delete()
            entry.delete()
        return StandardResponse.success(message='Deleted.')


class LookupActiveView(APIView):
    """POST /<base>/<id>/deactivate/ or /activate/ — set by as_view(activate=...)."""

    permission_classes = [IsSuperAdmin]

    category = None
    activate = False

    @extend_schema(tags=['Admin - Master Data'], request=None, responses={200: None, 404: None})
    def post(self, request, pk):
        entry = MasterLookup.objects.filter(category=self.category, pk=pk).first()
        if not entry:
            return StandardResponse.error('Not found.', status_code=404)
        entry.is_active = self.activate
        entry.save(update_fields=['is_active', 'updated_at'])
        return StandardResponse.success(
            data=serialize_entry(entry),
            message='Activated.' if self.activate else 'Deactivated.',
        )


class CommodityCreateView(LookupCreateView):
    category          = 'commodity'
    serializer_class  = CommodityCreateSerializer
    translation_label = 'Commodity'
    translation_desc  = 'Agricultural commodities for FPO registration'

    def get_metadata(self, data):
        return {'section': data['section']}

    @extend_schema(
        tags=['Admin - Master Data'],
        summary='Add a commodity',
        description='Creates a commodity with its English and Malayalam names and a section. '
                    'Available at `GET /api/public/master-data/?category=commodity`.',
        request=CommodityCreateSerializer,
        responses={201: None, 400: None},
    )
    def post(self, request):
        return self.create_entry(request)

    @extend_schema(
        tags=['Admin - Master Data'],
        summary='List entries (including inactive)',
        responses={200: None},
    )
    def get(self, request):
        return self.list_entries(request)


class PromotingAgencyCreateView(LookupCreateView):
    category          = 'promoting_agency'
    translation_label = 'Promoting Agency'
    translation_desc  = 'FPO promoting/implementing agencies'
    trailing_code     = 'others'

    @extend_schema(
        tags=['Admin - Master Data'],
        summary='Add a promoting agency',
        description='Creates an FPO promoting agency, placed before the trailing "Others" entry. '
                    'Available at `GET /api/public/master-data/?category=promoting_agency`.',
        request=LookupCreateSerializer,
        responses={201: None, 400: None},
    )
    def post(self, request):
        return self.create_entry(request)

    @extend_schema(
        tags=['Admin - Master Data'],
        summary='List entries (including inactive)',
        responses={200: None},
    )
    def get(self, request):
        return self.list_entries(request)


class BankCreateView(LookupCreateView):
    category          = 'bank_name'
    translation_label = 'Bank Names'
    translation_desc  = 'Banks for FPO Step 4 bank details'
    trailing_code     = 'other'

    @extend_schema(
        tags=['Admin - Master Data'],
        summary='Add a bank',
        description='Creates a bank, placed before the trailing "Other" entry. '
                    'Available at `GET /api/public/master-data/?category=bank_name`.',
        request=LookupCreateSerializer,
        responses={201: None, 400: None},
    )
    def post(self, request):
        return self.create_entry(request)

    @extend_schema(
        tags=['Admin - Master Data'],
        summary='List entries (including inactive)',
        responses={200: None},
    )
    def get(self, request):
        return self.list_entries(request)


class CropNameCreateView(LookupCreateView):
    category          = 'crop_name'
    serializer_class  = CropLookupCreateSerializer
    translation_label = 'Crop Names'
    translation_desc  = 'Crop names for Package of Practices and Crop Zone Profiles'

    @extend_schema(
        tags=['Admin - Master Data'],
        summary='Add a crop name',
        description='Adds a crop name to the dropdown used by Crop Package of Practices and Crop Zone '
                    'Profiles. The code is optional (derived from the name). The name must be unique.',
        request=CropLookupCreateSerializer,
        responses={201: None, 400: None},
    )
    def post(self, request):
        return self.create_entry(request)

    @extend_schema(tags=['Admin - Master Data'], summary='List entries (including inactive)', responses={200: None})
    def get(self, request):
        return self.list_entries(request)


class CropGroupCreateView(CropNameCreateView):
    category          = 'crop_group'
    translation_label = 'Crop Groups'
    translation_desc  = 'Crop groups for Package of Practices and Crop Zone Profiles'

    @extend_schema(
        tags=['Admin - Master Data'],
        summary='Add a crop group',
        description='Adds a crop group to the dropdown used by Crop Package of Practices and Crop Zone '
                    'Profiles. The code is optional (derived from the name). The name must be unique.',
        request=CropLookupCreateSerializer,
        responses={201: None, 400: None},
    )
    def post(self, request):
        return self.create_entry(request)
