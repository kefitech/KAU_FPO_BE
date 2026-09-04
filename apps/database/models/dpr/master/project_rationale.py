"""Project rationale reasons per KAU spec §2.3.7 (29 options)."""

from ._base import DPRMasterBase


class DPRProjectRationale(DPRMasterBase):
    class Meta(DPRMasterBase.Meta):
        db_table = 'dpr_project_rationale'
        verbose_name = 'DPR — Project Rationale'
        verbose_name_plural = 'DPR — Project Rationales'
