"""
FPO Marketing Strategy API — P2-14
=====================================
GET   /api/fpo/me/marketing-strategies/              — list generated strategies
POST  /api/fpo/me/marketing-strategies/generate/      — generate new strategy (async)
GET   /api/fpo/me/marketing-strategies/<id>/          — strategy detail
GET   /api/fpo/me/marketing-strategies/<id>/download/ — download as PDF

Business rules (README §Business Rules):
  1. FPO must be APPROVED to generate a strategy           -> T05, 403
  2. One strategy per commodity per FY, regenerate archives -> T06
  3. Claude API not configured                              -> T10, 503
  4. Generation is async — returns task_id immediately       -> T01, 202
  5. PDF stored in S3, pre-signed URL (24h)                  -> T09 (see TODO below)
  6. Content in FPO's preferred language (EN/ML)             -> not yet wired

Note: credentials for AI generation are read from AIServiceConfig
(service='marketing'), not ExternalAPISettings — confirmed by inspection:
ExternalAPISettings.SERVICE_CHOICES only covers pan/gstin/cin/weather
verification, it has no Claude entry despite what this app's README and
the ChatConversation model's docstring both claim.
"""

from datetime import date

from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.views import APIView

from apps.core.permissions.rbac import IsFPOManager
from apps.core.utils.constants import FPOStatus
from apps.core.utils.responses import StandardResponse
from apps.database.models import MarketingStrategy
from apps.fpo.tasks import generate_marketing_strategy_task


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _current_financial_year():
    today = date.today()
    if today.month >= 4:
        return f'{today.year}-{str(today.year + 1)[2:]}'
    return f'{today.year - 1}-{str(today.year)[2:]}'


def _get_fpo(user):
    """
    request.user.fpo (FPO.primary_user's OneToOneField reverse accessor)
    only resolves for the primary user — it raises RelatedObjectDoesNotExist
    for a secondary user, who reaches their FPO via user.fpo_membership.fpo
    instead. IsFPOManager permits both roles, so both paths are checked here.
    """
    fpo = getattr(user, 'fpo', None)
    if fpo is not None:
        return fpo
    membership = getattr(user, 'fpo_membership', None)
    return membership.fpo if membership else None


def _ai_marketing_configured():
    """
    business rule 3 / T10: Claude API not configured -> 503.
    AIServiceConfig(service='marketing') already exists as a model
    (apps/database/models/ai_config.py) with is_enabled + budget-cap
    auto-disable + an encrypted api key — this is the first real check
    against it. The actual Claude call itself is a separate step (see
    apps/fpo/tasks.py TODO), this only gates whether generation may start.
    """
    from apps.database.models import AIServiceConfig
    config = AIServiceConfig.objects.filter(service='marketing').first()
    if config is None or not config.is_enabled:
        return False
    return bool(config.get_api_key())


# ─────────────────────────────────────────────────────────────────────────────
# Serializers
# ─────────────────────────────────────────────────────────────────────────────

class MarketingStrategyGenerateSerializer(serializers.Serializer):
    commodity_id = serializers.IntegerField()
    target_segment = serializers.ChoiceField(choices=MarketingStrategy.TargetSegment.choices)
    financial_year = serializers.CharField(max_length=10, required=False)

    def validate_commodity_id(self, value):
        from apps.core.models.generic import MasterLookup
        if not MasterLookup.objects.filter(id=value, category='commodity').exists():
            raise serializers.ValidationError('Unknown commodity_id.')
        return value


class MarketingStrategySerializer(serializers.ModelSerializer):
    commodity_name = serializers.CharField(source='commodity.name_en', read_only=True)

    class Meta:
        model = MarketingStrategy
        fields = [
            'id', 'fpo', 'commodity', 'commodity_name', 'target_segment', 'region',
            'financial_year', 'status', 'failure_reason', 'content',
            'file_url', 'claude_model', 'generated_at',
        ]
        read_only_fields = fields


# ─────────────────────────────────────────────────────────────────────────────
# Views
# ─────────────────────────────────────────────────────────────────────────────

class MarketingStrategyListView(APIView):
    permission_classes = [IsFPOManager]

    @extend_schema(tags=['FPO - Marketing'], summary='List marketing strategies')
    def get(self, request):
        fpo = _get_fpo(request.user)
        if not fpo:
            return StandardResponse.error(
                'No FPO associated with this user.', status_code=status.HTTP_403_FORBIDDEN,
            )
        qs = MarketingStrategy.objects.filter(fpo=fpo, is_archived=False, is_deleted=False)
        return StandardResponse.success(
            data=MarketingStrategySerializer(qs, many=True).data,
            message='Marketing strategies retrieved.',
        )


class MarketingStrategyGenerateView(APIView):
    permission_classes = [IsFPOManager]

    @extend_schema(
        tags=['FPO - Marketing'],
        summary='Generate a new marketing strategy',
        description='Async — returns 202 + task_id. Poll GET .../<id>/ for status.',
        responses={202: None},
    )
    def post(self, request):
        fpo = _get_fpo(request.user)
        if not fpo:
            return StandardResponse.error(
                'No FPO associated with this user.', status_code=status.HTTP_403_FORBIDDEN,
            )
        # Business rule 1 / T05
        if fpo.status != FPOStatus.APPROVED:
            return StandardResponse.error(
                'FPO must be approved to generate a marketing strategy.',
                status_code=status.HTTP_403_FORBIDDEN,
            )
        # Business rule 3 / T10
        if not _ai_marketing_configured():
            return StandardResponse.error(
                'AI marketing generation is not configured. Contact your administrator.',
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        serializer = MarketingStrategyGenerateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        financial_year = data.get('financial_year') or _current_financial_year()

        # Business rule 2 / T06 — archive the existing active strategy for
        # this fpo+commodity+FY before inserting the new one; the model's
        # UniqueConstraint would otherwise reject the insert.
        MarketingStrategy.objects.filter(
            fpo=fpo, commodity_id=data['commodity_id'],
            financial_year=financial_year, is_archived=False,
        ).update(is_archived=True)

        strategy = MarketingStrategy.objects.create(
            fpo=fpo,
            commodity_id=data['commodity_id'],
            target_segment=data['target_segment'],
            region=fpo.district,
            financial_year=financial_year,
            status=MarketingStrategy.Status.PENDING,
            created_by=request.user,
        )

        # Business rule 4 / T01
        task = generate_marketing_strategy_task.delay(strategy_id=strategy.id)

        return StandardResponse.success(
            data={'strategy_id': strategy.id, 'task_id': task.id, 'status': strategy.status},
            message='Marketing strategy generation started.',
            status_code=status.HTTP_202_ACCEPTED,
        )


class MarketingStrategyDetailView(APIView):
    permission_classes = [IsFPOManager]

    @extend_schema(tags=['FPO - Marketing'], summary='Get marketing strategy detail')
    def get(self, request, strategy_id):
        fpo = _get_fpo(request.user)
        if not fpo:
            return StandardResponse.error(
                'No FPO associated with this user.', status_code=status.HTTP_403_FORBIDDEN,
            )
        strategy = MarketingStrategy.objects.filter(
            pk=strategy_id, fpo=fpo, is_deleted=False,
        ).first()
        if not strategy:
            return StandardResponse.error('Strategy not found.', status_code=status.HTTP_404_NOT_FOUND)
        return StandardResponse.success(data=MarketingStrategySerializer(strategy).data)


class MarketingStrategyDownloadView(APIView):
    permission_classes = [IsFPOManager]

    @extend_schema(tags=['FPO - Marketing'], summary='Download marketing strategy PDF')
    def get(self, request, strategy_id):
        fpo = _get_fpo(request.user)
        if not fpo:
            return StandardResponse.error(
                'No FPO associated with this user.', status_code=status.HTTP_403_FORBIDDEN,
            )
        strategy = MarketingStrategy.objects.filter(
            pk=strategy_id, fpo=fpo, is_deleted=False,
        ).first()
        if not strategy:
            return StandardResponse.error('Strategy not found.', status_code=status.HTTP_404_NOT_FOUND)
        if strategy.status != MarketingStrategy.Status.READY:
            return StandardResponse.error(
                f'Strategy is not ready yet (status: {strategy.status}).',
                status_code=status.HTTP_409_CONFLICT,
            )

        # TODO — business rule 5 / T09 (24h pre-signed URL, re-signed per
        # request): no S3 presigned-URL helper exists anywhere in this
        # codebase yet, checked via grep. strategy.file_url is a
        # placeholder until PDF generation (apps/fpo/tasks.py TODO) and
        # that helper are both written.
        return StandardResponse.success(data={'download_url': strategy.file_url})