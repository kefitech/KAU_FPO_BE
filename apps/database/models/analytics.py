"""
Analytics Snapshot Models — P2-09

Populated by Celery Beat task: refresh_analytics_snapshots — runs daily at 2:00 AM IST.
Dashboards read from this table — never run heavy aggregation queries live.
"""
from django.db import models
from apps.core.models.base import BaseModel


class AnalyticsSnapshot(BaseModel):
    snapshot_date = models.DateField()
    district = models.CharField(
        max_length=10, null=True, blank=True,
        help_text='null = state-level snapshot; TRS = Thrissur only'
    )
    fpo_count = models.IntegerField(default=0)
    approved_count = models.IntegerField(default=0)
    draft_count = models.IntegerField(default=0)
    rejected_count = models.IntegerField(default=0)
    suspended_count = models.IntegerField(default=0)
    tier_distribution = models.JSONField(
        default=dict,
        help_text='{"A":12,"B":34,"C":56,"D":8,"not_assessed":20}'
    )
    commodity_breakdown = models.JSONField(
        default=dict,
        help_text='{"rice":45,"banana":30}'
    )
    scheme_utilisation = models.JSONField(
        default=dict,
        help_text='{"scheme_id":{"applied":10,"approved":7}}'
    )
    avg_member_count = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    total_members = models.IntegerField(default=0)
    women_members = models.IntegerField(default=0)
    new_registrations_this_month = models.IntegerField(default=0)

    class Meta:
        verbose_name = 'Analytics Snapshot'
        verbose_name_plural = 'Analytics Snapshots'
        unique_together = ('snapshot_date', 'district')
        ordering = ['-snapshot_date']

    def __str__(self):
        scope = self.district if self.district else 'State'
        return f"{scope} — {self.snapshot_date}"
