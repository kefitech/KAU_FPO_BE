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

    service = models.CharField(
        max_length=30, choices=Service.choices, unique=True
    )
    is_enabled = models.BooleanField(
        default=True,
        help_text='Admin toggle — when False the feature returns fallback/placeholder response'
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
        if self.monthly_cap_inr and self.current_month_cost_inr >= self.monthly_cap_inr:
            self.is_enabled       = False
            self.auto_disabled_at = timezone.now()
            fields += ['is_enabled', 'auto_disabled_at']

        self.save(update_fields=fields)

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
