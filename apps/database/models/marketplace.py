"""
Marketplace Models — P2-11

Product         : FPO product listings
BuyerDirectory  : verified buyers (admin-managed)
BuyerSellerMatch: AI-matched buyer-product pairs
MarketPrice     : daily prices from AGMARKNET
Inquiry         : buyer-initiated purchase inquiries on a product
"""
import os
import uuid

from django.db import models
from apps.core.models.base import BaseModel

#arunima 23 sep
def _product_image_path(instance, filename):
    # Each upload gets its own UUID *folder* (guarantees no collisions,
    # same as before), but the filename itself is preserved so the FPO
    # sees their own original file name in the UI instead of a raw UUID.
    return f'marketplace/products/{uuid.uuid4()}/{filename}'


class Product(BaseModel):
    """
    Product MASTER — the FPO's product identity (name, commodity, image,
    description). Does NOT carry quantity/price/availability — that lives
    on ProductStock (see below). A product can exist with zero stock
    (e.g. right after its stock batch expired and was removed) or with
    exactly one active stock batch at a time.
    """

    fpo = models.ForeignKey(
        'database.FPO', on_delete=models.CASCADE, related_name='products'
    )
    name = models.JSONField(help_text='{"en":"Organic Rice","ml":"ഓർഗാനിക് അരി"}')
    commodity = models.ForeignKey(
        'core.MasterLookup', on_delete=models.PROTECT, related_name='products'
    )
    description = models.JSONField(default=dict, help_text='{"en":"...","ml":"..."}')
    image = models.ImageField(
        upload_to=_product_image_path, null=True, blank=True,
        help_text='Product photo shown on FPO products page and public Market Hub'
    )

    class Meta:
        verbose_name = 'Product'
        verbose_name_plural = 'Products'
        ordering = ['-created_at']

    def __str__(self):
        name = self.name.get('en', '') if isinstance(self.name, dict) else str(self.name)
        return f"{name} — {self.fpo}"

    @property
    def latest_stock(self):
        """
        The batch to surface in the flat/legacy serializer fields: most
        recent ACTIVE batch if any, else most recent batch of any status,
        else None. Soft-deleted stocks are always skipped — a batch the
        FPO removed should never resurface in the detail header.

        Walks any prefetched `stocks` cache so a page of products hitting
        ProductSerializer doesn't N+1 the DB.
        """
        cache = getattr(self, '_prefetched_objects_cache', None)
        if cache and 'stocks' in cache:
            all_stocks = [s for s in cache['stocks'] if not s.is_deleted]
        else:
            all_stocks = list(
                self.stocks.filter(is_deleted=False).order_by('-created_at')
            )

        for s in all_stocks:
            if s.status == ProductStock.Status.ACTIVE:
                return s
        return all_stocks[0] if all_stocks else None


class ProductStock(BaseModel):
    """
    A stock/listing batch for a Product. **Multiple batches per product are
    allowed** — the same Organic Rice product can have a 100kg batch @ ₹85
    plus a 500kg batch @ ₹82 live simultaneously. Each batch has its own
    quantity, price, availability window, and lifecycle (DRAFT → ACTIVE →
    EXPIRED → hard-deleted after KAU #3 3-day grace).

    The Product (master) carries the identity: name, commodity, image,
    description. Stocks are the sellable units.
    """

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

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='stocks'
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    unit = models.CharField(max_length=20, choices=Unit.choices)
    price_per_unit = models.DecimalField(max_digits=10, decimal_places=2)
    quality_certification = models.CharField(
        max_length=200, blank=True,
        help_text='Free text — e.g. FSSAI, NPOP Organic, ISO 22000'
    )
    contact_phone = models.CharField(
        max_length=20, blank=True,
        help_text='Direct seller phone for this batch — buyers see a tel: link '
                  'on the product card. Blank means "no direct line, inquiries '
                  'route via the Market Hub form only".'
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
    # 3-day-before-expiry reminder should fire exactly once per stock batch —
    # this flag prevents the daily Celery task from re-sending it every day
    # between the 3-day mark and actual expiry.
    expiry_reminder_sent = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Product Stock'
        verbose_name_plural = 'Product Stock'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.product} — {self.quantity}{self.unit} ({self.status})"


class BuyerDirectory(BaseModel):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        VERIFIED = 'verified', 'Verified'
        REJECTED = 'rejected', 'Rejected'

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
    # FPO-to-FPO marketplace (RCD Phase 2, §2.10 Action Items 3 & 4)
    fpo = models.ForeignKey(
        'database.FPO', on_delete=models.CASCADE, null=True, blank=True,
        related_name='buyer_registration',
        help_text='Set only when this row is an FPO registering itself to buy from '
                  'other FPOs. Null for regular external buyers added by admin.'
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.VERIFIED,
        help_text='pending = FPO self-registration awaiting KAU review; verified = '
                  'approved / admin-added directly; rejected = denied.'
    )
    # External buyer self-registration (login account link)
    user = models.OneToOneField(
        'auth.User', on_delete=models.CASCADE, null=True, blank=True,
        related_name='buyer_profile',
        help_text='Login account for this buyer, when they have one (external buyer '
                  'self-registration). Null for FPO-linked buyer rows and for legacy '
                  'admin-added external buyers with no login.'
    )

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
    message = models.TextField(
        blank=True,
        help_text='Buyer-submitted message, only populated for rows created via the '
                   'public Market Hub anonymous inquiry flow (PublicProductInquireView). '
                   'Blank for algorithmic suggested matches from run_matching().'
    )

    class Meta:
        verbose_name = 'Buyer Seller Match'
        verbose_name_plural = 'Buyer Seller Matches'

    def __str__(self):
        return f"{self.product} → {self.buyer} ({self.match_score})"


class Inquiry(BaseModel):
    """
    A verified buyer's structured purchase inquiry on a specific product.

    Distinct from BuyerSellerMatch, which represents algorithmic/system-
    suggested matches (has match_score, status=suggested, etc.) — this
    model represents an explicit, buyer-initiated request.

    Works for both buyer types (FPO-as-buyer and external buyer) via the
    `buyer` FK to BuyerDirectory, which already distinguishes the two
    (fpo set = FPO-as-buyer, user set = external buyer).

    contact_user is NOT a snapshot — it's a live link to whichever account
    submitted the inquiry (buyer.fpo.primary_user for FPO-as-buyer, or
    buyer.user for external buyer), so the seller always sees this
    contact's CURRENT phone/email. If that account is later deleted,
    contact_user becomes null and the seller UI shows "Contact no longer
    available" (SET_NULL, not CASCADE — deleting a user must not delete
    the inquiry record itself).

    submitted_by is the account that actually pressed "send": the same as
    contact_user except when an FPO team member inquires on behalf of their
    FPO. Both hear about status changes.
    """

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        CONTACTED = 'contacted', 'Contacted'
        RESOLVED = 'resolved', 'Resolved'

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='inquiries'
    )
    buyer = models.ForeignKey(
        BuyerDirectory, on_delete=models.CASCADE, related_name='inquiries'
    )
    contact_user = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='product_inquiries',
        help_text='The buyer account that submitted this inquiry, at time of '
                   'submission. Resolved from buyer.fpo.primary_user (FPO-as-buyer) '
                   'or buyer.user (external buyer). NOT a snapshot — contact info is '
                   'always read live from this account. Null if that account was '
                   'later deleted.'
    )
    submitted_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='submitted_inquiries',
        help_text='The account that actually submitted this inquiry. Differs from '
                  'contact_user when an FPO team member inquires on behalf of their FPO; '
                  'both are notified of status changes. Null on rows older than this '
                  'field or if the account was later deleted.'
    )
    quantity_requested = models.DecimalField(max_digits=12, decimal_places=2)
    message = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)

    class Meta:
        verbose_name = 'Inquiry'
        verbose_name_plural = 'Inquiries'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.buyer} → {self.product} ({self.status})"


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
