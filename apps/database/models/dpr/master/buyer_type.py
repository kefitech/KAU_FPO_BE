"""Buyer type dropdown per KAU spec §2.3.11 C."""

from ._base import DPRMasterBase


class DPRBuyerType(DPRMasterBase):
    class Meta(DPRMasterBase.Meta):
        db_table = 'dpr_buyer_type'
        verbose_name = 'DPR — Buyer Type'
        verbose_name_plural = 'DPR — Buyer Types'
