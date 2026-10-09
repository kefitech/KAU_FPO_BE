"""
AI Service Configuration & Usage Tracking — Phase 2
=====================================================
Author: Athul Gopan (Kefi Tech Solutions)
Created: 21-08-2026

AIServiceConfig  : per-feature on/off toggle + monthly budget cap
AIUsageLog       : every Claude API call logged (tokens, cost, feature, FPO)

Admin panel shows:
  - Toggle each AI feature on/off
  - Set monthly ₹ budget cap (auto-disables when hit)
  - Email alert at 80% of budget
  - Full usage log — tokens + estimated cost per call
"""

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

from apps.core.models.base import BaseModel


class AIServiceConfig(BaseModel):

    class Service(models.TextChoices):
        DPR_NARRATIVES = 'dpr_narratives',  'DPR Narrative Generation'
        CHATBOT        = 'chatbot',         'AI Chatbot'
        MARKETING      = 'marketing',       'Marketing Strategy AI'
        TRANSLATE      = 'translate',       'Auto-Translate AI'
        BUSINESS_PLAN  = 'business_plan',   'Business Plan Generation'

    class Provider(models.TextChoices):
        """Which LLM vendor this feature calls.

        Switching provider is a config change — no code deploy needed.
        `apps/fpo/services/dpr/llm_gateway.py` dispatches to the right SDK
        by reading this field.
        """
        MOCK      = 'mock',      'Deterministic mock (no external API)'
        ANTHROPIC = 'anthropic', 'Anthropic Claude'
        OPENAI    = 'openai',    'OpenAI GPT'
        GOOGLE    = 'google',    'Google Gemini'

    service = models.CharField(
        max_length=30, choices=Service.choices, unique=True
    )
    is_enabled = models.BooleanField(
        default=True,
        help_text='Admin toggle — when False the feature returns fallback/placeholder response'
    )
    provider = models.CharField(
        max_length=20, choices=Provider.choices, default=Provider.MOCK,
        help_text='Which LLM provider handles this feature. Change to switch '
                  'vendors without a code deploy. Requires the matching API '
                  'key + model name below.',
    )
    model_name = models.CharField(
        max_length=100, blank=True, default='',
        help_text='Provider-specific model ID. Examples: '
                  'anthropic → "claude-sonnet-4-6"; '
                  'openai → "gpt-4o-mini"; '
                  'google → "gemini-2.5-flash". '
                  'Blank uses the provider\'s current default (see llm_gateway.DEFAULT_MODELS).',
    )

    # Budget cap
    monthly_cap_inr = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text='Monthly spend limit in INR. 0 = no cap.'
    )
    alert_at_pct = models.IntegerField(
        default=80,
        help_text='Send alert email when usage reaches this % of monthly cap'
    )

    # Running totals — reset on 1st of each month by Celery beat task
    current_month_cost_inr = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text='Cumulative cost this calendar month (INR)'
    )
    current_month_tokens = models.BigIntegerField(
        default=0,
        help_text='Total tokens used this calendar month'
    )
    current_month_calls = models.IntegerField(
        default=0,
        help_text='Total API calls made this calendar month'
    )

    # API credentials (encrypted at rest using NOTIFICATION_ENCRYPTION_KEY)
    api_key_encrypted = models.TextField(
        blank=True, default='',
        help_text='Anthropic API key — stored encrypted. Set via admin API.'
    )
    usd_to_inr_rate = models.DecimalField(
        max_digits=8, decimal_places=2, default=84,
        help_text='USD → INR conversion rate for cost tracking'
    )

    # Alert state
    alert_sent = models.BooleanField(
        default=False,
        help_text='True once the 80% alert email has been sent this month — reset monthly'
    )
    auto_disabled_at = models.DateTimeField(
        null=True, blank=True,
        help_text='When this service was auto-disabled due to budget cap — cleared on monthly reset'
    )

    class Meta:
        verbose_name        = 'AI Service Config'
        verbose_name_plural = 'AI Service Configs'
        ordering            = ['service']

    def __str__(self):
        status = 'enabled' if self.is_enabled else 'disabled'
        return f"{self.get_service_display()} ({status})"

    def get_api_key(self) -> str:
        """Return decrypted API key, or '' if not set."""
        if not self.api_key_encrypted:
            return ''
        try:
            from apps.notifications.utils import decrypt_value
            return decrypt_value(self.api_key_encrypted)
        except Exception:
            return ''

    def set_api_key(self, raw_key: str):
        """Encrypt and store API key. Call save() after."""
        if not raw_key:
            self.api_key_encrypted = ''
            return
        from apps.notifications.utils import encrypt_value
        self.api_key_encrypted = encrypt_value(raw_key)

    @property
    def budget_usage_pct(self):
        if not self.monthly_cap_inr or self.monthly_cap_inr == 0:
            return None
        return round(float(self.current_month_cost_inr) / float(self.monthly_cap_inr) * 100, 1)

    def record_usage(self, cost_inr: float, tokens: int):
        """
        Called after every successful Claude API call.
        Updates running totals and auto-disables if budget cap is hit.
        """
        from decimal import Decimal
        self.current_month_cost_inr += Decimal(str(cost_inr))
        self.current_month_tokens   += tokens
        self.current_month_calls    += 1

        fields = ['current_month_cost_inr', 'current_month_tokens', 'current_month_calls']

        # Auto-disable if cap exceeded
        auto_disabled_now = False
        if self.monthly_cap_inr and self.current_month_cost_inr >= self.monthly_cap_inr:
            if self.is_enabled:
                auto_disabled_now = True
            self.is_enabled       = False
            self.auto_disabled_at = timezone.now()
            fields += ['is_enabled', 'auto_disabled_at']

        # Wave B (2026-10-09): the alert threshold existed but nothing ever
        # fired. Notify super admins once per month at alert_at_pct, and
        # again (regardless of alert_sent) the moment auto-disable trips.
        alert_now = False
        _pct = self.budget_usage_pct
        if (self.monthly_cap_inr and not self.alert_sent and _pct is not None
                and _pct >= (self.alert_at_pct or 80)):
            alert_now = True
            self.alert_sent = True
            fields += ['alert_sent']

        self.save(update_fields=fields)

        if alert_now or auto_disabled_now:
            self._send_budget_alert(disabled=auto_disabled_now)

    def _send_budget_alert(self, disabled: bool) -> None:
        """Email + in-app alert to every active super admin. Best-effort —
        a notification failure must never break the LLM call path."""
        try:
            from django.contrib.auth.models import User
            from apps.notifications.services import send_notification
            status_line = (
                'The service has been AUTOMATICALLY DISABLED for the rest of '
                'the month (it re-enables on the monthly reset).'
                if disabled else
                'The service remains enabled; it will auto-disable if the '
                'cap is reached.'
            )
            context_base = {
                'service_label': self.get_service_display(),
                'usage_pct':     f'{self.budget_usage_pct}',
                'spend_inr':     f'{self.current_month_cost_inr:,.0f}',
                'cap_inr':       f'{self.monthly_cap_inr:,.0f}',
                'status_line':   status_line,
            }
            admins = User.objects.filter(
                groups__name='super_admin', is_active=True,
            ).distinct()
            for admin in admins:
                for channel in ('email', 'in_app'):
                    try:
                        send_notification(
                            user=admin,
                            code='ai_budget_alert',
                            channel=channel,
                            context={**context_base, 'user_name': admin.get_full_name() or admin.username},
                        )
                    except Exception:  # noqa: BLE001
                        pass
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception('AI budget alert dispatch failed')

    def reset_monthly_totals(self):
        """Called by Celery beat on 1st of each month."""
        self.current_month_cost_inr = 0
        self.current_month_tokens   = 0
        self.current_month_calls    = 0
        self.alert_sent             = False
        self.auto_disabled_at       = None
        if not self.is_enabled and self.auto_disabled_at:
            self.is_enabled = True  # re-enable after monthly reset
        self.save(update_fields=[
            'current_month_cost_inr', 'current_month_tokens',
            'current_month_calls', 'alert_sent', 'auto_disabled_at', 'is_enabled',
        ])


class AIUsageLog(BaseModel):
    """
    One row per Claude API call.
    Used for admin usage dashboard and cost tracking.
    """

    class Service(models.TextChoices):
        DPR_NARRATIVES = 'dpr_narratives', 'DPR Narrative Generation'
        CHATBOT        = 'chatbot',        'AI Chatbot'
        MARKETING      = 'marketing',      'Marketing Strategy AI'
        TRANSLATE      = 'translate',      'Auto-Translate AI'
        BUSINESS_PLAN  = 'business_plan',  'Business Plan Generation'

    service = models.CharField(max_length=30, choices=Service.choices)
    fpo = models.ForeignKey(
        'database.FPO', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='ai_usage_logs',
        help_text='Which FPO triggered this call (null for system-level calls)'
    )
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='ai_usage_logs'
    )
    provider = models.CharField(
        max_length=20, blank=True, default='',
        help_text='Which LLM vendor served this call — mirrors AIServiceConfig.provider '
                  'at the time of the call. Useful for cost breakdown when a service '
                  'switches provider mid-month.',
    )
    model_used = models.CharField(
        max_length=100, default='claude-sonnet-4-6',
        help_text='Exact model ID used for this call'
    )

    # Token counts (returned by Anthropic API in every response)
    input_tokens  = models.IntegerField(default=0)
    output_tokens = models.IntegerField(default=0)
    total_tokens  = models.IntegerField(default=0)

    # Cost (calculated from Anthropic pricing at time of call)
    cost_usd = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    cost_inr = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Outcome
    success       = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)

    # What was generated (optional reference)
    reference_id  = models.CharField(
        max_length=100, blank=True,
        help_text='e.g. DPRProject ID or ChatConversation ID'
    )

    class Meta:
        verbose_name        = 'AI Usage Log'
        verbose_name_plural = 'AI Usage Logs'
        ordering            = ['-created_at']
        indexes             = [
            models.Index(fields=['service', 'created_at']),
            models.Index(fields=['fpo', 'created_at']),
        ]

    def __str__(self):
        return f"{self.get_service_display()} — {self.total_tokens} tokens — ₹{self.cost_inr}"
