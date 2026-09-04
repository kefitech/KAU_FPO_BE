"""Project objectives per KAU spec §2.2 field 6."""

from ._base import DPRMasterBase


class DPRProjectObjective(DPRMasterBase):
    class Meta(DPRMasterBase.Meta):
        db_table = 'dpr_project_objective'
        verbose_name = 'DPR — Project Objective'
        verbose_name_plural = 'DPR — Project Objectives'
