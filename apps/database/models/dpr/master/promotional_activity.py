"""
Promotional Activities per KAU spec §2.3.11 G (8 options).
Digital vs. traditional flag helps the AI content generator select relevant guidance.
"""

from django.db import models

from ._base import DPRMasterBase


class DPRPromotionalActivity(DPRMasterBase):
    is_digital = models.BooleanField(
        default=False,
        help_text='True for digital channels (Social Media, Digital Marketing). '
                  'AI marketing narrative differentiates digital vs. traditional strategy.',
    )

    class Meta(DPRMasterBase.Meta):
        db_table = 'dpr_promotional_activity'
        verbose_name = 'DPR — Promotional Activity'
        verbose_name_plural = 'DPR — Promotional Activities'
