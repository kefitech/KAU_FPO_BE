"""
AI Services — Admin CRUD for per-feature provider config + budget cap.

Per KAU RCD reply B.5 + operational readiness (2026-09-03):
    Every AI feature (DPR narratives, chatbot, marketing, translate) has one
    AIServiceConfig row driving its behaviour. Admin can:
      - enable / disable the feature
      - pick the LLM provider (Anthropic / OpenAI / Google / mock)
      - pick the model within that provider
      - set the API key (encrypted at rest)
      - set the monthly budget cap + alert threshold
      - view monthly usage totals

Switching provider is a config change here — no code deploy. The gateway
`apps/fpo/services/dpr/llm_gateway.py` dispatches to the right SDK by
reading `AIServiceConfig.provider` on every call.

Access: super_admin only (writes); sub_admin can read.
Audit: every mutation writes AuditLog(DPR_CONFIG_CHANGE) — the same action
       used for DPR config since these are conceptually the same class of
       central-admin controls.

Endpoints (mounted at /api/admin/ai-services/):
    GET    /                       — list all 4 service rows
    GET    /<pk>/                  — retrieve one
    PATCH  /<pk>/                  — update provider / model / key / cap / enabled
    POST   /<pk>/reset-usage/      — reset current-month totals (admin recovery)
    GET    /providers/             — list available providers + default models
                                      (pulled from llm_gateway) — used by FE
                                      dropdowns

Author: Athul Gopan (Kefi Tech Solutions)
"""
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.models.generic import AuditLog
from apps.core.permissions.rbac import IsSuperAdminOrReadOnly
from apps.core.utils.responses import StandardResponse
from apps.database.models import AIServiceConfig
from apps.fpo.services.dpr.llm_gateway import DEFAULT_MODELS, PRICING_USD_PER_MTOKEN


# ─────────────────────────────────────────────────────────────────────────────
# Serializers
# ─────────────────────────────────────────────────────────────────────────────

class AIServiceConfigSerializer(serializers.ModelSerializer):
    """Full read shape. API key is masked; writes accept plain text and encrypt."""

    service_display = serializers.CharField(source='get_service_display', read_only=True)
    provider_display = serializers.CharField(source='get_provider_display', read_only=True)
    api_key_masked = serializers.SerializerMethodField()
    budget_usage_pct = serializers.SerializerMethodField()
    # Write-only field: admin submits the raw key here; we encrypt via set_api_key.
    # Never returned in reads (the masked version above is used instead).
    api_key = serializers.CharField(
        write_only=True, required=False, allow_blank=True,
        help_text='Plain-text API key — encrypted before storage. Send empty '
                  'string to clear the stored key.',
    )

    class Meta:
        model = AIServiceConfig
        fields = (
            'id', 'service', 'service_display', 'is_enabled',
            'provider', 'provider_display', 'model_name',
            'api_key', 'api_key_masked',
            'monthly_cap_inr', 'alert_at_pct', 'usd_to_inr_rate',
            'current_month_cost_inr', 'current_month_tokens', 'current_month_calls',
            'budget_usage_pct',
            'alert_sent', 'auto_disabled_at',
            'created_at', 'updated_at',
        )
        read_only_fields = (
            'id', 'service', 'service_display', 'provider_display', 'api_key_masked',
            'current_month_cost_inr', 'current_month_tokens', 'current_month_calls',
            'budget_usage_pct', 'alert_sent', 'auto_disabled_at',
            'created_at', 'updated_at',
        )

    def get_api_key_masked(self, obj):
        """Return dots + last-4 style mask so admin can confirm a key is set."""
        if not obj.api_key_encrypted:
            return ''
        # We never surface the plaintext, so just show '••••••••' as a
        # "key is set" indicator. Real length reveal would leak info.
        return '••••••••'

    def get_budget_usage_pct(self, obj):
        return obj.budget_usage_pct

    def update(self, instance, validated_data):
        # Extract the write-only api_key and route it through set_api_key so
        # encryption happens in the model helper. Empty string → clear.
        raw_key = validated_data.pop('api_key', None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        if raw_key is not None:
            instance.set_api_key(raw_key)
        instance.save()
        return instance


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _audit(user, obj, op: str, changes_before: dict):
    """AuditLog row for a config change. Uses DPR_CONFIG_CHANGE to match the
    existing "central-admin control" audit taxonomy."""
    AuditLog.objects.create(
        user=user,
        action=AuditLog.Action.DPR_CONFIG_CHANGE,
        object_repr=f'AIServiceConfig({obj.service})',
        changes={
            'op': op,
            'service': obj.service,
            'before': changes_before,
            'after': {
                'provider': obj.provider,
                'model_name': obj.model_name,
                'is_enabled': obj.is_enabled,
                'monthly_cap_inr': str(obj.monthly_cap_inr),
                'has_api_key': bool(obj.api_key_encrypted),
            },
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Views
# ─────────────────────────────────────────────────────────────────────────────

@extend_schema(tags=['Admin — AI Services'])
class AIServiceListView(APIView):
    """GET all configured AI services."""

    permission_classes = [IsAuthenticated, IsSuperAdminOrReadOnly]

    def get(self, request):
        # Ensure a row exists for each declared Service — admin sees all 4
        # rows even on a fresh DB.
        for choice, _ in AIServiceConfig.Service.choices:
            AIServiceConfig.objects.get_or_create(
                service=choice,
                defaults={'is_enabled': True, 'monthly_cap_inr': 0},
            )
        rows = AIServiceConfig.objects.all().order_by('service')
        return StandardResponse.success(
            AIServiceConfigSerializer(rows, many=True).data,
            f'{rows.count()} AI service(s) retrieved',
        )


@extend_schema(tags=['Admin — AI Services'])
class AIServiceDetailView(APIView):
    """GET / PATCH a single service config."""

    permission_classes = [IsAuthenticated, IsSuperAdminOrReadOnly]

    def _get(self, pk):
        try:
            return AIServiceConfig.objects.get(pk=pk), None
        except AIServiceConfig.DoesNotExist:
            return None, StandardResponse.error('AI service not found', status_code=404)

    def get(self, request, pk):
        obj, err = self._get(pk)
        if err:
            return err
        return StandardResponse.success(AIServiceConfigSerializer(obj).data, 'Retrieved')

    def patch(self, request, pk):
        obj, err = self._get(pk)
        if err:
            return err
        # Snapshot before mutation for audit diff
        before = {
            'provider': obj.provider,
            'model_name': obj.model_name,
            'is_enabled': obj.is_enabled,
            'monthly_cap_inr': str(obj.monthly_cap_inr),
            'has_api_key': bool(obj.api_key_encrypted),
        }
        ser = AIServiceConfigSerializer(obj, data=request.data, partial=True)
        if not ser.is_valid():
            return StandardResponse.error(ser.errors, status_code=400)
        obj = ser.save()
        _audit(request.user, obj, 'update', before)
        return StandardResponse.success(
            AIServiceConfigSerializer(obj).data, 'AI service updated',
        )


@extend_schema(tags=['Admin — AI Services'])
class AIServiceResetUsageView(APIView):
    """POST → reset current-month totals. Admin recovery for stuck auto-disable."""

    permission_classes = [IsAuthenticated, IsSuperAdminOrReadOnly]

    def post(self, request, pk):
        try:
            obj = AIServiceConfig.objects.get(pk=pk)
        except AIServiceConfig.DoesNotExist:
            return StandardResponse.error('AI service not found', status_code=404)
        obj.reset_monthly_totals()
        _audit(request.user, obj, 'reset_usage', before={})
        return StandardResponse.success(
            AIServiceConfigSerializer(obj).data,
            'Monthly usage reset',
        )


@extend_schema(tags=['Admin — AI Services'])
class AIProvidersInfoView(APIView):
    """GET → provider metadata for FE dropdowns.

    Returns:
      - list of provider IDs + labels
      - default model per provider
      - list of known (provider, model) pairs with pricing (so the FE can
        show "cheap" / "expensive" hints next to model options)
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        providers = [
            {'value': v, 'label': l, 'default_model': DEFAULT_MODELS.get(v, '')}
            for v, l in AIServiceConfig.Provider.choices
        ]
        # Group known models by provider for the model-picker dropdown.
        models_by_provider: dict[str, list[dict]] = {}
        for (provider, model), (in_rate, out_rate) in PRICING_USD_PER_MTOKEN.items():
            models_by_provider.setdefault(provider, []).append({
                'model': model,
                'input_usd_per_mtoken': str(in_rate),
                'output_usd_per_mtoken': str(out_rate),
            })
        # Stable ordering — sorted by input price ascending so cheapest first.
        for models in models_by_provider.values():
            models.sort(key=lambda m: float(m['input_usd_per_mtoken']))

        return StandardResponse.success({
            'providers': providers,
            'models_by_provider': models_by_provider,
        }, 'Provider info retrieved')
