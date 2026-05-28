"""
External API Settings — KAU-FPO Platform
=========================================

Stores encrypted credentials for third-party verification APIs.
Admin configures via /api/admin/external-apis/.

Services:
    pan_verification   — Income Tax Department API (SRS §5.2)
    gstin_verification — GST API via GSP integration (SRS §5.2)
    cin_verification   — MCA21 Portal API (SRS §5.2)

Flow:
    is_active=True  → VerificationService calls live API first
    is_active=False → VerificationService falls back to format-only validation
    API failure     → falls back to format-only + logs failure for admin review
"""

from django.db import models

from apps.core.models.base import BaseModel

1
class ExternalAPISettings(BaseModel):
    """
    Encrypted credentials for external verification APIs.

    config JSONField holds sensitive fields (api_key, client_id, password etc.)
    encrypted via Fernet — same pattern as NotificationChannelSettings.
    Masked as '••••••••' in API responses.
    """

    SERVICE_PAN   = 'pan_verification'
    SERVICE_GSTIN = 'gstin_verification'
    SERVICE_CIN   = 'cin_verification'

    SERVICE_CHOICES = [
        (SERVICE_PAN,   'PAN Verification (Income Tax Dept API)'),
        (SERVICE_GSTIN, 'GSTIN Verification (GST API / GSP)'),
        (SERVICE_CIN,   'CIN Verification (MCA21 Portal API)'),
    ]

    service   = models.CharField(max_length=30, choices=SERVICE_CHOICES, unique=True)
    api_url   = models.URLField(blank=True)
    config    = models.JSONField(
        default=dict,
        help_text='Encrypted credentials. Sensitive keys: api_key, client_id, password, secret'
    )
    is_active = models.BooleanField(
        default=False,
        help_text='False = format-only fallback. True = live API verification.'
    )

    class Meta:
        verbose_name        = 'External API Setting'
        verbose_name_plural = 'External API Settings'
        ordering            = ['service']

    def __str__(self):
        status = 'active' if self.is_active else 'inactive'
        return f"{self.get_service_display()} ({status})"
