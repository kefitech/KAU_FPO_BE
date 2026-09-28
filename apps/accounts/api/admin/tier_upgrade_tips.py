"""
Tier Upgrade Tips — Admin CRUD
==============================
Base Path: /api/admin/tier-upgrade-tips/

KAU Admin manages the pool of rule-based upgrade tips shown to FPOs after
they submit a tier assessment. Each tip is tied to a TierQuestion (fine)
or TierCriterion (coarse), has a trigger, and a target tier.

Wording lives directly on the row (`tip_en`, `tip_ml`) — no Translation
table hop, since KAU wants to edit these inline in the admin UI.
"""

from rest_framework import serializers, filters, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view

from apps.core.permissions.rbac import IsSubAdminOrSuperAdmin
from apps.core.utils.pagination import StandardPagination
from apps.core.utils.responses import StandardResponse
from apps.database.models.fpo import (
    TierUpgradeTip, TierQuestion, TierCriterion, TierChoice,
)


class TierUpgradeTipSerializer(serializers.ModelSerializer):
    question_no    = serializers.IntegerField(
        source='question.question_no', read_only=True, allow_null=True,
    )
    criterion_code = serializers.CharField(
        source='criterion.code', read_only=True, allow_null=True,
    )
    question_id    = serializers.PrimaryKeyRelatedField(
        source='question', queryset=TierQuestion.objects.all(),
        required=False, allow_null=True, write_only=True,
    )
    criterion_id   = serializers.PrimaryKeyRelatedField(
        source='criterion', queryset=TierCriterion.objects.all(),
        required=False, allow_null=True, write_only=True,
    )

    class Meta:
        model  = TierUpgradeTip
        fields = [
            'id',
            'question_id', 'question_no',
            'criterion_id', 'criterion_code',
            'trigger_type', 'trigger_value',
            'tip_en', 'tip_ml',
            'target_tier', 'priority', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, attrs):
        # A tip must be anchored to either a question or a criterion (not both none).
        # On PATCH, fall back to existing values.
        instance = self.instance
        question  = attrs.get('question',  instance.question  if instance else None)
        criterion = attrs.get('criterion', instance.criterion if instance else None)
        if not question and not criterion:
            raise serializers.ValidationError(
                'Tip must be anchored to either a question_id or a criterion_id.'
            )
        target_tier = attrs.get('target_tier', instance.target_tier if instance else None)
        if target_tier and target_tier not in dict(TierChoice.choices):
            raise serializers.ValidationError({'target_tier': 'Invalid tier value.'})
        return attrs


@extend_schema_view(
    list    = extend_schema(tags=['Admin - Tier Upgrade Tips']),
    create  = extend_schema(tags=['Admin - Tier Upgrade Tips']),
    retrieve= extend_schema(tags=['Admin - Tier Upgrade Tips']),
    update  = extend_schema(tags=['Admin - Tier Upgrade Tips']),
    partial_update = extend_schema(tags=['Admin - Tier Upgrade Tips']),
    destroy = extend_schema(tags=['Admin - Tier Upgrade Tips']),
)
class TierUpgradeTipViewSet(viewsets.ModelViewSet):
    """CRUD + activate/deactivate for TierUpgradeTip rows."""
    queryset           = TierUpgradeTip.objects.select_related('question', 'criterion')
    serializer_class   = TierUpgradeTipSerializer
    permission_classes = [IsSubAdminOrSuperAdmin]
    pagination_class   = StandardPagination
    filter_backends    = [filters.SearchFilter, filters.OrderingFilter]
    search_fields      = ['tip_en', 'tip_ml', 'question__text', 'criterion__code']
    ordering_fields    = ['priority', 'target_tier', 'created_at']
    ordering           = ['target_tier', 'priority', 'id']

    def get_queryset(self):
        qs = super().get_queryset()
        target_tier = self.request.query_params.get('target_tier')
        question_no = self.request.query_params.get('question_no')
        is_active   = self.request.query_params.get('is_active')
        if target_tier:
            qs = qs.filter(target_tier=target_tier)
        if question_no:
            qs = qs.filter(question__question_no=question_no)
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() in ('1', 'true', 'yes'))
        return qs

    @extend_schema(
        tags=['Admin - Tier Upgrade Tips'],
        summary='List all tier questions (for the tip form dropdown)',
        description='Returns the 29 seeded TierQuestion rows so the admin form can bind tips to a question.',
    )
    @action(detail=False, methods=['get'], url_path='questions', pagination_class=None)
    def questions(self, request):
        rows = TierQuestion.objects.select_related('criterion__domain').order_by('question_no')
        data = [
            {
                'id':             q.id,
                'question_no':    q.question_no,
                'text':           q.text,
                'input_type':     q.input_type,
                'criterion_code': q.criterion.code,
                'domain_code':    q.criterion.domain.code,
            }
            for q in rows
        ]
        return Response({'status': 'success', 'message': 'Questions retrieved.', 'data': data})

    @extend_schema(tags=['Admin - Tier Upgrade Tips'], summary='Activate tip')
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        tip = self.get_object()
        tip.is_active = True
        tip.save(update_fields=['is_active', 'updated_at'])
        return StandardResponse.success(TierUpgradeTipSerializer(tip).data, 'Tip activated.')

    @extend_schema(tags=['Admin - Tier Upgrade Tips'], summary='Deactivate tip')
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        tip = self.get_object()
        tip.is_active = False
        tip.save(update_fields=['is_active', 'updated_at'])
        return StandardResponse.success(TierUpgradeTipSerializer(tip).data, 'Tip deactivated.')
