"""
Admin CRUD for DPRFieldRule (Level 2 applicability rules).

Kefitech / KAU 2026-09-19: Level 1 already has an admin UI at
/admin/dpr-applicability, but Level 2 field rules could only be edited
via a Python seed script. This module exposes the missing API surface so
KAU admin can add/edit/delete field rules without a code deploy.

Endpoints:
    GET    /api/admin/dpr/field-rules/                — list (filterable)
    POST   /api/admin/dpr/field-rules/                — create
    GET    /api/admin/dpr/field-rules/<id>/           — retrieve
    PATCH  /api/admin/dpr/field-rules/<id>/           — update
    DELETE /api/admin/dpr/field-rules/<id>/           — delete
    GET    /api/admin/dpr/field-rules/schema/         — sections + components
                                                        for FE dropdowns

Author: Athul Gopan (Kefi Tech Solutions)
"""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions.rbac import IsSubAdminOrSuperAdmin
from apps.core.utils.responses import StandardResponse
from apps.database.models import DPRComponent, DPRFieldRule


# ─────────────────────────────────────────────────────────────────────────────
# Serializers
# ─────────────────────────────────────────────────────────────────────────────

class FieldRuleSerializer(serializers.ModelSerializer):
    """Full read/write shape.

    `required_components` is exposed as a list of component IDs (write)
    plus a nested `required_components_detail` (read-only) so the FE can
    show the human-readable component labels without a second lookup.
    """
    required_components = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=DPRComponent.objects.all(),
        required=False,
    )
    required_components_detail = serializers.SerializerMethodField()

    class Meta:
        model = DPRFieldRule
        fields = [
            'id',
            'data_element_key',
            'field_name',
            'recipe_type',
            'visibility',
            'required_components',
            'required_components_detail',
            'trigger_field',
            'trigger_value',
            'notes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'required_components_detail']

    def get_required_components_detail(self, obj) -> list[dict]:
        return [
            {'id': c.id, 'code': c.code, 'label': c.label_en}
            for c in obj.required_components.all()
        ]

    def validate(self, attrs):
        """Recipe-specific consistency — enforce that the caller filled the
        right fields for the chosen recipe_type.

        `component_in`  → required_components must be non-empty; trigger_*
                          must be blank.
        `field_equals`  → trigger_field + trigger_value must be non-empty;
                          required_components must be empty.
        """
        recipe = attrs.get('recipe_type') or (self.instance and self.instance.recipe_type)
        req_comps = attrs.get('required_components')
        trig_field = attrs.get('trigger_field', '')
        trig_value = attrs.get('trigger_value', '')

        # For PATCHes, fall back to instance values on unspecified fields.
        if self.instance:
            if req_comps is None:
                req_comps = list(self.instance.required_components.all())
            if 'trigger_field' not in attrs:
                trig_field = self.instance.trigger_field
            if 'trigger_value' not in attrs:
                trig_value = self.instance.trigger_value

        if recipe == DPRFieldRule.RecipeType.COMPONENT_IN:
            if not req_comps:
                raise serializers.ValidationError({
                    'required_components': (
                        'At least one component must be selected when '
                        "recipe_type is 'component_in'."
                    )
                })
            if trig_field or trig_value:
                raise serializers.ValidationError({
                    'trigger_field': (
                        "trigger_field / trigger_value must be blank when "
                        "recipe_type is 'component_in'."
                    )
                })
        elif recipe == DPRFieldRule.RecipeType.FIELD_EQUALS:
            if not trig_field or not trig_value:
                raise serializers.ValidationError({
                    'trigger_field': (
                        "trigger_field and trigger_value are both required "
                        "when recipe_type is 'field_equals'."
                    )
                })
            if req_comps:
                raise serializers.ValidationError({
                    'required_components': (
                        "required_components must be empty when "
                        "recipe_type is 'field_equals'."
                    )
                })
        return attrs


# ─────────────────────────────────────────────────────────────────────────────
# Views
# ─────────────────────────────────────────────────────────────────────────────

@extend_schema(tags=['Admin - DPR Field Rules'])
class FieldRuleListCreateView(APIView):
    """GET list (filterable by section / field / recipe_type) + POST create."""
    permission_classes = [IsAuthenticated, IsSubAdminOrSuperAdmin]

    def get(self, request):
        qs = DPRFieldRule.objects.all().prefetch_related('required_components')
        section = request.query_params.get('section')
        field = request.query_params.get('field')
        recipe = request.query_params.get('recipe_type')
        if section:
            qs = qs.filter(data_element_key=section)
        if field:
            qs = qs.filter(field_name=field)
        if recipe:
            qs = qs.filter(recipe_type=recipe)
        return StandardResponse.success(
            data=FieldRuleSerializer(qs, many=True).data,
            message='Field rules retrieved',
        )

    def post(self, request):
        s = FieldRuleSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        s.save()
        return StandardResponse.success(
            data=s.data,
            message='Field rule created',
            status_code=201,
        )


@extend_schema(tags=['Admin - DPR Field Rules'])
class FieldRuleDetailView(APIView):
    """GET retrieve + PATCH update + DELETE for a single field rule."""
    permission_classes = [IsAuthenticated, IsSubAdminOrSuperAdmin]

    def get(self, request, pk):
        rule = get_object_or_404(DPRFieldRule, pk=pk)
        return StandardResponse.success(
            data=FieldRuleSerializer(rule).data,
            message='Field rule retrieved',
        )

    def patch(self, request, pk):
        rule = get_object_or_404(DPRFieldRule, pk=pk)
        s = FieldRuleSerializer(rule, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return StandardResponse.success(
            data=s.data,
            message='Field rule updated',
        )

    def delete(self, request, pk):
        rule = get_object_or_404(DPRFieldRule, pk=pk)
        rule.delete()
        return Response(status=204)


@extend_schema(tags=['Admin - DPR Field Rules'])
class FieldRuleSchemaView(APIView):
    """Return the section keys + components + recipe / visibility choices so
    the FE can populate the create/edit dropdowns without hard-coding them.

    Deliberately does NOT enumerate every FIELD NAME across every section —
    that list is huge, per-section, and better handled by a text input on
    the FE (the admin knows which field they're targeting).
    """
    permission_classes = [IsAuthenticated, IsSubAdminOrSuperAdmin]

    # Skip these bookkeeping fields when introspecting a section model for
    # auto-complete — they're on TimeStampedModel / AuditModel and never
    # meaningful targets for a Level 2 rule.
    _SKIP_FIELDS = {
        'id', 'created_at', 'updated_at', 'created_by', 'updated_by',
        'project', 'is_complete', 'field_sources',
    }

    # Map section key → the Django model that stores that section's data.
    # Extend when a new section is added — a missing key just means "no
    # auto-complete for this section", the FE gracefully falls back to
    # free-text.
    _SECTION_MODEL_MAP = {
        'identification':      'DPRProject',
        'components':          'DPRSectionComponents',
        'nature_of_business':  'DPRSectionNatureOfBusiness',
        'investment':          'DPRSectionInvestment',
        'products':            'DPRSectionProducts',
        'location':            'DPRSectionLocation',
        'rationale':           'DPRSectionRationale',
        'baseline':            'DPRSectionBaseline',
        'capacity':            'DPRSectionCapacity',
        'raw_material':        'DPRSectionRawMaterial',
        'market':              'DPRSectionMarket',
        'technology':          'DPRSectionTechnology',
        'site':                'DPRSectionSite',
        'civil':               'DPRSectionCivil',
        'machinery':           'DPRSectionMachinery',
        'utilities':           'DPRSectionUtilities',
        'hr':                  'DPRSectionHR',
        'finance':             'DPRSectionFinance',
        'compliance':          'DPRSectionCompliance',
        'ess':                 'DPRSectionESS',
        'implementation':      'DPRSectionImplementation',
        'risk':                'DPRSectionRisk',
    }

    def _section_field_names(self) -> dict[str, list[str]]:
        """Introspect each section model to return its scalar field names.
        Skips ForeignKey / M2M / bookkeeping fields — Level 2 rules only
        target scalars + choice fields.

        Returns {section_key: [field_name, …], …}. Missing keys mean the
        FE should fall back to free-text (still valid — the rule engine
        doesn't care whether the field name comes from autocomplete).
        """
        from django.apps import apps
        from django.db import models as dj_models

        out: dict[str, list[str]] = {}
        for section_key, model_name in self._SECTION_MODEL_MAP.items():
            try:
                Model = apps.get_model('database', model_name)
            except LookupError:
                continue
            names: list[str] = []
            for f in Model._meta.get_fields():
                # Skip reverse relations, m2m accessors, and non-concrete fields.
                if f.auto_created and not f.concrete:
                    continue
                if not getattr(f, 'concrete', False):
                    continue
                name = getattr(f, 'name', None)
                if not name or name in self._SKIP_FIELDS:
                    continue
                # M2M + FK are unusual targets for Level 2 rules; expose them
                # too so the admin can pick them if needed, but keep the
                # scalar-first ordering by rendering them at the tail.
                if isinstance(f, dj_models.ForeignKey) or isinstance(f, dj_models.ManyToManyField):
                    continue
                names.append(name)
            out[section_key] = sorted(names)
        return out

    def get(self, request):
        from apps.database.models.dpr.ai_content import CHAPTER_UPSTREAM_SECTIONS

        # Section keys — union of every section the AI narrative can pull
        # upstream from + the identification section. Matches the wizard
        # sidebar order defined in the FE.
        section_keys: set[str] = {'identification'}
        for sections in CHAPTER_UPSTREAM_SECTIONS.values():
            section_keys.update(sections)

        components = DPRComponent.objects.all().order_by('group', 'code').values(
            'id', 'code', 'label_en', 'group',
        )

        return StandardResponse.success(
            data={
                'section_keys': sorted(section_keys),
                # KAU 2026-09-19 — real field names per section, so the FE can
                # offer autocomplete instead of a bare text input. Prevents
                # typos that would silently make a rule never fire.
                'section_fields': self._section_field_names(),
                'components': list(components),
                'recipe_types': [
                    {'value': k, 'label': v} for k, v in DPRFieldRule.RecipeType.choices
                ],
                'visibility_directions': [
                    {'value': k, 'label': v} for k, v in DPRFieldRule.Visibility.choices
                ],
            },
            message='Field rule schema retrieved',
        )
