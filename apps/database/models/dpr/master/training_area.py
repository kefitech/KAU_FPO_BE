"""Training area options per KAU spec §2.3.17 E (Machine Operation, QC, Food Safety, Financial Management, Marketing, Digital Systems, Safety, Maintenance, Others)."""

from ._base import DPRMasterBase


class DPRTrainingArea(DPRMasterBase):
    class Meta(DPRMasterBase.Meta):
        db_table = 'dpr_training_area'
        verbose_name = 'DPR — Training Area'
        verbose_name_plural = 'DPR — Training Areas'
