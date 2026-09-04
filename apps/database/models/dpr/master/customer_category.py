"""Customer category options per KAU spec §2.3.11 A (Individual Consumers, Farmers, FPOs, Cooperatives, Retail Shops, Wholesalers, Processors, Industries, Exporters, Government, Institutions, Online Customers, Others)."""

from ._base import DPRMasterBase


class DPRCustomerCategory(DPRMasterBase):
    class Meta(DPRMasterBase.Meta):
        db_table = 'dpr_customer_category'
        verbose_name = 'DPR — Customer Category'
        verbose_name_plural = 'DPR — Customer Categories'
