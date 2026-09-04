"""Product category dropdown per KAU spec §2.3.5."""

from ._base import DPRMasterBase


class DPRProductCategory(DPRMasterBase):
    class Meta(DPRMasterBase.Meta):
        db_table = 'dpr_product_category'
        verbose_name = 'DPR — Product Category'
        verbose_name_plural = 'DPR — Product Categories'
