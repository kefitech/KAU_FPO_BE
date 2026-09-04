"""Project types per KAU spec §2.2 (new / expansion / diversification / modernisation / value_addition / infrastructure_development)."""

from ._base import DPRMasterBase


class DPRProjectType(DPRMasterBase):
    class Meta(DPRMasterBase.Meta):
        db_table = 'dpr_project_type'
        verbose_name = 'DPR — Project Type'
        verbose_name_plural = 'DPR — Project Types'
