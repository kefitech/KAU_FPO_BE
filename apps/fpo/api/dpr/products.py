"""
DPR §2.3.5 Proposed Products and Services — section endpoints.

Routes:
    GET   /projects/<uuid>/sections/products/
    PATCH /projects/<uuid>/sections/products/
    GET   /projects/<uuid>/sections/products/readiness/
"""

import json

from django.core.files.base import ContentFile
from drf_spectacular.utils import extend_schema, OpenApiTypes
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.utils.responses import StandardResponse
from apps.database.models import (
    DPRCapacityUnit,
    DPRProductItem,
    DPRSectionProducts,
    Product,
)
from apps.fpo.services.dpr.products_validators import validate_section

from .projects import get_project_or_error
from .serializers import DPRProductItemSerializer, DPRSectionProductsSerializer

# Guardrails for the product image upload — kept in sync with the FE
# `<input type="file" accept="…">`. Server-side check is authoritative.
_ALLOWED_IMAGE_TYPES = ('image/jpeg', 'image/png', 'image/webp')
_MAX_IMAGE_BYTES = 5 * 1024 * 1024   # 5 MB


def _get_or_create_section(project, user):
    section, _ = DPRSectionProducts.objects.get_or_create(
        project=project,
        defaults={'created_by': user, 'updated_by': user},
    )
    return section


@extend_schema(tags=['FPO - DPR §2.3.5 Products & Services'])
class DPRProductsSectionView(APIView):
    permission_classes = [IsAuthenticated]
    # Accept both JSON (default section-save path) and multipart (new: lets
    # clients atomically save a new product row + its image in one PATCH).
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    @extend_schema(summary='Retrieve Products & Services section')
    def get(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        section = _get_or_create_section(project, request.user)
        data = DPRSectionProductsSerializer(section, context={'request': request}).data
        return StandardResponse.success(data, 'Section retrieved')

    @extend_schema(
        summary='Update Products & Services (JSON or multipart, single-call save + image)',
        description=(
            'Two request shapes:\n\n'
            '1. **JSON** — full-replace on `items` list, same as before.\n'
            '2. **multipart/form-data** — send `items` as a JSON string in a '
            'form field, and attach files under form field names like '
            '`image_new_1`. Each new item in `items` that carries a matching '
            '`_image_key: "new_1"` will have that file attached as its photo '
            'after the row is created. Existing rows are untouched by the '
            'image parts. Same allowed types (JPEG / PNG / WebP) and size cap '
            '(5 MB) as the standalone image endpoint.'
        ),
    )
    def patch(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        section = _get_or_create_section(project, request.user)

        # ── Detect payload shape ───────────────────────────────────────────
        # request.FILES is populated by MultiPartParser. If any files were
        # sent, we're on the multipart flow: unpack `items` from the form
        # string and collect image parts keyed by their form-field name.
        payload = request.data
        image_files: dict = {}
        if request.FILES:
            # 1. Parse the `items` JSON blob out of the form field.
            raw_items = request.data.get('items')
            if raw_items is None:
                return StandardResponse.error(
                    'Multipart save requires the `items` field '
                    '(JSON-encoded string).',
                    status_code=400,
                )
            if isinstance(raw_items, str):
                try:
                    items_parsed = json.loads(raw_items)
                except json.JSONDecodeError:
                    return StandardResponse.error(
                        '`items` must be a valid JSON array.',
                        status_code=400,
                    )
            else:
                items_parsed = raw_items

            # 2. Extract image files. Keys look like `image_new_1`; the
            # matching row carries `_image_key: "new_1"`. We validate each
            # file up-front so a bad blob is rejected before touching the DB.
            for key, f in request.FILES.items():
                if not key.startswith('image_'):
                    continue
                if getattr(f, 'content_type', None) not in _ALLOWED_IMAGE_TYPES:
                    return StandardResponse.error(
                        f'Unsupported image type on {key}. '
                        'Allowed: JPEG, PNG, WebP.',
                        status_code=400,
                    )
                if f.size > _MAX_IMAGE_BYTES:
                    return StandardResponse.error(
                        f'Image on {key} too large ({f.size} bytes). '
                        'Max size is 5 MB.',
                        status_code=400,
                    )
                # Strip the `image_` prefix so the marker on the row
                # (`_image_key: "new_1"`) matches the dict key.
                image_files[key[len('image_'):]] = f

            # 3. Reshape the payload the serializer expects.
            payload = {'items': items_parsed}

        ser = DPRSectionProductsSerializer(
            section,
            data=payload,
            partial=True,
            context={'request': request, 'image_files': image_files},
        )
        if not ser.is_valid():
            return StandardResponse.error(ser.errors, status_code=400)
        ser.save()
        section.refresh_from_db()
        data = DPRSectionProductsSerializer(section, context={'request': request}).data
        return StandardResponse.success(data, 'Section updated')


@extend_schema(
    tags=['FPO - DPR §2.3.5 Products & Services'],
    summary='Run validators (no save)',
)
class DPRProductsSectionReadinessView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        section = _get_or_create_section(project, request.user)
        result = validate_section(section)
        return StandardResponse.success(result, 'Readiness computed')


@extend_schema(
    tags=['FPO - DPR §2.3.5 Products & Services'],
    summary='Import a product row from the FPO marketplace',
    description=(
        'Creates a new DPRProductItem on the section, pre-filled with the '
        'name, unit, description, and selling price from the picked '
        'marketplace product. If the marketplace product has an image, its '
        'file is COPIED to the DPR item so subsequent changes on the '
        'marketplace listing do not affect the DPR PDF. Returns the newly '
        'created row so the FE can open its edit modal for the DPR-specific '
        'fields (Primary/Secondary, Product Type, etc.).'
    ),
    request={'application/json': {
        'type': 'object',
        'properties': {'marketplace_product_id': {'type': 'integer'}},
        'required': ['marketplace_product_id'],
    }},
)
class DPRProductsImportFromMarketplaceView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        section = _get_or_create_section(project, request.user)

        mp_id = request.data.get('marketplace_product_id')
        if not mp_id:
            return StandardResponse.error(
                'marketplace_product_id is required.', status_code=400,
            )

        # Scoped to the same FPO — never let an FPO import someone else's product.
        marketplace = (
            Product.objects
            .filter(pk=mp_id, fpo=project.fpo, is_deleted=False)
            .first()
        )
        if not marketplace:
            return StandardResponse.error(
                'Marketplace product not found for this FPO.', status_code=404,
            )

        # Best-effort unit mapping — marketplace uses the same codes as
        # DPRCapacityUnit master (kg / quintal / mt / litre / piece).
        unit = DPRCapacityUnit.objects.filter(code=marketplace.unit).first()

        # Name / description are multilang JSON on the marketplace side.
        # DPR uses plain text — take EN and fall back to ML.
        def _pick_lang(field):
            v = field or {}
            if isinstance(v, dict):
                return (v.get('en') or v.get('ml') or '').strip()
            return str(v).strip()

        # Assign a stable order — after any existing rows.
        next_order = (
            (section.items.order_by('-order').values_list('order', flat=True).first() or 0)
            + 1
        )

        item = DPRProductItem.objects.create(
            section=section,
            order=next_order,
            name=_pick_lang(marketplace.name)[:200],
            description=_pick_lang(marketplace.description),
            selling_price_per_unit=marketplace.price_per_unit,
            unit_of_measurement=unit,
            selling_unit=unit,
            created_by=request.user if request.user.is_authenticated else None,
            updated_by=request.user if request.user.is_authenticated else None,
        )

        # Copy the marketplace image to the DPR item — decouples lifecycles.
        # If the FPO later deletes the marketplace listing, the DPR PDF still
        # renders the photo.
        if marketplace.image:
            try:
                marketplace.image.open('rb')
                data = marketplace.image.read()
                filename = marketplace.image.name.rsplit('/', 1)[-1]
                item.image.save(filename, ContentFile(data), save=True)
            finally:
                try:
                    marketplace.image.close()
                except Exception:
                    pass

        data = DPRProductItemSerializer(item, context={'request': request}).data
        return StandardResponse.success(data, 'Product imported from marketplace.')


@extend_schema(tags=['FPO - DPR §2.3.5 Products & Services'])
class DPRProductItemImageView(APIView):
    """Dedicated multipart endpoint for uploading / clearing a product photo.

    POST accepts a single file `image` (jpg/png/webp, ≤5 MB) and stores it
    on the DPRProductItem. DELETE clears the image. Kept separate from the
    section PATCH so JSON payloads stay JSON and re-saves never wipe photos.

    Rendered in the DPR PDF's products chapter + as the cover hero image
    (first product with a photo).
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def _get_item(self, request, project_uuid, item_id):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return None, err
        item = (
            DPRProductItem.objects
            .filter(pk=item_id, section__project=project)
            .first()
        )
        if not item:
            return None, StandardResponse.error(
                'Product item not found.', status_code=404,
            )
        return item, None

    @extend_schema(
        summary='Upload / replace product photo (multipart)',
        request={'multipart/form-data': {
            'type': 'object',
            'properties': {'image': {'type': 'string', 'format': 'binary'}},
            'required': ['image'],
        }},
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request, project_uuid, item_id):
        item, err = self._get_item(request, project_uuid, item_id)
        if err:
            return err
        f = request.FILES.get('image')
        if not f:
            return StandardResponse.error(
                'No file provided. Send the image under the field name "image".',
                status_code=400,
            )
        # Type check by content-type header (browser sets this). Extension
        # is not authoritative — clients can lie about it.
        if getattr(f, 'content_type', None) not in _ALLOWED_IMAGE_TYPES:
            return StandardResponse.error(
                f'Unsupported image type. Allowed: JPEG, PNG, WebP.',
                status_code=400,
            )
        if f.size > _MAX_IMAGE_BYTES:
            return StandardResponse.error(
                f'Image too large ({f.size} bytes). Max size is 5 MB.',
                status_code=400,
            )
        item.image = f
        if request.user.is_authenticated:
            item.updated_by = request.user
        item.save(update_fields=['image', 'updated_by', 'updated_at'])
        return StandardResponse.success(
            {'id': item.id, 'image_url': item.image.url if item.image else None},
            'Product image uploaded.',
        )

    @extend_schema(summary='Delete product photo')
    def delete(self, request, project_uuid, item_id):
        item, err = self._get_item(request, project_uuid, item_id)
        if err:
            return err
        if item.image:
            item.image.delete(save=False)
        item.image = None
        if request.user.is_authenticated:
            item.updated_by = request.user
        item.save(update_fields=['image', 'updated_by', 'updated_at'])
        return StandardResponse.success({'id': item.id}, 'Product image cleared.')
