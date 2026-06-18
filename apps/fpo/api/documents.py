"""
FPO Document Upload APIs
=========================
Base path: /api/fpo/me/documents/

Endpoints:
    POST   /api/fpo/me/documents/        — upload a document
    GET    /api/fpo/me/documents/        — list all uploaded documents
    DELETE /api/fpo/me/documents/{id}/   — soft delete (DRAFT only)

Rules (CLAUDE.md / SRS §3.1.3):
    - Required types: fpo_reg_cert, bank_details, signatory_id, pan_card
    - Optional types: gst_cert, annual_report, member_list, board_resolution, moa_aoa, other
    - Max size: 5 MB standard, 10 MB for member_list and annual_report
    - Allowed mime: PDF, JPG, PNG (XLSX also for member_list)
    - Only one active file per document_type — uploading again replaces previous
    - Delete only allowed in DRAFT status
"""

import magic

from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiExample
from rest_framework import serializers, status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.views import APIView

from apps.core.permissions.rbac import IsFPOManager
from apps.core.utils.constants import DocumentType, FPOStatus, REQUIRED_DOCUMENTS
from apps.core.utils.responses import StandardResponse
from apps.core.services.translation import t
from apps.core.services.audit import AuditService
from apps.core.models.generic import AuditLog
from apps.database.models.fpo import FPO, FPODocument


ALLOWED_MIME_TYPES = {
    'application/pdf',
    'image/jpeg',
    'image/png',
}

ALLOWED_MIME_MEMBER_LIST = ALLOWED_MIME_TYPES | {
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',  # xlsx
}


def _get_fpo_or_404(user, lang):
    try:
        return FPO.objects.get(primary_user=user), None
    except FPO.DoesNotExist:
        return None, StandardResponse.error(
            t('fpo.fpo_not_found', lang),
            status_code=status.HTTP_404_NOT_FOUND,
        )


class FPODocumentSerializer(serializers.ModelSerializer):
    document_type_display = serializers.CharField(
        source='get_document_type_display', read_only=True
    )
    file_url = serializers.SerializerMethodField()
    is_required = serializers.BooleanField(read_only=True)

    class Meta:
        model  = FPODocument
        fields = [
            'id', 'document_type', 'document_type_display',
            'file_url', 'file_size', 'mime_type',
            'is_required', 'is_verified', 'verified_at',
            'created_at',
        ]

    def get_file_url(self, obj):
        request = self.context.get('request')
        if obj.file and request:
            return request.build_absolute_uri(obj.file.url)
        return None


class DocumentUploadView(APIView):
    permission_classes = [IsFPOManager]
    parser_classes     = [MultiPartParser, FormParser]

    @extend_schema(
        tags=['FPO - Documents'],
        summary='Upload a document',
        description=(
            'Upload a document for the FPO registration. '
            'Send as `multipart/form-data` with `document_type` and `file` fields.\n\n'
            '**Required types** (all 4 must be uploaded before submission):\n'
            '`fpo_reg_cert`, `bank_details`, `signatory_id`, `pan_card`\n\n'
            '**Optional types**: `gst_cert`, `annual_report`, `member_list`, '
            '`board_resolution`, `moa_aoa`, `other`\n\n'
            '**Size limits**: 5 MB standard · 10 MB for `member_list` and `annual_report`\n\n'
            '**Allowed formats**: PDF, JPG, PNG (XLSX also allowed for `member_list`)\n\n'
            'Uploading the same `document_type` again soft-deletes the previous file and stores the new one.'
        ),
        request={
            'multipart/form-data': {
                'type': 'object',
                'properties': {
                    'document_type': {'type': 'string', 'example': 'pan_card'},
                    'file': {'type': 'string', 'format': 'binary'},
                },
                'required': ['document_type', 'file'],
            }
        },
        responses={201: FPODocumentSerializer},
    )
    def post(self, request):
        lang = request.language
        fpo, err = _get_fpo_or_404(request.user, lang)
        if err:
            return err

        if fpo.status != FPOStatus.DRAFT:
            return StandardResponse.error(
                t('fpo.cannot_edit_status', lang).format(status=fpo.status),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        document_type = request.data.get('document_type', '').strip()
        file          = request.FILES.get('file')

        # Validate document_type
        valid_types = [choice[0] for choice in DocumentType.choices]
        if not document_type or document_type not in valid_types:
            return StandardResponse.error(
                t('fpo.invalid_document_type', lang),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Validate file present
        if not file:
            return StandardResponse.error(
                t('fpo.document_file_required', lang),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Validate file size
        max_size = (
            FPODocument.MAX_SIZE_LARGE
            if document_type in FPODocument.LARGE_TYPES
            else FPODocument.MAX_SIZE_STANDARD
        )
        if file.size > max_size:
            limit_mb = max_size // (1024 * 1024)
            return StandardResponse.error(
                t('fpo.document_too_large', lang).format(limit=limit_mb),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Validate mime type via file content (not just extension)
        mime_type = magic.from_buffer(file.read(2048), mime=True)
        file.seek(0)

        allowed = (
            ALLOWED_MIME_MEMBER_LIST
            if document_type == DocumentType.MEMBER_LIST
            else ALLOWED_MIME_TYPES
        )
        if mime_type not in allowed:
            return StandardResponse.error(
                t('fpo.document_invalid_format', lang),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Soft-delete any previous file of same type
        FPODocument.objects.filter(
            fpo=fpo, document_type=document_type, is_deleted=False
        ).update(is_deleted=True)

        # Create new document record
        doc = FPODocument.objects.create(
            fpo           = fpo,
            document_type = document_type,
            file          = file,
            file_size     = file.size,
            mime_type     = mime_type,
            created_by    = request.user,
            updated_by    = request.user,
        )

        AuditService.log(
            user=request.user,
            action=AuditLog.Action.DOCUMENT_UPLOAD,
            instance=doc,
            request=request,
            changes={'document_type': document_type, 'file_size': file.size, 'mime_type': mime_type},
        )

        serializer = FPODocumentSerializer(doc, context={'request': request})
        return StandardResponse.success(
            data=serializer.data,
            message=t('fpo.document_uploaded', lang),
            status_code=status.HTTP_201_CREATED,
        )

    @extend_schema(
        tags=['FPO - Documents'],
        summary='List uploaded documents',
        description=(
            'Returns all active (non-deleted) documents for the current FPO. '
            'Shows which required types are still missing.'
        ),
        responses={200: FPODocumentSerializer(many=True)},
    )
    def get(self, request):
        lang = request.language
        fpo, err = _get_fpo_or_404(request.user, lang)
        if err:
            return err

        docs = FPODocument.objects.filter(fpo=fpo, is_deleted=False).order_by('document_type')
        serializer = FPODocumentSerializer(docs, many=True, context={'request': request})

        uploaded_types  = {d.document_type for d in docs}
        missing_required = [
            dt for dt in REQUIRED_DOCUMENTS if dt not in uploaded_types
        ]

        return StandardResponse.success(
            data={
                'documents':       serializer.data,
                'missing_required': missing_required,
                'ready_to_submit':  len(missing_required) == 0,
            }
        )


class DocumentDeleteView(APIView):
    permission_classes = [IsFPOManager]

    @extend_schema(
        tags=['FPO - Documents'],
        summary='Delete a document',
        description='Soft-delete a document. Only allowed while FPO is in DRAFT status.',
        responses={200: None, 400: None, 404: None},
    )
    def delete(self, request, doc_id):
        lang = request.language
        fpo, err = _get_fpo_or_404(request.user, lang)
        if err:
            return err

        if fpo.status != FPOStatus.DRAFT:
            return StandardResponse.error(
                t('fpo.cannot_edit_status', lang).format(status=fpo.status),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            doc = FPODocument.objects.get(id=doc_id, fpo=fpo, is_deleted=False)
        except FPODocument.DoesNotExist:
            return StandardResponse.error(
                t('fpo.document_not_found', lang),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        doc.is_deleted  = True
        doc.updated_by  = request.user
        doc.save(update_fields=['is_deleted', 'updated_by', 'updated_at'])

        AuditService.log(
            user=request.user,
            action=AuditLog.Action.DOCUMENT_DELETE,
            instance=doc,
            request=request,
            changes={'document_type': doc.document_type},
        )

        return StandardResponse.success(message=t('fpo.document_deleted', lang))
