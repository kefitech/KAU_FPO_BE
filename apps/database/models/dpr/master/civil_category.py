"""Civil works site development category per KAU spec §2.3.14 C (Land Development, Site Levelling, Roads, Compound Wall, Gate, Drainage, Parking, Borewell, Water Tank, Septic Tank, Rainwater Harvesting, Fire Water Tank, Others)."""

from ._base import DPRMasterBase


class DPRCivilCategory(DPRMasterBase):
    class Meta(DPRMasterBase.Meta):
        db_table = 'dpr_civil_category'
        verbose_name = 'DPR — Civil Category'
        verbose_name_plural = 'DPR — Civil Categories'
