"""
Project Components per KAU spec §2.3.2 — organised into 6 groups.
Selection drives the dynamic questionnaire (Ch 1.7.2, Ch 6.3-6.4).
"""

from django.db import models

from ._base import DPRMasterBase


class DPRComponent(DPRMasterBase):
    class Group(models.TextChoices):
        PRIMARY_PRODUCTION      = 'primary_production', 'Primary Production'
        PROCESSING_VALUE_ADD    = 'processing_value_addition', 'Processing & Value Addition'
        STORAGE_POST_HARVEST    = 'storage_post_harvest', 'Storage & Post-Harvest'
        MARKETING_BUSINESS_DEV  = 'marketing_business_dev', 'Marketing & Business Development'
        SERVICE_ENTERPRISES     = 'service_enterprises', 'Service-Based Enterprises'
        SUPPORTING_INFRA        = 'supporting_infrastructure', 'Supporting Infrastructure'

    group = models.CharField(
        max_length=50, choices=Group.choices, db_index=True,
        help_text='Which of the 6 KAU spec groups this component belongs to',
    )

    class Meta(DPRMasterBase.Meta):
        db_table = 'dpr_component'
        verbose_name = 'DPR — Project Component'
        verbose_name_plural = 'DPR — Project Components'
        ordering = ['group', 'order', 'code']
