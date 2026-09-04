"""Business nature options per KAU spec §2.3.3 (14 options, multi-select)."""

from ._base import DPRMasterBase


class DPRNatureOfBusiness(DPRMasterBase):
    class Meta(DPRMasterBase.Meta):
        db_table = 'dpr_nature_of_business'
        verbose_name = 'DPR — Nature of Business'
        verbose_name_plural = 'DPR — Natures of Business'
