"""Climate risk options per KAU spec §2.3.20 C (Flood, Drought, Cyclone, Heat Stress, Salinity, Pest, Disease, Others)."""

from ._base import DPRMasterBase


class DPRClimateRisk(DPRMasterBase):
    class Meta(DPRMasterBase.Meta):
        db_table = 'dpr_climate_risk'
        verbose_name = 'DPR — Climate Risk'
        verbose_name_plural = 'DPR — Climate Risks'
