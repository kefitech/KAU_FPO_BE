"""Building type options per KAU spec §2.3.14 B (19 types: Administrative Office, Processing Hall, Storage Warehouse, Cold Storage, Pack House, Raw Material Store, Finished Goods Store, QC Lab, Training Hall, Staff Room, Toilet Block, Security Cabin, Utility Room, Generator Room, Electrical Room, Parking Area, Loading/Unloading Platform, Others)."""

from ._base import DPRMasterBase


class DPRBuildingType(DPRMasterBase):
    class Meta(DPRMasterBase.Meta):
        db_table = 'dpr_building_type'
        verbose_name = 'DPR — Building Type'
        verbose_name_plural = 'DPR — Building Types'
