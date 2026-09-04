"""
DPR serializers — Phase 1 (Project shell + §2.3.10 Raw Material).

Nested-write strategy for section: **full-replace per child list**.
If the client sends `materials: [...]`, the existing list is wiped and recreated.
If a child list key is absent, that list is left untouched. This is the pilot
pattern all future sections will follow.

M2M (`quality_parameters`) is popped before the model create and set via `.set()`.
"""

from django.db import transaction
from rest_framework import serializers

from apps.database.models import (
    DPRProject,
    DPRSectionRawMaterial,
    DPRRawMaterial,
    DPRRawMaterialRisk,
    DPRPackagingMaterial,
    DPRConsumable,
    DPRSectionMarket,
    DPRMarketingProduct,
    DPRMarketingBuyer,
    DPRMarketingChannelSelection,
    DPRMarketingCompetitor,
    DPRMarketingRisk,
    DPRSectionComponents,
    DPRSectionNatureOfBusiness,
    DPRSectionInvestment,
    DPRSectionProducts,
    DPRProductItem,
    DPRSectionLocation,
    DPRSectionRationale,
    DPRRationaleSelection,
    DPRSectionBaseline,
    DPRSectionCapacity,
    DPRSectionTechnology,
    DPRTechnology,
    DPRTechnologyRisk,
    DPRSectionSite,
    DPRLandParcel,
    DPRExistingInfrastructure,
    DPRSiteConstraint,
    DPRSectionCivil,
    DPRExistingBuilding,
    DPRProposedBuilding,
    DPRSiteDevelopmentItem,
    DPRSectionMachinery,
    DPRMachineryItem,
    DPRSupportingAssetItem,
    DPRSectionUtilities,
    DPRFuelUsage,
    DPRProcessUtility,
    DPRWasteManagement,
    DPRRenewableInitiativeSelection,
    DPRSectionHR,
    DPREmployeeCategory,
    DPRDepartmentStaffing,
    DPRTrainingRequirement,
    DPRSectionFinance,
    DPRRevenueAssumption,
    DPRFinancialYearHistory,
    DPRSectionCompliance,
    DPRComplianceItem,
    DPRSectionESS,
    DPREnvironmentalImpactSelection,
    DPRClimateRiskSelection,
    DPRSectionImplementation,
    DPRImplementationActivity,
    DPRImplementationMilestone,
    DPRSectionRisk,
    DPRRiskItem,
)


# ─────────────────────────────────────────────────────────────────────────────
# DPRProject — §2.2 Project Identification
# ─────────────────────────────────────────────────────────────────────────────

class DPRProjectSerializer(serializers.ModelSerializer):
    """
    List / minimal-shape serializer — used by list & create endpoints where
    only the row-summary matters. Detail view uses DPRProjectDetailSerializer.
    """

    class Meta:
        model = DPRProject
        fields = ('uuid', 'title', 'status', 'created_at', 'updated_at')
        read_only_fields = ('uuid', 'status', 'created_at', 'updated_at')


class DPRProjectDetailSerializer(serializers.ModelSerializer):
    """
    §2.2 Project Identification — full field set.
    All 6 relational fields accept PKs on write; read exposes ids.
    """

    class Meta:
        model = DPRProject
        fields = (
            'uuid', 'status', 'created_at', 'updated_at',
            # §2.2 fields
            'title',                       # 1 — Proposed Project Title
            'project_types',               # 2 — Multi-select (ids)
            'brief_description',           # 3 — Long text
            'primary_commodity',           # 4 — FK MasterLookup id
            'secondary_commodities',       # 5 — Multi-select MasterLookup ids
            'project_objectives',          # 6 — Multi-select ids
            'project_objectives_other',
            'expected_outcomes',           # 7 — Multi-select ids
            'expected_outcomes_other',
        )
        read_only_fields = ('uuid', 'status', 'created_at', 'updated_at')


# ─────────────────────────────────────────────────────────────────────────────
# §2.3.10 Raw Material — child item serializers
# ─────────────────────────────────────────────────────────────────────────────

_CHILD_EXCLUDE = ('section', 'created_at', 'updated_at', 'created_by', 'updated_by')


class DPRRawMaterialSerializer(serializers.ModelSerializer):
    """Category A + B + D + E — one raw material row."""

    class Meta:
        model = DPRRawMaterial
        exclude = _CHILD_EXCLUDE


class DPRRawMaterialRiskSerializer(serializers.ModelSerializer):
    """Category F — supply risk with mitigation."""

    class Meta:
        model = DPRRawMaterialRisk
        exclude = _CHILD_EXCLUDE


class DPRPackagingMaterialSerializer(serializers.ModelSerializer):
    """Category G — packaging materials."""

    class Meta:
        model = DPRPackagingMaterial
        exclude = _CHILD_EXCLUDE


class DPRConsumableSerializer(serializers.ModelSerializer):
    """Category H — other consumables."""

    class Meta:
        model = DPRConsumable
        exclude = _CHILD_EXCLUDE


# ─────────────────────────────────────────────────────────────────────────────
# Section serializer with nested writable lists
# ─────────────────────────────────────────────────────────────────────────────

class DPRSectionRawMaterialSerializer(serializers.ModelSerializer):
    """
    §2.3.10 section — Category C (section-level fields) + nested lists.

    Read: returns section fields + all four child lists.
    Write: any child list present in payload is **wiped and recreated**;
           absent keys leave that list untouched.
    """

    materials = DPRRawMaterialSerializer(many=True, required=False)
    risks = DPRRawMaterialRiskSerializer(many=True, required=False)
    packaging_materials = DPRPackagingMaterialSerializer(many=True, required=False)
    consumables = DPRConsumableSerializer(many=True, required=False)

    class Meta:
        model = DPRSectionRawMaterial
        exclude = ('project', 'created_at', 'updated_at', 'created_by', 'updated_by')

    # ── nested write ─────────────────────────────────────────────────────────

    @transaction.atomic
    def update(self, instance, validated_data):
        materials_data = validated_data.pop('materials', None)
        risks_data = validated_data.pop('risks', None)
        packaging_data = validated_data.pop('packaging_materials', None)
        consumables_data = validated_data.pop('consumables', None)

        # Section-level fields
        for k, v in validated_data.items():
            setattr(instance, k, v)
        user = self.context['request'].user if 'request' in self.context else None
        if user and user.is_authenticated:
            instance.updated_by = user
        instance.save()

        if materials_data is not None:
            self._replace_materials(instance, materials_data, user)
        if risks_data is not None:
            self._replace_risks(instance, risks_data, user)
        if packaging_data is not None:
            self._replace_packaging(instance, packaging_data, user)
        if consumables_data is not None:
            self._replace_consumables(instance, consumables_data, user)

        return instance

    # ── nested-list replace helpers ──────────────────────────────────────────

    @staticmethod
    def _audit(user):
        if user and user.is_authenticated:
            return {'created_by': user, 'updated_by': user}
        return {}

    def _replace_materials(self, section, items_data, user):
        section.materials.all().delete()
        audit = self._audit(user)
        for item in items_data:
            item.pop('id', None)
            quality_params = item.pop('quality_parameters', [])
            m = DPRRawMaterial.objects.create(section=section, **item, **audit)
            if quality_params:
                m.quality_parameters.set(quality_params)

    def _replace_risks(self, section, items_data, user):
        section.risks.all().delete()
        audit = self._audit(user)
        for item in items_data:
            item.pop('id', None)
            DPRRawMaterialRisk.objects.create(section=section, **item, **audit)

    def _replace_packaging(self, section, items_data, user):
        section.packaging_materials.all().delete()
        audit = self._audit(user)
        for item in items_data:
            item.pop('id', None)
            DPRPackagingMaterial.objects.create(section=section, **item, **audit)

    def _replace_consumables(self, section, items_data, user):
        section.consumables.all().delete()
        audit = self._audit(user)
        for item in items_data:
            item.pop('id', None)
            DPRConsumable.objects.create(section=section, **item, **audit)


# ─────────────────────────────────────────────────────────────────────────────
# §2.3.11 Market Assessment — child item serializers
# ─────────────────────────────────────────────────────────────────────────────

class DPRMarketingProductSerializer(serializers.ModelSerializer):
    """Cat A + Cat H — product identity + sales projection."""

    class Meta:
        model = DPRMarketingProduct
        exclude = _CHILD_EXCLUDE


class DPRMarketingBuyerSerializer(serializers.ModelSerializer):
    """Cat C — existing buyer."""

    class Meta:
        model = DPRMarketingBuyer
        exclude = _CHILD_EXCLUDE


class DPRMarketingChannelSelectionSerializer(serializers.ModelSerializer):
    """Cat D — channel selection with expected share."""

    class Meta:
        model = DPRMarketingChannelSelection
        exclude = _CHILD_EXCLUDE


class DPRMarketingCompetitorSerializer(serializers.ModelSerializer):
    """Cat F — competitor."""

    class Meta:
        model = DPRMarketingCompetitor
        exclude = _CHILD_EXCLUDE


class DPRMarketingRiskSerializer(serializers.ModelSerializer):
    """Cat I — marketing risk with mitigation."""

    class Meta:
        model = DPRMarketingRisk
        exclude = _CHILD_EXCLUDE


class DPRSectionMarketSerializer(serializers.ModelSerializer):
    """
    §2.3.11 section — Cat B + E + G section-level + 5 nested lists.

    Same nested-write contract as Raw Material:
        - Key present in PATCH → wipe and recreate the whole list
        - Key absent → leave the list untouched
        - M2M `promotional_activities` on section handled by DRF's default
          PrimaryKeyRelatedField (works because it's not nested inside a list)
        - M2M `customer_categories` on each product row: popped, then .set() after create
    """

    products = DPRMarketingProductSerializer(many=True, required=False)
    buyers = DPRMarketingBuyerSerializer(many=True, required=False)
    channel_selections = DPRMarketingChannelSelectionSerializer(many=True, required=False)
    competitors = DPRMarketingCompetitorSerializer(many=True, required=False)
    risks = DPRMarketingRiskSerializer(many=True, required=False)

    class Meta:
        model = DPRSectionMarket
        exclude = ('project', 'created_at', 'updated_at', 'created_by', 'updated_by')

    @transaction.atomic
    def update(self, instance, validated_data):
        products_data = validated_data.pop('products', None)
        buyers_data = validated_data.pop('buyers', None)
        channels_data = validated_data.pop('channel_selections', None)
        competitors_data = validated_data.pop('competitors', None)
        risks_data = validated_data.pop('risks', None)
        # promotional_activities is a section-level M2M — let ModelSerializer handle it after save
        promo_activities = validated_data.pop('promotional_activities', None)

        for k, v in validated_data.items():
            setattr(instance, k, v)
        user = self.context['request'].user if 'request' in self.context else None
        if user and user.is_authenticated:
            instance.updated_by = user
        instance.save()

        if promo_activities is not None:
            instance.promotional_activities.set(promo_activities)

        if products_data is not None:
            self._replace_products(instance, products_data, user)
        if buyers_data is not None:
            self._replace_buyers(instance, buyers_data, user)
        if channels_data is not None:
            self._replace_channels(instance, channels_data, user)
        if competitors_data is not None:
            self._replace_competitors(instance, competitors_data, user)
        if risks_data is not None:
            self._replace_risks(instance, risks_data, user)

        return instance

    @staticmethod
    def _audit(user):
        if user and user.is_authenticated:
            return {'created_by': user, 'updated_by': user}
        return {}

    def _replace_products(self, section, items_data, user):
        section.products.all().delete()
        audit = self._audit(user)
        for item in items_data:
            item.pop('id', None)
            customer_cats = item.pop('customer_categories', [])
            p = DPRMarketingProduct.objects.create(section=section, **item, **audit)
            if customer_cats:
                p.customer_categories.set(customer_cats)

    def _replace_buyers(self, section, items_data, user):
        section.buyers.all().delete()
        audit = self._audit(user)
        for item in items_data:
            item.pop('id', None)
            DPRMarketingBuyer.objects.create(section=section, **item, **audit)

    def _replace_channels(self, section, items_data, user):
        section.channel_selections.all().delete()
        audit = self._audit(user)
        for item in items_data:
            item.pop('id', None)
            DPRMarketingChannelSelection.objects.create(section=section, **item, **audit)

    def _replace_competitors(self, section, items_data, user):
        section.competitors.all().delete()
        audit = self._audit(user)
        for item in items_data:
            item.pop('id', None)
            DPRMarketingCompetitor.objects.create(section=section, **item, **audit)

    def _replace_risks(self, section, items_data, user):
        section.risks.all().delete()
        audit = self._audit(user)
        for item in items_data:
            item.pop('id', None)
            DPRMarketingRisk.objects.create(section=section, **item, **audit)


# ─────────────────────────────────────────────────────────────────────────────
# §2.3.2 Project Components — 1-table section, simple M2M + 6 "other" fields
# ─────────────────────────────────────────────────────────────────────────────

class DPRSectionComponentsSerializer(serializers.ModelSerializer):
    """
    §2.3.2 section. No child lists — just an M2M and 6 companion "Others (Specify)" fields.

    DRF's default ModelSerializer handles the M2M `components` via PrimaryKeyRelatedField.
    We only need to stamp `updated_by`.
    """

    class Meta:
        model = DPRSectionComponents
        exclude = ('project', 'created_at', 'updated_at', 'created_by', 'updated_by')

    @transaction.atomic
    def update(self, instance, validated_data):
        components = validated_data.pop('components', None)

        for k, v in validated_data.items():
            setattr(instance, k, v)
        user = self.context['request'].user if 'request' in self.context else None
        if user and user.is_authenticated:
            instance.updated_by = user
        instance.save()

        if components is not None:
            instance.components.set(components)

        return instance


# ─────────────────────────────────────────────────────────────────────────────
# §2.3.3 Nature of Business — 1-table section, single M2M + 1 "other" field
# ─────────────────────────────────────────────────────────────────────────────

class DPRSectionNatureOfBusinessSerializer(serializers.ModelSerializer):
    """§2.3.3 section. M2M `natures` + 1 companion CharField `nature_other`."""

    class Meta:
        model = DPRSectionNatureOfBusiness
        exclude = ('project', 'created_at', 'updated_at', 'created_by', 'updated_by')

    @transaction.atomic
    def update(self, instance, validated_data):
        natures = validated_data.pop('natures', None)

        for k, v in validated_data.items():
            setattr(instance, k, v)
        user = self.context['request'].user if 'request' in self.context else None
        if user and user.is_authenticated:
            instance.updated_by = user
        instance.save()

        if natures is not None:
            instance.natures.set(natures)

        return instance


# ─────────────────────────────────────────────────────────────────────────────
# §2.3.4 Proposed Project Investment — trivial 1-table, no M2M, no children
# ─────────────────────────────────────────────────────────────────────────────

class DPRSectionInvestmentSerializer(serializers.ModelSerializer):
    """§2.3.4 section. Plain ModelSerializer — no M2M or nested lists."""

    class Meta:
        model = DPRSectionInvestment
        exclude = ('project', 'created_at', 'updated_at', 'created_by', 'updated_by')

    def update(self, instance, validated_data):
        for k, v in validated_data.items():
            setattr(instance, k, v)
        user = self.context['request'].user if 'request' in self.context else None
        if user and user.is_authenticated:
            instance.updated_by = user
        instance.save()
        return instance


# ─────────────────────────────────────────────────────────────────────────────
# §2.3.5 Proposed Products and Services — nested-list section
# ─────────────────────────────────────────────────────────────────────────────

class DPRProductItemSerializer(serializers.ModelSerializer):
    """One product/service row (10 KAU-spec columns)."""

    class Meta:
        model = DPRProductItem
        exclude = _CHILD_EXCLUDE


class DPRSectionProductsSerializer(serializers.ModelSerializer):
    """§2.3.5 section — full-replace pattern for `items` list."""

    items = DPRProductItemSerializer(many=True, required=False)

    class Meta:
        model = DPRSectionProducts
        exclude = ('project', 'created_at', 'updated_at', 'created_by', 'updated_by')

    @transaction.atomic
    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)

        for k, v in validated_data.items():
            setattr(instance, k, v)
        user = self.context['request'].user if 'request' in self.context else None
        if user and user.is_authenticated:
            instance.updated_by = user
        instance.save()

        if items_data is not None:
            self._replace_items(instance, items_data, user)
        return instance

    @staticmethod
    def _audit(user):
        if user and user.is_authenticated:
            return {'created_by': user, 'updated_by': user}
        return {}

    def _replace_items(self, section, items_data, user):
        section.items.all().delete()
        audit = self._audit(user)
        for item in items_data:
            item.pop('id', None)
            DPRProductItem.objects.create(section=section, **item, **audit)


# ─────────────────────────────────────────────────────────────────────────────
# §2.3.6 Proposed Project Location — 1-table with 2 M2Ms (no child lists)
# ─────────────────────────────────────────────────────────────────────────────

class DPRSectionLocationSerializer(serializers.ModelSerializer):
    """§2.3.6 section — DRF handles both M2Ms via PrimaryKeyRelatedField."""

    class Meta:
        model = DPRSectionLocation
        exclude = ('project', 'created_at', 'updated_at', 'created_by', 'updated_by')

    @transaction.atomic
    def update(self, instance, validated_data):
        ownership = validated_data.pop('land_ownership_types', None)
        site_statuses = validated_data.pop('site_statuses', None)

        for k, v in validated_data.items():
            setattr(instance, k, v)
        user = self.context['request'].user if 'request' in self.context else None
        if user and user.is_authenticated:
            instance.updated_by = user
        instance.save()

        if ownership is not None:
            instance.land_ownership_types.set(ownership)
        if site_statuses is not None:
            instance.site_statuses.set(site_statuses)

        return instance


# ─────────────────────────────────────────────────────────────────────────────
# §2.3.7 Project Rationale — through-table with per-selection justification
# ─────────────────────────────────────────────────────────────────────────────

class DPRRationaleSelectionSerializer(serializers.ModelSerializer):
    """One (rationale, justification) row."""

    class Meta:
        model = DPRRationaleSelection
        exclude = _CHILD_EXCLUDE


class DPRSectionRationaleSerializer(serializers.ModelSerializer):
    """§2.3.7 section — full-replace pattern for selections list."""

    selections = DPRRationaleSelectionSerializer(many=True, required=False)

    class Meta:
        model = DPRSectionRationale
        exclude = ('project', 'created_at', 'updated_at', 'created_by', 'updated_by')

    def validate_selections(self, value):
        """Reject duplicate rationale IDs before the DB unique constraint fires."""
        seen = set()
        for i, item in enumerate(value):
            r_id = item.get('rationale').pk if item.get('rationale') else None
            if r_id in seen:
                raise serializers.ValidationError(
                    f'Duplicate rationale at selections[{i}] — each rationale may be selected only once.',
                )
            seen.add(r_id)
        return value

    @transaction.atomic
    def update(self, instance, validated_data):
        selections_data = validated_data.pop('selections', None)

        for k, v in validated_data.items():
            setattr(instance, k, v)
        user = self.context['request'].user if 'request' in self.context else None
        if user and user.is_authenticated:
            instance.updated_by = user
        instance.save()

        if selections_data is not None:
            self._replace_selections(instance, selections_data, user)
        return instance

    @staticmethod
    def _audit(user):
        if user and user.is_authenticated:
            return {'created_by': user, 'updated_by': user}
        return {}

    def _replace_selections(self, section, items_data, user):
        section.selections.all().delete()
        audit = self._audit(user)
        for item in items_data:
            item.pop('id', None)
            DPRRationaleSelection.objects.create(section=section, **item, **audit)


# ─────────────────────────────────────────────────────────────────────────────
# §2.3.8 Current Status / Baseline — trivial 1-table, no M2M, no children
# ─────────────────────────────────────────────────────────────────────────────

class DPRSectionBaselineSerializer(serializers.ModelSerializer):
    """§2.3.8 conditional questionnaire. All fields nullable — validator enforces branch."""

    class Meta:
        model = DPRSectionBaseline
        exclude = ('project', 'created_at', 'updated_at', 'created_by', 'updated_by')

    def update(self, instance, validated_data):
        for k, v in validated_data.items():
            setattr(instance, k, v)
        user = self.context['request'].user if 'request' in self.context else None
        if user and user.is_authenticated:
            instance.updated_by = user
        instance.save()
        return instance


# ─────────────────────────────────────────────────────────────────────────────
# §2.3.9 Project Capacity — 1-table, ArrayField multi-selects, no children/M2M
# ─────────────────────────────────────────────────────────────────────────────

class DPRSectionCapacitySerializer(serializers.ModelSerializer):
    """§2.3.9 section. All 5 categories A-E collapsed into a single row."""

    class Meta:
        model = DPRSectionCapacity
        exclude = ('project', 'created_at', 'updated_at', 'created_by', 'updated_by')

    def update(self, instance, validated_data):
        for k, v in validated_data.items():
            setattr(instance, k, v)
        user = self.context['request'].user if 'request' in self.context else None
        if user and user.is_authenticated:
            instance.updated_by = user
        instance.save()
        return instance


# ─────────────────────────────────────────────────────────────────────────────
# §2.3.12 Technology — 2-level nested (section → technologies → risks)
# ─────────────────────────────────────────────────────────────────────────────

class DPRTechnologyRiskSerializer(serializers.ModelSerializer):
    """§2.3.12 Cat H — one risk per row."""

    class Meta:
        model = DPRTechnologyRisk
        exclude = ('technology', 'created_at', 'updated_at', 'created_by', 'updated_by')


class DPRTechnologySerializer(serializers.ModelSerializer):
    """One technology row (Cat A + B + C + D + E + F + G) with nested Cat H risks."""

    risks = DPRTechnologyRiskSerializer(many=True, required=False)

    class Meta:
        model = DPRTechnology
        exclude = ('section', 'created_at', 'updated_at', 'created_by', 'updated_by')


class DPRSectionTechnologySerializer(serializers.ModelSerializer):
    """§2.3.12 section — full-replace on `technologies` list. Each technology's `risks` and M2Ms handled inside."""

    technologies = DPRTechnologySerializer(many=True, required=False)

    class Meta:
        model = DPRSectionTechnology
        exclude = ('project', 'created_at', 'updated_at', 'created_by', 'updated_by')

    @transaction.atomic
    def update(self, instance, validated_data):
        technologies_data = validated_data.pop('technologies', None)

        for k, v in validated_data.items():
            setattr(instance, k, v)
        user = self.context['request'].user if 'request' in self.context else None
        if user and user.is_authenticated:
            instance.updated_by = user
        instance.save()

        if technologies_data is not None:
            self._replace_technologies(instance, technologies_data, user)
        return instance

    @staticmethod
    def _audit(user):
        if user and user.is_authenticated:
            return {'created_by': user, 'updated_by': user}
        return {}

    def _replace_technologies(self, section, techs_data, user):
        section.technologies.all().delete()   # cascades to risks
        audit = self._audit(user)
        for tech in techs_data:
            tech.pop('id', None)
            risks = tech.pop('risks', [])
            reasons = tech.pop('reasons', [])
            certifications = tech.pop('certifications', [])
            t = DPRTechnology.objects.create(section=section, **tech, **audit)
            if reasons:
                t.reasons.set(reasons)
            if certifications:
                t.certifications.set(certifications)
            for risk in risks:
                risk.pop('id', None)
                DPRTechnologyRisk.objects.create(technology=t, **risk, **audit)


# ─────────────────────────────────────────────────────────────────────────────
# §2.3.13 Site — 4 tables (section + parcels + infrastructure + constraints)
# ─────────────────────────────────────────────────────────────────────────────

class DPRLandParcelSerializer(serializers.ModelSerializer):
    class Meta:
        model = DPRLandParcel
        exclude = _CHILD_EXCLUDE


class DPRExistingInfrastructureSerializer(serializers.ModelSerializer):
    class Meta:
        model = DPRExistingInfrastructure
        exclude = _CHILD_EXCLUDE


class DPRSiteConstraintSerializer(serializers.ModelSerializer):
    class Meta:
        model = DPRSiteConstraint
        exclude = _CHILD_EXCLUDE


class DPRSectionSiteSerializer(serializers.ModelSerializer):
    """§2.3.13 section with 3 nested lists. Full-replace pattern per list."""

    parcels = DPRLandParcelSerializer(many=True, required=False)
    existing_infrastructure = DPRExistingInfrastructureSerializer(many=True, required=False)
    constraints = DPRSiteConstraintSerializer(many=True, required=False)

    class Meta:
        model = DPRSectionSite
        exclude = ('project', 'created_at', 'updated_at', 'created_by', 'updated_by')

    @transaction.atomic
    def update(self, instance, validated_data):
        parcels_data = validated_data.pop('parcels', None)
        infra_data = validated_data.pop('existing_infrastructure', None)
        constraints_data = validated_data.pop('constraints', None)

        for k, v in validated_data.items():
            setattr(instance, k, v)
        user = self.context['request'].user if 'request' in self.context else None
        if user and user.is_authenticated:
            instance.updated_by = user
        instance.save()

        if parcels_data is not None:
            self._replace_parcels(instance, parcels_data, user)
        if infra_data is not None:
            self._replace_infra(instance, infra_data, user)
        if constraints_data is not None:
            self._replace_constraints(instance, constraints_data, user)
        return instance

    @staticmethod
    def _audit(user):
        if user and user.is_authenticated:
            return {'created_by': user, 'updated_by': user}
        return {}

    def _replace_parcels(self, section, items_data, user):
        section.parcels.all().delete()
        audit = self._audit(user)
        for item in items_data:
            item.pop('id', None)
            DPRLandParcel.objects.create(section=section, **item, **audit)

    def _replace_infra(self, section, items_data, user):
        section.existing_infrastructure.all().delete()
        audit = self._audit(user)
        for item in items_data:
            item.pop('id', None)
            DPRExistingInfrastructure.objects.create(section=section, **item, **audit)

    def _replace_constraints(self, section, items_data, user):
        section.constraints.all().delete()
        audit = self._audit(user)
        for item in items_data:
            item.pop('id', None)
            DPRSiteConstraint.objects.create(section=section, **item, **audit)


# ─────────────────────────────────────────────────────────────────────────────
# §2.3.14 Civil — 4 tables (section + 3 child lists)
# ─────────────────────────────────────────────────────────────────────────────

class DPRExistingBuildingSerializer(serializers.ModelSerializer):
    class Meta:
        model = DPRExistingBuilding
        exclude = _CHILD_EXCLUDE


class DPRProposedBuildingSerializer(serializers.ModelSerializer):
    class Meta:
        model = DPRProposedBuilding
        exclude = _CHILD_EXCLUDE


class DPRSiteDevelopmentItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = DPRSiteDevelopmentItem
        exclude = _CHILD_EXCLUDE


class DPRSectionCivilSerializer(serializers.ModelSerializer):
    """§2.3.14 section with 3 nested lists (buildings existing + proposed + site dev items)."""

    existing_buildings = DPRExistingBuildingSerializer(many=True, required=False)
    proposed_buildings = DPRProposedBuildingSerializer(many=True, required=False)
    site_development_items = DPRSiteDevelopmentItemSerializer(many=True, required=False)

    class Meta:
        model = DPRSectionCivil
        exclude = ('project', 'created_at', 'updated_at', 'created_by', 'updated_by')

    @transaction.atomic
    def update(self, instance, validated_data):
        existing_data = validated_data.pop('existing_buildings', None)
        proposed_data = validated_data.pop('proposed_buildings', None)
        site_dev_data = validated_data.pop('site_development_items', None)

        for k, v in validated_data.items():
            setattr(instance, k, v)
        user = self.context['request'].user if 'request' in self.context else None
        if user and user.is_authenticated:
            instance.updated_by = user
        instance.save()

        if existing_data is not None:
            self._replace(instance.existing_buildings, DPRExistingBuilding, instance, existing_data, user)
        if proposed_data is not None:
            self._replace(instance.proposed_buildings, DPRProposedBuilding, instance, proposed_data, user)
        if site_dev_data is not None:
            self._replace(instance.site_development_items, DPRSiteDevelopmentItem, instance, site_dev_data, user)
        return instance

    @staticmethod
    def _audit(user):
        if user and user.is_authenticated:
            return {'created_by': user, 'updated_by': user}
        return {}

    def _replace(self, related_manager, model_cls, section, items_data, user):
        related_manager.all().delete()
        audit = self._audit(user)
        for item in items_data:
            item.pop('id', None)
            model_cls.objects.create(section=section, **item, **audit)


# ─────────────────────────────────────────────────────────────────────────────
# §2.3.16 Utilities — 5 tables (section + 4 child lists)
# ─────────────────────────────────────────────────────────────────────────────

class DPRFuelUsageSerializer(serializers.ModelSerializer):
    class Meta:
        model = DPRFuelUsage
        exclude = _CHILD_EXCLUDE


class DPRProcessUtilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = DPRProcessUtility
        exclude = _CHILD_EXCLUDE


class DPRWasteManagementSerializer(serializers.ModelSerializer):
    class Meta:
        model = DPRWasteManagement
        exclude = _CHILD_EXCLUDE


class DPRRenewableInitiativeSelectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DPRRenewableInitiativeSelection
        exclude = _CHILD_EXCLUDE


class DPRSectionUtilitiesSerializer(serializers.ModelSerializer):
    fuels = DPRFuelUsageSerializer(many=True, required=False)
    process_utilities = DPRProcessUtilitySerializer(many=True, required=False)
    wastes = DPRWasteManagementSerializer(many=True, required=False)
    renewable_initiatives = DPRRenewableInitiativeSelectionSerializer(many=True, required=False)

    class Meta:
        model = DPRSectionUtilities
        exclude = ('project', 'created_at', 'updated_at', 'created_by', 'updated_by')

    def validate_fuels(self, value):
        return _dedupe_by_fk(value, 'fuel', 'fuels')

    def validate_wastes(self, value):
        return _dedupe_by_fk(value, 'waste', 'wastes')

    def validate_process_utilities(self, value):
        return _dedupe_by_field(value, 'utility_type', 'process_utilities')

    def validate_renewable_initiatives(self, value):
        return _dedupe_by_fk(value, 'initiative', 'renewable_initiatives')

    @transaction.atomic
    def update(self, instance, validated_data):
        fuels = validated_data.pop('fuels', None)
        process_utils = validated_data.pop('process_utilities', None)
        wastes = validated_data.pop('wastes', None)
        renewables = validated_data.pop('renewable_initiatives', None)

        for k, v in validated_data.items():
            setattr(instance, k, v)
        user = self.context['request'].user if 'request' in self.context else None
        if user and user.is_authenticated:
            instance.updated_by = user
        instance.save()

        if fuels is not None:
            self._replace(instance.fuels, DPRFuelUsage, instance, fuels, user)
        if process_utils is not None:
            self._replace(instance.process_utilities, DPRProcessUtility, instance, process_utils, user)
        if wastes is not None:
            self._replace(instance.wastes, DPRWasteManagement, instance, wastes, user)
        if renewables is not None:
            self._replace(instance.renewable_initiatives, DPRRenewableInitiativeSelection, instance, renewables, user)
        return instance

    @staticmethod
    def _audit(user):
        if user and user.is_authenticated:
            return {'created_by': user, 'updated_by': user}
        return {}

    def _replace(self, related_manager, model_cls, section, items_data, user):
        related_manager.all().delete()
        audit = self._audit(user)
        for item in items_data:
            item.pop('id', None)
            model_cls.objects.create(section=section, **item, **audit)


# ─────────────────────────────────────────────────────────────────────────────
# §2.3.18 Finance — 3 tables (section + 2 child lists)
# ─────────────────────────────────────────────────────────────────────────────

class DPRRevenueAssumptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DPRRevenueAssumption
        exclude = _CHILD_EXCLUDE


class DPRFinancialYearHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = DPRFinancialYearHistory
        exclude = _CHILD_EXCLUDE


class DPRSectionFinanceSerializer(serializers.ModelSerializer):
    revenue_assumptions = DPRRevenueAssumptionSerializer(many=True, required=False)
    year_history = DPRFinancialYearHistorySerializer(many=True, required=False)

    class Meta:
        model = DPRSectionFinance
        exclude = ('project', 'created_at', 'updated_at', 'created_by', 'updated_by')

    def validate_year_history(self, value):
        return _dedupe_by_field(value, 'financial_year', 'year_history')

    @transaction.atomic
    def update(self, instance, validated_data):
        rev = validated_data.pop('revenue_assumptions', None)
        yh = validated_data.pop('year_history', None)

        for k, v in validated_data.items():
            setattr(instance, k, v)
        user = self.context['request'].user if 'request' in self.context else None
        if user and user.is_authenticated:
            instance.updated_by = user
        instance.save()

        if rev is not None:
            self._replace(instance.revenue_assumptions, DPRRevenueAssumption, instance, rev, user)
        if yh is not None:
            self._replace(instance.year_history, DPRFinancialYearHistory, instance, yh, user)
        return instance

    @staticmethod
    def _audit(user):
        if user and user.is_authenticated:
            return {'created_by': user, 'updated_by': user}
        return {}

    def _replace(self, related_manager, model_cls, section, items_data, user):
        related_manager.all().delete()
        audit = self._audit(user)
        for item in items_data:
            item.pop('id', None)
            model_cls.objects.create(section=section, **item, **audit)


# ─────────────────────────────────────────────────────────────────────────────
# §2.3.19 Compliance — 2 tables (section + 1 unified through-table)
# ─────────────────────────────────────────────────────────────────────────────

class DPRComplianceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = DPRComplianceItem
        exclude = _CHILD_EXCLUDE


class DPRSectionComplianceSerializer(serializers.ModelSerializer):
    items = DPRComplianceItemSerializer(many=True, required=False)

    class Meta:
        model = DPRSectionCompliance
        exclude = ('project', 'created_at', 'updated_at', 'created_by', 'updated_by')

    @transaction.atomic
    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)

        for k, v in validated_data.items():
            setattr(instance, k, v)
        user = self.context['request'].user if 'request' in self.context else None
        if user and user.is_authenticated:
            instance.updated_by = user
        instance.save()

        if items_data is not None:
            self._replace(instance.items, DPRComplianceItem, instance, items_data, user)
        return instance

    @staticmethod
    def _audit(user):
        if user and user.is_authenticated:
            return {'created_by': user, 'updated_by': user}
        return {}

    def _replace(self, related_manager, model_cls, section, items_data, user):
        related_manager.all().delete()
        audit = self._audit(user)
        for item in items_data:
            item.pop('id', None)
            model_cls.objects.create(section=section, **item, **audit)


# ─────────────────────────────────────────────────────────────────────────────
# §2.3.20 ESS — 3 tables (section + 2 child lists)
# ─────────────────────────────────────────────────────────────────────────────

class DPREnvironmentalImpactSelectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DPREnvironmentalImpactSelection
        exclude = _CHILD_EXCLUDE


class DPRClimateRiskSelectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DPRClimateRiskSelection
        exclude = _CHILD_EXCLUDE


class DPRSectionESSSerializer(serializers.ModelSerializer):
    environmental_impacts = DPREnvironmentalImpactSelectionSerializer(many=True, required=False)
    climate_risks = DPRClimateRiskSelectionSerializer(many=True, required=False)

    class Meta:
        model = DPRSectionESS
        exclude = ('project', 'created_at', 'updated_at', 'created_by', 'updated_by')

    def validate_environmental_impacts(self, value):
        return _dedupe_by_fk(value, 'impact', 'environmental_impacts')

    def validate_climate_risks(self, value):
        return _dedupe_by_fk(value, 'risk', 'climate_risks')

    @transaction.atomic
    def update(self, instance, validated_data):
        impacts = validated_data.pop('environmental_impacts', None)
        risks = validated_data.pop('climate_risks', None)

        for k, v in validated_data.items():
            setattr(instance, k, v)
        user = self.context['request'].user if 'request' in self.context else None
        if user and user.is_authenticated:
            instance.updated_by = user
        instance.save()

        if impacts is not None:
            self._replace(instance.environmental_impacts, DPREnvironmentalImpactSelection, instance, impacts, user)
        if risks is not None:
            self._replace(instance.climate_risks, DPRClimateRiskSelection, instance, risks, user)
        return instance

    @staticmethod
    def _audit(user):
        if user and user.is_authenticated:
            return {'created_by': user, 'updated_by': user}
        return {}

    def _replace(self, related_manager, model_cls, section, items_data, user):
        related_manager.all().delete()
        audit = self._audit(user)
        for item in items_data:
            item.pop('id', None)
            model_cls.objects.create(section=section, **item, **audit)


# ─────────────────────────────────────────────────────────────────────────────
# §2.3.21 Implementation — 3 tables (section + 2 child lists)
# ─────────────────────────────────────────────────────────────────────────────

class DPRImplementationActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = DPRImplementationActivity
        exclude = _CHILD_EXCLUDE


class DPRImplementationMilestoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = DPRImplementationMilestone
        exclude = _CHILD_EXCLUDE


class DPRSectionImplementationSerializer(serializers.ModelSerializer):
    activities = DPRImplementationActivitySerializer(many=True, required=False)
    milestones = DPRImplementationMilestoneSerializer(many=True, required=False)

    class Meta:
        model = DPRSectionImplementation
        exclude = ('project', 'created_at', 'updated_at', 'created_by', 'updated_by')

    @transaction.atomic
    def update(self, instance, validated_data):
        acts = validated_data.pop('activities', None)
        mils = validated_data.pop('milestones', None)

        for k, v in validated_data.items():
            setattr(instance, k, v)
        user = self.context['request'].user if 'request' in self.context else None
        if user and user.is_authenticated:
            instance.updated_by = user
        instance.save()

        if acts is not None:
            self._replace(instance.activities, DPRImplementationActivity, instance, acts, user)
        if mils is not None:
            self._replace(instance.milestones, DPRImplementationMilestone, instance, mils, user)
        return instance

    @staticmethod
    def _audit(user):
        if user and user.is_authenticated:
            return {'created_by': user, 'updated_by': user}
        return {}

    def _replace(self, related_manager, model_cls, section, items_data, user):
        related_manager.all().delete()
        audit = self._audit(user)
        for item in items_data:
            item.pop('id', None)
            model_cls.objects.create(section=section, **item, **audit)


# ─────────────────────────────────────────────────────────────────────────────
# §2.3.22 Risk — 2 tables (section + 1 unified risk-item list)
# ─────────────────────────────────────────────────────────────────────────────

class DPRRiskItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = DPRRiskItem
        exclude = _CHILD_EXCLUDE


class DPRSectionRiskSerializer(serializers.ModelSerializer):
    items = DPRRiskItemSerializer(many=True, required=False)

    class Meta:
        model = DPRSectionRisk
        exclude = ('project', 'created_at', 'updated_at', 'created_by', 'updated_by')

    def validate_items(self, value):
        """Reject duplicate (risk_category, risk_code) pairs — DB unique constraint."""
        seen = set()
        for i, item in enumerate(value):
            key = (item.get('risk_category'), item.get('risk_code'))
            if key in seen:
                raise serializers.ValidationError(
                    f'Duplicate risk at items[{i}] — (category={key[0]}, code={key[1]}) already present.',
                )
            seen.add(key)
        return value

    @transaction.atomic
    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)

        for k, v in validated_data.items():
            setattr(instance, k, v)
        user = self.context['request'].user if 'request' in self.context else None
        if user and user.is_authenticated:
            instance.updated_by = user
        instance.save()

        if items_data is not None:
            self._replace(instance.items, DPRRiskItem, instance, items_data, user)
        return instance

    @staticmethod
    def _audit(user):
        if user and user.is_authenticated:
            return {'created_by': user, 'updated_by': user}
        return {}

    def _replace(self, related_manager, model_cls, section, items_data, user):
        related_manager.all().delete()
        audit = self._audit(user)
        for item in items_data:
            item.pop('id', None)
            model_cls.objects.create(section=section, **item, **audit)


def _dedupe_by_fk(value, fk_name, list_name):
    """Reject duplicate FK values in a nested list before DB unique constraint fires."""
    seen = set()
    for i, item in enumerate(value):
        pk = item.get(fk_name).pk if item.get(fk_name) else None
        if pk in seen:
            raise serializers.ValidationError(
                f'Duplicate {fk_name} at {list_name}[{i}] — each {fk_name} may be selected only once.',
            )
        seen.add(pk)
    return value


def _dedupe_by_field(value, field_name, list_name):
    """Reject duplicate non-FK values (e.g. choice fields) in a nested list."""
    seen = set()
    for i, item in enumerate(value):
        v = item.get(field_name)
        if v in seen:
            raise serializers.ValidationError(
                f'Duplicate {field_name} at {list_name}[{i}] — each {field_name} may appear only once.',
            )
        seen.add(v)
    return value


# ─────────────────────────────────────────────────────────────────────────────
# §2.3.17 HR — 4 tables (section + 3 child lists)
# ─────────────────────────────────────────────────────────────────────────────

class DPREmployeeCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = DPREmployeeCategory
        exclude = _CHILD_EXCLUDE


class DPRDepartmentStaffingSerializer(serializers.ModelSerializer):
    class Meta:
        model = DPRDepartmentStaffing
        exclude = _CHILD_EXCLUDE


class DPRTrainingRequirementSerializer(serializers.ModelSerializer):
    class Meta:
        model = DPRTrainingRequirement
        exclude = _CHILD_EXCLUDE


class DPRSectionHRSerializer(serializers.ModelSerializer):
    employee_categories = DPREmployeeCategorySerializer(many=True, required=False)
    departments = DPRDepartmentStaffingSerializer(many=True, required=False)
    training_requirements = DPRTrainingRequirementSerializer(many=True, required=False)

    class Meta:
        model = DPRSectionHR
        exclude = ('project', 'created_at', 'updated_at', 'created_by', 'updated_by')

    def validate_departments(self, value):
        return _dedupe_by_field(value, 'department', 'departments')

    def validate_training_requirements(self, value):
        return _dedupe_by_fk(value, 'training_area', 'training_requirements')

    @transaction.atomic
    def update(self, instance, validated_data):
        emp = validated_data.pop('employee_categories', None)
        dept = validated_data.pop('departments', None)
        trn = validated_data.pop('training_requirements', None)

        for k, v in validated_data.items():
            setattr(instance, k, v)
        user = self.context['request'].user if 'request' in self.context else None
        if user and user.is_authenticated:
            instance.updated_by = user
        instance.save()

        if emp is not None:
            self._replace(instance.employee_categories, DPREmployeeCategory, instance, emp, user)
        if dept is not None:
            self._replace(instance.departments, DPRDepartmentStaffing, instance, dept, user)
        if trn is not None:
            self._replace(instance.training_requirements, DPRTrainingRequirement, instance, trn, user)
        return instance

    @staticmethod
    def _audit(user):
        if user and user.is_authenticated:
            return {'created_by': user, 'updated_by': user}
        return {}

    def _replace(self, related_manager, model_cls, section, items_data, user):
        related_manager.all().delete()
        audit = self._audit(user)
        for item in items_data:
            item.pop('id', None)
            model_cls.objects.create(section=section, **item, **audit)


# ─────────────────────────────────────────────────────────────────────────────
# §2.3.15 Machinery — 3 tables (section + 2 child lists)
# ─────────────────────────────────────────────────────────────────────────────

class DPRMachineryItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = DPRMachineryItem
        exclude = _CHILD_EXCLUDE


class DPRSupportingAssetItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = DPRSupportingAssetItem
        exclude = _CHILD_EXCLUDE


class DPRSectionMachinerySerializer(serializers.ModelSerializer):
    items = DPRMachineryItemSerializer(many=True, required=False)
    supporting_assets = DPRSupportingAssetItemSerializer(many=True, required=False)

    class Meta:
        model = DPRSectionMachinery
        exclude = ('project', 'created_at', 'updated_at', 'created_by', 'updated_by')

    @transaction.atomic
    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        support_data = validated_data.pop('supporting_assets', None)

        for k, v in validated_data.items():
            setattr(instance, k, v)
        user = self.context['request'].user if 'request' in self.context else None
        if user and user.is_authenticated:
            instance.updated_by = user
        instance.save()

        if items_data is not None:
            self._replace(instance.items, DPRMachineryItem, instance, items_data, user)
        if support_data is not None:
            self._replace(instance.supporting_assets, DPRSupportingAssetItem, instance, support_data, user)
        return instance

    @staticmethod
    def _audit(user):
        if user and user.is_authenticated:
            return {'created_by': user, 'updated_by': user}
        return {}

    def _replace(self, related_manager, model_cls, section, items_data, user):
        related_manager.all().delete()
        audit = self._audit(user)
        for item in items_data:
            item.pop('id', None)
            model_cls.objects.create(section=section, **item, **audit)
