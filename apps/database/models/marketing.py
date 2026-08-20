"""
AI Marketing Strategy Models — P2-14
"""
from django.db import models
from apps.core.models.base import BaseModel


class MarketingStrategy(BaseModel):

    class TargetSegment(models.TextChoices):
        RETAIL = 'retail', 'Retail'
        WHOLESALE = 'wholesale', 'Wholesale'
        EXPORT = 'export', 'Export'
        PROCESSING = 'processing', 'Processing'

    fpo = models.ForeignKey(
        'database.FPO', on_delete=models.CASCADE, related_name='marketing_strategies'
    )
    commodity = models.ForeignKey(
        'database.MasterLookup', on_delete=models.PROTECT, related_name='marketing_strategies'
    )
    target_segment = models.CharField(max_length=20, choices=TargetSegment.choices)
    region = models.CharField(
        max_length=10,
        help_text='District code from constants.py e.g. TRS, EKM'
    )
    financial_year = models.CharField(max_length=10, help_text='e.g. 2025-26')
    content = models.JSONField(
        default=dict,
        help_text='market_overview, target_buyers, pricing_strategy, distribution_channels, value_addition, promotion_ideas, seasonal_calendar'
    )
    file_url = models.CharField(
        max_length=1000, null=True, blank=True,
        help_text='S3 URL of generated PDF'
    )
    generated_at = models.DateTimeField(auto_now_add=True)
    claude_model = models.CharField(
        max_length=100, blank=True,
        help_text='e.g. claude-sonnet-4-6'
    )

    class Meta:
        verbose_name = 'Marketing Strategy'
        verbose_name_plural = 'Marketing Strategies'
        ordering = ['-generated_at']

    def __str__(self):
        return f"{self.fpo} — {self.commodity} ({self.target_segment}, {self.financial_year})"
