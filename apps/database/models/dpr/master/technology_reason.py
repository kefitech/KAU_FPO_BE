"""
Technology Selection Reasons per KAU spec §2.3.12 B (15 options).
Some reasons require the FPO to attach a brief justification (max 100 words).
"""

from django.db import models

from ._base import DPRMasterBase


class DPRTechnologyReason(DPRMasterBase):
    requires_justification = models.BooleanField(
        default=False,
        help_text='If True, when the FPO selects this reason, they must attach a brief justification '
                  '(spec §2.3.12 B: optional per reason, but flagged reasons are always required).',
    )

    class Meta(DPRMasterBase.Meta):
        db_table = 'dpr_technology_reason'
        verbose_name = 'DPR — Technology Selection Reason'
        verbose_name_plural = 'DPR — Technology Selection Reasons'
