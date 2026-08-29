"""
DPR §2.3.5 — Proposed Products and Services.

Multi-entry table per KAU spec. Two tables:
    DPRSectionProducts    — 1:1 with project (container + is_complete)
    DPRProductItem        — N per section (10 columns per row from spec)

Note on KAU spec ambiguity flagged 2026-08-25:
    §2.3.5 has TWO separate dropdowns "Primary / Secondary Product" AND "Product Type"
    (finished/intermediate/by-product/service). §2.3.11 Cat A conflates both under a
    single "Product Type" field. We handle §2.3.5 correctly with both fields separate;
    §2.3.11 kept as-is until KAU clarifies the intended semantics.
"""

from django.db import models

from apps.core.models.base import TimeStampedModel, AuditModel


PRIMARY_SECONDARY_CHOICES = [
    ('primary', 'Primary Product'),
    ('secondary', 'Secondary Product'),
]


class DPRSectionProducts(TimeStampedModel, AuditModel):
    """§2.3.5 section container. One-to-one with DPRProject."""

    project = models.OneToOneField(
        'database.DPRProject',
        on_delete=models.CASCADE,
        related_name='section_products',
    )
    is_complete = models.BooleanField(default=False)

    class Meta:
        db_table = 'dpr_section_products'
        verbose_name = 'DPR — Products & Services Section'
        verbose_name_plural = 'DPR — Products & Services Sections'

    def __str__(self):
        return f'Products section for project {self.project_id}'


class DPRProductItem(TimeStampedModel, AuditModel):
    """One product/service row — 10 KAU-spec columns."""

    section = models.ForeignKey(
        DPRSectionProducts,
        on_delete=models.CASCADE,
        related_name='items',
    )
    order = models.IntegerField(default=0)

    name = models.CharField(max_length=200)
    category = models.ForeignKey(
        'database.DPRProductCategory',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='+',
    )
    primary_or_secondary = models.CharField(
        max_length=10, choices=PRIMARY_SECONDARY_CHOICES, blank=True,
    )
    product_type = models.ForeignKey(
        'database.DPRProductType',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='+',
        help_text='Finished / Intermediate / By-product / Service',
    )
    unit_of_measurement = models.ForeignKey(
        'database.DPRCapacityUnit',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='+',
    )
    annual_quantity = models.DecimalField(max_digits=18, decimal_places=3, null=True, blank=True)
    selling_unit = models.ForeignKey(
        'database.DPRCapacityUnit',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='dpr_product_selling_unit',
        help_text='Unit at point of sale (may differ from unit_of_measurement — e.g. produced in kg, sold in packets)',
    )
    selling_price_per_unit = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    is_value_added = models.BooleanField(default=False)
    description = models.TextField(blank=True)

    class Meta:
        db_table = 'dpr_product_item'
        verbose_name = 'DPR — Product Item'
        verbose_name_plural = 'DPR — Product Items'
        ordering = ['order', 'id']

    def __str__(self):
        return self.name or f'Product #{self.pk}'
