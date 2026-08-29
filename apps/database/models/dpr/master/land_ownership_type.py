"""Land ownership options per KAU spec §2.3.6 C / §2.3.13 A (Owned by FPO, Owned by Members, Leased, Rented, Government Land, Proposed to be Purchased, Others)."""

from ._base import DPRMasterBase


class DPRLandOwnershipType(DPRMasterBase):
    class Meta(DPRMasterBase.Meta):
        db_table = 'dpr_land_ownership_type'
        verbose_name = 'DPR — Land Ownership Type'
        verbose_name_plural = 'DPR — Land Ownership Types'
