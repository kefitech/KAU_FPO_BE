"""Quality parameter options per KAU spec §2.3.10 D (Moisture, Purity, Size, Colour, Maturity, Foreign Matter, Others)."""

from ._base import DPRMasterBase


class DPRQualityParameter(DPRMasterBase):
    class Meta(DPRMasterBase.Meta):
        db_table = 'dpr_quality_parameter'
        verbose_name = 'DPR — Quality Parameter'
        verbose_name_plural = 'DPR — Quality Parameters'
