"""
Arunima S

Product API — FPO Product Listings
===================================
Base Path: /api/marketplace/products/
"""
import csv
import io
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from django.http import HttpResponse

from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser

from apps.core.exceptions import BusinessLogicError
from apps.core.models.generic import MasterLookup
from apps.core.permissions.rbac import IsAuthenticated, IsFPOManager
from apps.core.services.translation import t
from apps.core.utils.pagination import StandardPagination
from apps.core.utils.responses import StandardResponse
from apps.core.views import TranslatedViewSet
from apps.database.models import Product, ProductStock
from apps.core.services.fpo_permission import get_member_fpo
from apps.marketplace.permissions import CanManageProducts, IsApprovedFPO
from apps.marketplace.serializers import ProductSerializer
from apps.marketplace.services import run_matching


def _clear_public_market_cache():
    """
    Wipe all cached Public Market Hub product-list responses.
    Called whenever a product's status/public visibility could change,
    so new/updated products show up immediately instead of waiting for
    the 1-hour cache TTL to expire naturally.
    """
    from django.core.cache import cache
    try:
        cache.delete_pattern('public:market:products:*')
        cache.delete_pattern('public:market:commodities:*')
        cache.delete_pattern('public:market:opportunities')
    except AttributeError:
        # Cache backend doesn't support delete_pattern (e.g. LocMemCache in tests)
        pass


# =============================================================================
# BULK IMPORT — parsing/validation helpers for POST .../bulk-import/
# =============================================================================

def _parse_decimal(value, field_name):
    """Parse a required positive-number cell (quantity / price_per_unit)."""
    if value is None or str(value).strip() == '':
        raise ValueError(f'{field_name} is required')
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field_name} must be a number, got '{value}'")
    if parsed <= 0:
        raise ValueError(f'{field_name} must be greater than 0')
    return parsed


def _parse_date(value, field_name, required=False):
    """
    Parse a date cell. openpyxl hands back a real datetime/date object for
    date-formatted Excel cells; a CSV upload hands back a plain string
    ('YYYY-MM-DD'), so both are accepted here.
    """
    if value is None or str(value).strip() == '':
        if required:
            raise ValueError(f'{field_name} is required')
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value).strip(), '%Y-%m-%d').date()
    except ValueError:
        raise ValueError(f"{field_name} must be a valid date (YYYY-MM-DD), got '{value}'")


def _create_bulk_product(fpo, row):
    """
    Validate one row from the bulk-import sheet and create a Product +
    ProductStock (status=ACTIVE) from it — per the confirmed decision that
    bulk-imported products go live immediately, no draft review step.

    Raises ValueError with a human-readable message on any validation
    failure; the caller catches this and skips just this row, so one bad
    row never blocks the rest of the file.
    """
    name_en = str(row.get('name_en') or '').strip()
    if not name_en:
        raise ValueError('name_en is required')
    name_ml = str(row.get('name_ml') or '').strip()

    commodity_code = str(row.get('commodity_code') or '').strip().lower()
    if not commodity_code:
        raise ValueError('commodity_code is required')
    try:
        commodity = MasterLookup.objects.get(
            category='commodity', code=commodity_code, is_active=True,
        )
    except MasterLookup.DoesNotExist:
        raise ValueError(f"Unknown commodity_code '{commodity_code}' — check the Commodity Codes sheet")

    description_en = str(row.get('description_en') or '').strip()
    if not description_en:
        raise ValueError('description_en is required')
    description_ml = str(row.get('description_ml') or '').strip()

    quantity = _parse_decimal(row.get('quantity'), 'quantity')
    price_per_unit = _parse_decimal(row.get('price_per_unit'), 'price_per_unit')

    unit = str(row.get('unit') or '').strip().lower()
    valid_units = [choice[0] for choice in ProductStock.Unit.choices]
    if unit not in valid_units:
        raise ValueError(f"unit must be one of {', '.join(valid_units)}, got '{unit}'")

    quality_certification = str(row.get('quality_certification') or '').strip()

    available_from = _parse_date(row.get('available_from'), 'available_from', required=True)
    available_until = _parse_date(row.get('available_until'), 'available_until', required=False)

    product = Product.objects.create(
        fpo=fpo,
        name={'en': name_en, 'ml': name_ml},
        commodity=commodity,
        description={'en': description_en, 'ml': description_ml},
    )
    ProductStock.objects.create(
        product=product,
        quantity=quantity,
        unit=unit,
        price_per_unit=price_per_unit,
        quality_certification=quality_certification,
        available_from=available_from,
        available_until=available_until,
        status=ProductStock.Status.ACTIVE,
    )
    return product


@extend_schema_view(
    list=extend_schema(tags=['Marketplace - Products']),
    create=extend_schema(tags=['Marketplace - Products']),
    retrieve=extend_schema(tags=['Marketplace - Products']),
    update=extend_schema(tags=['Marketplace - Products']),
    partial_update=extend_schema(tags=['Marketplace - Products']),
    destroy=extend_schema(tags=['Marketplace - Products']),
)
class ProductViewSet(TranslatedViewSet):
    """
    GET/POST          /api/marketplace/products/
    GET/PATCH/DELETE  /api/marketplace/products/{id}/
    POST              /api/marketplace/products/{id}/publish/
    POST              /api/marketplace/products/{id}/mark-sold/
    GET               /api/marketplace/products/bulk-template/
    POST              /api/marketplace/products/bulk-import/
    """

    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated, IsFPOManager, IsApprovedFPO, CanManageProducts]
    pagination_class = StandardPagination

    list_message = 'marketplace.products_retrieved'
    create_message = 'marketplace.product_created'
    update_message = 'marketplace.product_updated'
    destroy_message = 'marketplace.product_deleted'

    def get_queryset(self):
        from django.db.models import Q

        # FPO members only see their own FPO's products; exclude soft-deleted rows
        fpo = get_member_fpo(self.request.user)
        queryset = Product.objects.filter(fpo=fpo, is_deleted=False).select_related(
            'commodity', 'fpo', 'stock'
        ).order_by('-created_at')

        search = self.request.query_params.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(name__en__icontains=search) | Q(name__ml__icontains=search)
            )

        status = self.request.query_params.get('status')
        if status in (ProductStock.Status.DRAFT, ProductStock.Status.ACTIVE, ProductStock.Status.SOLD, ProductStock.Status.EXPIRED):
            queryset = queryset.filter(stock__status=status)
        return queryset

    # update()/destroy() are NOT overridden — per house convention, business
    # rule checks live in perform_update()/perform_destroy(), raising
    # BusinessLogicError (HTTP 422). custom_exception_handler (apps/core/
    # exceptions/handlers.py) catches BaseAPIException subclasses and formats
    # them into the standard {"status": "error", "message": ..., "code": ...}
    # shape via exc.to_dict() — so TranslatedViewSet's built-in update()/
    # destroy() (which already return StandardResponse on success) stay
    # untouched.
    #
    # NOTE: BusinessLogicError returns HTTP 422, not 400 — this is a genuine
    # behavior change from the earlier StandardResponse.error(..., status_code=400)
    # version. 422 is arguably more correct for "valid request, wrong state"
    # (vs 400 "malformed request"), but flag this if the frontend specifically
    # expects 400 for these cases.
    def perform_create(self, serializer):
        serializer.save()
        _clear_public_market_cache()

    def perform_update(self, serializer):
        product = serializer.instance
        stock = getattr(product, 'stock', None)
        # A product with no stock at all (e.g. its batch expired and was
        # removed) has nothing to protect — editing is always allowed in
        # that case, since the FPO is likely re-adding stock via this same
        # PATCH. If stock exists, only DRAFT/ACTIVE batches stay editable.
        if stock and stock.status not in (ProductStock.Status.DRAFT, ProductStock.Status.ACTIVE):
            raise BusinessLogicError(
                message=t('marketplace.product_not_editable', self.get_language()),
                code='product_not_editable',
            )
        serializer.save()
        _clear_public_market_cache()

    def perform_destroy(self, instance):
        # Soft delete — draft only. BaseModel provides .soft_delete(), which
        # sets is_deleted=True instead of removing the row.
        stock = getattr(instance, 'stock', None)
        if stock and stock.status != ProductStock.Status.DRAFT:
            raise BusinessLogicError(
                message=t('marketplace.only_draft_deletable', self.get_language()),
                code='only_draft_deletable',
            )
        instance.soft_delete(user=self.request.user)
        _clear_public_market_cache()

    @extend_schema(tags=['Marketplace - Products'])
    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        """draft -> active, then runs buyer-seller matching."""
        product = self.get_object()
        stock = getattr(product, 'stock', None)
        if stock is None or stock.status != ProductStock.Status.DRAFT:
            raise BusinessLogicError(
                message=t('marketplace.only_draft_publishable', self.get_language()),
                code='only_draft_publishable',
            )
        stock.status = ProductStock.Status.ACTIVE
        stock.save()

        run_matching(product)
        _clear_public_market_cache()

        return StandardResponse.success(
            data=ProductSerializer(product).data,
            message=t('marketplace.product_published', self.get_language())
        )

    @extend_schema(tags=['Marketplace - Products'])
    @action(detail=True, methods=['post'], url_path='mark-sold')
    def mark_sold(self, request, pk=None):
        product = self.get_object()
        stock = getattr(product, 'stock', None)
        if stock is None or stock.status != ProductStock.Status.ACTIVE:
            raise BusinessLogicError(
                message=t('marketplace.only_active_can_be_sold', self.get_language()),
                code='only_active_can_be_sold',
            )
        stock.status = ProductStock.Status.SOLD
        stock.save()
        _clear_public_market_cache()
        return StandardResponse.success(
            data=ProductSerializer(product).data,
            message=t('marketplace.product_sold', self.get_language())
        )

    @extend_schema(tags=['Marketplace - Products'], summary='Download bulk-import Excel template')
    @action(detail=False, methods=['get'], url_path='bulk-template')
    def bulk_template(self, request):
        """
        GET /api/marketplace/products/bulk-template/

        Downloads an .xlsx with three sheets:
          - "Products"        — the sheet the FPO fills in and re-uploads
          - "Instructions"     — column meanings and rules
          - "Commodity Codes"  — every valid commodity code, for reference
        """
        wb = openpyxl.Workbook()

        # ── Sheet 1: Products (what the FPO fills in) ──
        ws = wb.active
        ws.title = 'Products'
        headers = [
            'name_en', 'name_ml', 'commodity_code', 'description_en', 'description_ml',
            'quantity', 'unit', 'price_per_unit', 'quality_certification',
            'available_from', 'available_until',
        ]
        header_font = Font(bold=True, color='FFFFFF')
        header_fill = PatternFill(start_color='2563EB', end_color='2563EB', fill_type='solid')
        center = Alignment(horizontal='center', vertical='center')
        for col_idx, header in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center
        for col_idx in range(1, len(headers) + 1):
            ws.column_dimensions[get_column_letter(col_idx)].width = 20
        ws.row_dimensions[1].height = 22

        # ── Sheet 2: Instructions ──
        ws2 = wb.create_sheet(title='Instructions')
        instructions = [
            ('HOW TO FILL THIS FILE', True),
            ('', False),
            ('1. Fill one row per product, starting from row 2 of the "Products" sheet.', False),
            ('2. Do NOT change the column headers in row 1.', False),
            ('3. Required: name_en, commodity_code, description_en, quantity, unit, price_per_unit, available_from.', False),
            ('4. All other columns are optional and can be left blank.', False),
            ('5. Save as .xlsx before uploading.', False),
            ('', False),
            ('COLUMN MEANINGS', True),
            ('', False),
            ('name_en                -> Product name in English (required)', False),
            ('name_ml                -> Product name in Malayalam', False),
            ('commodity_code         -> Must match a code from the "Commodity Codes" sheet (required)', False),
            ('description_en         -> Product description in English (required)', False),
            ('description_ml         -> Product description in Malayalam', False),
            ('quantity               -> A positive number (required)', False),
            ('unit                   -> One of: kg, quintal, mt, litre, piece (required)', False),
            ('price_per_unit         -> A positive number (required)', False),
            ('quality_certification  -> Free text, e.g. FSSAI, NPOP Organic', False),
            ('available_from         -> Date in YYYY-MM-DD format (required)', False),
            ('available_until        -> Date in YYYY-MM-DD format, leave blank if open-ended', False),
            ('', False),
            ('All products created from this sheet go live (Active) immediately.', True),
            ('Product photos cannot be added here — add them by editing each product afterward.', True),
        ]
        for row_idx, (text, is_heading) in enumerate(instructions, start=1):
            cell = ws2.cell(row=row_idx, column=1, value=text)
            if is_heading:
                cell.font = Font(bold=True, size=12)
        ws2.column_dimensions['A'].width = 95

        # ── Sheet 3: Commodity Codes (reference only) ──
        ws3 = wb.create_sheet(title='Commodity Codes')
        ws3.cell(row=1, column=1, value='code').font = Font(bold=True)
        ws3.cell(row=1, column=2, value='name').font = Font(bold=True)
        commodities = MasterLookup.objects.filter(
            category='commodity', is_active=True
        ).order_by('display_order', 'code')
        for row_idx, commodity in enumerate(commodities, start=2):
            ws3.cell(row=row_idx, column=1, value=commodity.code)
            ws3.cell(row=row_idx, column=2, value=commodity.get_name('en'))
        ws3.column_dimensions['A'].width = 20
        ws3.column_dimensions['B'].width = 35

        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)

        response = HttpResponse(
            buffer.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = 'attachment; filename="product_bulk_import_template.xlsx"'
        return response

    @extend_schema(tags=['Marketplace - Products'], summary='Bulk-create products from an uploaded Excel/CSV file')
    @action(detail=False, methods=['post'], url_path='bulk-import', parser_classes=[MultiPartParser])
    def bulk_import(self, request):
        """
        POST /api/marketplace/products/bulk-import/

        Upload a filled bulk-template .xlsx (or .csv) as multipart form
        field "file". Valid rows are created as brand-new, Active products
        (never restocks an existing product — v1 scope, per confirmed
        decision). Invalid rows are skipped and reported back so the FPO
        can fix just those and re-upload. Mirrors the pattern used by the
        team bulk-invite-file endpoint (apps/fpo/api/team.py).
        """
        fpo = get_member_fpo(request.user)

        file = request.FILES.get('file')
        if not file:
            raise BusinessLogicError(
                message='No file uploaded. Send file as multipart form field "file".',
                code='no_file_uploaded',
            )

        filename = file.name.lower()
        rows = []
        try:
            if filename.endswith('.xlsx'):
                wb = openpyxl.load_workbook(file, read_only=True, data_only=True)
                ws = wb['Products'] if 'Products' in wb.sheetnames else wb.active
                headers = [str(c.value).strip().lower() if c.value else '' for c in next(ws.iter_rows())]
                for row in ws.iter_rows(min_row=2, values_only=True):
                    if not row or all(v is None or str(v).strip() == '' for v in row):
                        continue  # skip fully empty rows
                    rows.append(dict(zip(headers, row)))
            elif filename.endswith('.csv'):
                content = file.read().decode('utf-8-sig')
                reader = csv.DictReader(io.StringIO(content))
                rows = [r for r in reader if any((v or '').strip() for v in r.values())]
            else:
                raise BusinessLogicError(
                    message='Only .xlsx and .csv files are supported.',
                    code='unsupported_file_type',
                )
        except BusinessLogicError:
            raise
        except Exception as e:
            raise BusinessLogicError(
                message=f'Could not parse file: {e}',
                code='file_parse_error',
            )

        if not rows:
            raise BusinessLogicError(
                message='File is empty or has no data rows.',
                code='empty_file',
            )

        success, failed, created_products = [], [], []
        for i, row in enumerate(rows, start=2):  # row 1 is the header
            try:
                product = _create_bulk_product(fpo, row)
                created_products.append(product)
                success.append({
                    'row': i,
                    'product_id': product.id,
                    'name': product.name.get('en', ''),
                })
            except Exception as e:
                failed.append({
                    'row': i,
                    'name_en': str(row.get('name_en', '') or ''),
                    'reason': str(e),
                })

        if created_products:
            for product in created_products:
                run_matching(product)
            _clear_public_market_cache()

        return StandardResponse.success(
            data={'success': len(success), 'failed': len(failed), 'results': success, 'errors': failed},
            message=f'{len(success)} product(s) created successfully, {len(failed)} failed.',
        )
