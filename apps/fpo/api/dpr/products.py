"""
DPR §2.3.5 Proposed Products and Services — section endpoints.

Routes:
    GET   /projects/<uuid>/sections/products/
    PATCH /projects/<uuid>/sections/products/
    GET   /projects/<uuid>/sections/products/readiness/
"""

from drf_spectacular.utils import extend_schema, OpenApiTypes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.utils.responses import StandardResponse
from apps.database.models import DPRSectionProducts, DPRProductItem
from apps.fpo.services.dpr.products_validators import validate_section

from .projects import get_project_or_error
from .serializers import DPRSectionProductsSerializer

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

    @extend_schema(summary='Retrieve Products & Services section')
    def get(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        section = _get_or_create_section(project, request.user)
        data = DPRSectionProductsSerializer(section, context={'request': request}).data
        return StandardResponse.success(data, 'Section retrieved')

    @extend_schema(summary='Update Products & Services (full-replace items list)')
    def patch(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        section = _get_or_create_section(project, request.user)
        ser = DPRSectionProductsSerializer(
            section, data=request.data, partial=True, context={'request': request},
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
