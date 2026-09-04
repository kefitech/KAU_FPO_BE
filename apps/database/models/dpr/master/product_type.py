"""Product type per KAU spec §2.3.5 (Finished / Intermediate / By-product / Service)."""

from ._base import DPRMasterBase


class DPRProductType(DPRMasterBase):
    class Meta(DPRMasterBase.Meta):
        db_table = 'dpr_product_type'
        verbose_name = 'DPR — Product Type'
        verbose_name_plural = 'DPR — Product Types'
