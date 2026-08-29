"""Supporting asset options per KAU spec §2.3.15 H (Trolleys, Pallets, Bins, Racks, Crates, Weighing Scales, Forklifts, Conveyors, Hand Tools, Safety Equipment, Fire Safety, Office Furniture, Computers, Printers, CCTV, UPS, DG Set, Solar Equipment, Other Fixed Assets)."""

from ._base import DPRMasterBase


class DPRSupportingAsset(DPRMasterBase):
    class Meta(DPRMasterBase.Meta):
        db_table = 'dpr_supporting_asset'
        verbose_name = 'DPR — Supporting Asset'
        verbose_name_plural = 'DPR — Supporting Assets'
