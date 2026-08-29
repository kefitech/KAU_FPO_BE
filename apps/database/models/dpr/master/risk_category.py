"""Risk category groupings per KAU spec §2.3.22 (Production, Market, Financial, Institutional, Environmental, Regulatory)."""

from ._base import DPRMasterBase


class DPRRiskCategory(DPRMasterBase):
    class Meta(DPRMasterBase.Meta):
        db_table = 'dpr_risk_category'
        verbose_name = 'DPR — Risk Category'
        verbose_name_plural = 'DPR — Risk Categories'
