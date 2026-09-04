"""Marketing channel options per KAU spec §2.3.11 D (15 options: Farm Gate, Collection Centre, Wholesale, Retail, Supermarkets, Institutional, Hotels, Restaurants, Food Processing, Export, E-commerce, Government Procurement, Online Marketplace, Direct Consumer, Distributor Network, Franchise, Others)."""

from ._base import DPRMasterBase


class DPRMarketingChannel(DPRMasterBase):
    class Meta(DPRMasterBase.Meta):
        db_table = 'dpr_marketing_channel'
        verbose_name = 'DPR — Marketing Channel'
        verbose_name_plural = 'DPR — Marketing Channels'
