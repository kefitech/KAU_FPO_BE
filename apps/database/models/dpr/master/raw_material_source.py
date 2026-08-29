"""Raw material source options per KAU spec §2.3.10 A (11 options: FPO Members, Local Farmers, Local Market, Wholesale Market, Government Agency, Contract Farming, Other FPO, Traders, Processing Industry, Import, Others)."""

from ._base import DPRMasterBase


class DPRRawMaterialSource(DPRMasterBase):
    class Meta(DPRMasterBase.Meta):
        db_table = 'dpr_raw_material_source'
        verbose_name = 'DPR — Raw Material Source'
        verbose_name_plural = 'DPR — Raw Material Sources'
