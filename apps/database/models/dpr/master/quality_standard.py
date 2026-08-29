"""Quality standards / certifications per KAU spec §2.3.12 E (FSSAI, AGMARK, BIS, Organic, PGS, GlobalG.A.P., HACCP, ISO 22000, GMP, Export Cert, etc)."""

from ._base import DPRMasterBase


class DPRQualityStandard(DPRMasterBase):
    class Meta(DPRMasterBase.Meta):
        db_table = 'dpr_quality_standard'
        verbose_name = 'DPR — Quality Standard'
        verbose_name_plural = 'DPR — Quality Standards'
