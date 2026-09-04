"""Expected outcomes per KAU spec §2.2 field 7."""

from ._base import DPRMasterBase


class DPRProjectOutcome(DPRMasterBase):
    class Meta(DPRMasterBase.Meta):
        db_table = 'dpr_project_outcome'
        verbose_name = 'DPR — Expected Outcome'
        verbose_name_plural = 'DPR — Expected Outcomes'
