"""
Marketplace Models — P2-11

Product         : FPO product listings
BuyerDirectory  : verified buyers (admin-managed)
BuyerSellerMatch: AI-matched buyer-product pairs
MarketPrice     : daily prices from AGMARKNET
"""
from django.db import models
from apps.core.models.base import BaseModel


class Product(BaseModel):

    class Unit(models.TextChoices):
        KG = 'kg', 'Kilogram'
        QUINTAL = 'quintal', 'Quintal'
        MT = 'mt', 'Metric Tonne'
        LITRE = 'litre', 'Litre'
        PIECE = 'piece', 'Piece'

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        ACTIVE = 'active', 'Active'
        SOLD = 'sold', 'Sold'
        EXPIRED = 'expired', 'Expired'

    fpo = models.ForeignKey(
        'database.FPO', on_delete=models.CASCADE, related_name='products'
    )
    name = models.JSONField(help_text='{"en":"Organic Rice","ml":"ഓർഗാനിക് അരി"}')
    commodity = models.ForeignKey(
        'core.MasterLookup', on_delete=models.PROTECT, related_name='products'
    )
    description = models.JSONField(default=dict, help_text='{"en":"...","ml":"..."}')
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    unit = models.CharField(max_length=20, choices=Unit.choices)
    price_per_unit = models.DecimalField(max_digits=10, decimal_places=2)
    quality_certification = models.CharField(
        max_length=200, blank=True,
        help_text='Free text — e.g. FSSAI, NPOP Organic, ISO 22000'
    )
    available_from = models.DateField()
    available_until = models.DateField(null=True, blank=True)
    is_ondc_listed = models.BooleanField(default=False)
    ondc_product_id = models.CharField(
        max_length=200, null=True, blank=True,
        help_text='Assigned by ONDC after listing'
    )
    is_public = models.BooleanField(
        default=False,
        help_text='Visible on public Market Hub (P2-12)'
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
 
    class Meta:
        verbose_name = 'Product'
        verbose_name_plural = 'Products'
        ordering = ['-created_at']

    def __str__(self):
        name = self.name.get('en', '') if isinstance(self.name, dict) else str(self.name)
        return f"{name} — {self.fpo}"


class BuyerDirectory(BaseModel):
    #--------------------------------------------------------
    #Arunima S 01 Sep 2026
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        VERIFIED = 'verified', 'Verified'
        REJECTED = 'rejected', 'Rejected'
    #----------------------------------------------------------------

    name = models.CharField(max_length=300)
    organisation = models.CharField(max_length=300, blank=True)
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=20, blank=True)
    location = models.CharField(
        max_length=10, blank=True,
        help_text='District code from constants.py e.g. TRS, EKM'
    )
    commodities_interested = models.JSONField(
        default=list,
        help_text='List of MasterLookup commodity codes'
    )
    min_quantity = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    max_quantity = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    unit = models.CharField(max_length=20, blank=True)
    is_verified = models.BooleanField(
        default=False,
        help_text='Verified by KAU Admin before showing to FPOs'
    )
#--------------------------------------------------------------------------------------
#Arunima S 01 Sep 2026
# ── New — FPO-to-FPO marketplace (RCD Phase 2, §2.10 Action Items 3 & 4) ──
    fpo = models.ForeignKey(
        'database.FPO', on_delete=models.CASCADE, null=True, blank=True,
        related_name='buyer_registration',
        help_text='Set only when this row is an FPO registering itself to buy from '
                   'other FPOs. Null for regular external buyers added by admin.'
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.VERIFIED,
        help_text='pending = FPO self-registration awaiting KAU review; verified = '
                   'approved / admin-added directly; rejected = denied. Buyers added '
                   'directly by admin (fpo=None) default to verified, matching prior '
                   'behaviour where admin-added buyers had no review step.'
    )

    # ── New — External Buyer self-registration (login account link) ──
    user = models.OneToOneField(
        'auth.User', on_delete=models.CASCADE, null=True, blank=True,
        related_name='buyer_profile',
        help_text='Login account for this buyer, when they have one (external buyer '
                  'self-registration). Null for FPO-linked buyer rows (see `fpo` field) '
                  'and for legacy admin-added external buyers with no login.'
    )
#----------------------------------------------------------------------------------
    class Meta:
        verbose_name = 'Buyer'
        verbose_name_plural = 'Buyer Directory'

    def __str__(self):
        return f"{self.name} ({self.organisation})"


class BuyerSellerMatch(BaseModel):

    class Status(models.TextChoices):
        SUGGESTED = 'suggested', 'Suggested'
        ACCEPTED = 'accepted', 'Accepted'
        REJECTED = 'rejected', 'Rejected'
        COMPLETED = 'completed', 'Completed'

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='matches'
    )
    buyer = models.ForeignKey(
        BuyerDirectory, on_delete=models.CASCADE, related_name='matches'
    )
    match_score = models.DecimalField(
        max_digits=4, decimal_places=3,
        help_text='AI confidence score 0.000 – 1.000'
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUGGESTED)
    suggested_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Buyer Seller Match'
        verbose_name_plural = 'Buyer Seller Matches'

    def __str__(self):
        return f"{self.product} → {self.buyer} ({self.match_score})"


class MarketPrice(BaseModel):
    commodity = models.ForeignKey(
        'core.MasterLookup', on_delete=models.PROTECT, related_name='market_prices'
    )
    market_name = models.CharField(
        max_length=200,
        help_text='APMC / mandi name — free text as returned by AGMARKNET API'
    )
    date = models.DateField()
    min_price = models.DecimalField(max_digits=10, decimal_places=2)
    max_price = models.DecimalField(max_digits=10, decimal_places=2)
    modal_price = models.DecimalField(max_digits=10, decimal_places=2)
    source = models.CharField(
        max_length=50, default='AGMARKNET',
        help_text='AGMARKNET / e-NAM'
    )

    class Meta:
        verbose_name = 'Market Price'
        verbose_name_plural = 'Market Prices'
        unique_together = ('commodity', 'market_name', 'date', 'source')
        ordering = ['-date']

    def __str__(self):
        return f"{self.commodity} — {self.market_name} ({self.date})"
