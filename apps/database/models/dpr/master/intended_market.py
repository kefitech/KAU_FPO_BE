"""
Intended Market options per KAU spec §2.3.11 A — Product's target market scope.
KAU admin can add / remove options via /api/admin/dpr/master/intended-markets/.
"""

from ._base import DPRMasterBase


class DPRIntendedMarket(DPRMasterBase):
    class Meta(DPRMasterBase.Meta):
        db_table = 'dpr_intended_market'
        verbose_name = 'DPR — Intended Market'
        verbose_name_plural = 'DPR — Intended Markets'
