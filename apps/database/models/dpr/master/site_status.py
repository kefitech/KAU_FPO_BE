"""Site status options per KAU spec §2.3.6 D (Existing Facility, Vacant Land, Under Construction, Existing Building to be Modified, Existing Building to be Expanded, Others)."""

from ._base import DPRMasterBase


class DPRSiteStatus(DPRMasterBase):
    class Meta(DPRMasterBase.Meta):
        db_table = 'dpr_site_status'
        verbose_name = 'DPR — Site Status'
        verbose_name_plural = 'DPR — Site Statuses'
