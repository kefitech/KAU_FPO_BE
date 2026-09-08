"""
DPR Knowledge Base — Admin CRUD per KAU RCD A.2 (2026-09-02).

Every AI-generated paragraph must trace back to authoritative source entries
stored here. This module lets super_admins curate the KB: add entries from
KAU PoP publications, government schemes, Kefi Tech SOPs, statutory portals,
and AGMARKNET feeds; supersede outdated versions; deactivate incorrect
entries.

Access:
    Read  — any authenticated admin (sub_admin + super_admin).
    Write — super_admin only (IsSuperAdminOrReadOnly).
    Audit — every mutation writes AuditLog action=DPR_KB_CHANGE with
            {op, entry_id, source, title, changes}.

Endpoints (mounted under /api/admin/dpr/knowledge/):
    GET    /                     — list + filter (source_type, language, section,
                                    commodity, component, tag, is_active, q text search)
    POST   /                     — create entry
    GET    /<pk>/                — retrieve
    PATCH  /<pk>/                — update
    DELETE /<pk>/                — hard-delete (rare — usually supersede instead)
    POST   /<pk>/deactivate/     — set is_active=False (keep for traceability)
    POST   /<pk>/supersede/      — attach a superseded_by → old row deactivated
                                    (see model.save() auto-hook), new row created

The list endpoint deliberately supports flexible search — the KB grows to
hundreds of rows and the admin UI needs to find entries fast.

Author: Athul Gopan (Kefi Tech Solutions)
"""
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.models.generic import AuditLog
from apps.core.permissions.rbac import IsSuperAdminOrReadOnly
from apps.core.utils.pagination import StandardPagination
from apps.core.utils.responses import StandardResponse
from apps.database.models import DPRKnowledgeEntry


# ─────────────────────────────────────────────────────────────────────────────
# Serializers
# ─────────────────────────────────────────────────────────────────────────────

class KnowledgeEntryListSerializer(serializers.ModelSerializer):
    """Compact shape for the admin list view — no full content dump."""

    source_type_display = serializers.CharField(source='get_source_type_display', read_only=True)
    commodity_count = serializers.SerializerMethodField()
    component_count = serializers.SerializerMethodField()
    business_type_count = serializers.SerializerMethodField()
    updated_by_email = serializers.SerializerMethodField()

    class Meta:
        model = DPRKnowledgeEntry
        fields = (
            'id',
            'source_type', 'source_type_display', 'source_name', 'source_url', 'source_version',
            'title', 'language',
            'section_keys', 'tags',
            'commodity_count', 'component_count', 'business_type_count',
            'is_active', 'superseded_by',
            'ingested_at', 'updated_at', 'updated_by_email',
        )
        read_only_fields = fields

    def get_commodity_count(self, obj):
        return obj.commodities.count()

    def get_component_count(self, obj):
        return obj.components.count()

    def get_business_type_count(self, obj):
        return obj.business_types.count()

    def get_updated_by_email(self, obj):
        return obj.updated_by.email if obj.updated_by_id else None


class KnowledgeEntryDetailSerializer(serializers.ModelSerializer):
    """Full read/write shape. IDs used for M2M writes; nested labels for read display."""

    source_type_display = serializers.CharField(source='get_source_type_display', read_only=True)
    commodity_labels = serializers.SerializerMethodField(read_only=True)
    component_labels = serializers.SerializerMethodField(read_only=True)
    business_type_labels = serializers.SerializerMethodField(read_only=True)
    updated_by_email = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = DPRKnowledgeEntry
        fields = (
            'id',
            'source_type', 'source_type_display', 'source_name', 'source_url', 'source_version',
            'title', 'content', 'language',
            'commodities', 'commodity_labels',
            'components', 'component_labels',
            'business_types', 'business_type_labels',
            'section_keys', 'tags',
            'is_active', 'superseded_by',
            'ingested_at', 'created_at', 'updated_at', 'updated_by_email',
        )
        read_only_fields = (
            'id', 'source_type_display', 'commodity_labels', 'component_labels',
            'business_type_labels', 'ingested_at', 'created_at', 'updated_at',
            'updated_by_email',
        )

    def get_commodity_labels(self, obj):
        # MasterLookup exposes get_name() for translation-backed display names
        return [{'id': c.id, 'name': c.get_name('en')} for c in obj.commodities.all()]

    def get_component_labels(self, obj):
        return [{'id': c.id, 'name': c.get_name('en')} for c in obj.components.all()]

    def get_business_type_labels(self, obj):
        return [{'id': b.id, 'name': b.get_name('en')} for b in obj.business_types.all()]

    def get_updated_by_email(self, obj):
        return obj.updated_by.email if obj.updated_by_id else None


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _audit(user, op: str, entry: DPRKnowledgeEntry, extra: dict | None = None):
    """Write an AuditLog row for a KB mutation.

    `op` is one of: create, update, deactivate, supersede, delete.
    """
    changes = {
        'op': op,
        'entry_id': entry.id,
        'source_type': entry.source_type,
        'source_name': entry.source_name,
        'title': entry.title,
    }
    if extra:
        changes.update(extra)
    AuditLog.objects.create(
        user=user,
        action=AuditLog.Action.DPR_KB_CHANGE,
        object_repr=str(entry)[:200],
        changes=changes,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Views
# ─────────────────────────────────────────────────────────────────────────────

@extend_schema(tags=['Admin — DPR Knowledge Base'])
class KnowledgeListCreateView(APIView):
    """List + filter + search KB entries; create new entries (super_admin)."""

    permission_classes = [IsAuthenticated, IsSuperAdminOrReadOnly]

    @extend_schema(
        summary='List KB entries',
        parameters=[
            OpenApiParameter('source_type', str, description='Filter by source_type value'),
            OpenApiParameter('language', str, description='Filter by language code'),
            OpenApiParameter('section', str, description='Filter to entries relevant to this DPR section key'),
            OpenApiParameter('commodity', int, description='Filter by commodity MasterLookup id'),
            OpenApiParameter('component', int, description='Filter by DPRComponent id'),
            OpenApiParameter('tag', str, description='Filter by tag string (exact match inside tags JSON)'),
            OpenApiParameter('is_active', bool, description='Filter by active flag'),
            OpenApiParameter('q', str, description='Full-text search across title, content, source_name'),
        ],
    )
    def get(self, request):
        qs = DPRKnowledgeEntry.objects.all().prefetch_related(
            'commodities', 'components', 'business_types',
        )

        qp = request.query_params
        if qp.get('source_type'):
            qs = qs.filter(source_type=qp['source_type'])
        if qp.get('language'):
            qs = qs.filter(language=qp['language'])
        if qp.get('section'):
            # Section filter matches either universal (empty) or containing key
            from django.db.models import Q
            qs = qs.filter(Q(section_keys__contains=[qp['section']]) | Q(section_keys=[]))
        if qp.get('commodity'):
            qs = qs.filter(commodities__id=qp['commodity'])
        if qp.get('component'):
            qs = qs.filter(components__id=qp['component'])
        if qp.get('tag'):
            qs = qs.filter(tags__contains=[qp['tag']])
        if qp.get('is_active') is not None and qp.get('is_active') != '':
            qs = qs.filter(is_active=qp['is_active'].lower() in ('1', 'true', 'yes'))
        if qp.get('q'):
            from django.db.models import Q
            q = qp['q']
            qs = qs.filter(Q(title__icontains=q) | Q(content__icontains=q) | Q(source_name__icontains=q))

        # M2M filters can produce duplicates — always distinct
        qs = qs.distinct().order_by('-ingested_at', '-id')

        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        ser = KnowledgeEntryListSerializer(page, many=True)
        return paginator.get_paginated_response(ser.data)

    @extend_schema(summary='Create a KB entry', request=KnowledgeEntryDetailSerializer, responses=KnowledgeEntryDetailSerializer)
    def post(self, request):
        ser = KnowledgeEntryDetailSerializer(data=request.data)
        if not ser.is_valid():
            return StandardResponse.error(ser.errors, status_code=400)
        entry = ser.save(created_by=request.user, updated_by=request.user)
        _audit(request.user, 'create', entry)
        return StandardResponse.success(
            KnowledgeEntryDetailSerializer(entry).data,
            'KB entry created',
            status_code=201,
        )


@extend_schema(tags=['Admin — DPR Knowledge Base'])
class KnowledgeDetailView(APIView):
    """Retrieve / update / delete a single KB entry."""

    permission_classes = [IsAuthenticated, IsSuperAdminOrReadOnly]

    def _get(self, pk):
        try:
            return DPRKnowledgeEntry.objects.get(pk=pk), None
        except DPRKnowledgeEntry.DoesNotExist:
            return None, StandardResponse.error('KB entry not found', status_code=404)

    def get(self, request, pk):
        obj, err = self._get(pk)
        if err:
            return err
        return StandardResponse.success(KnowledgeEntryDetailSerializer(obj).data, 'Retrieved')

    def patch(self, request, pk):
        obj, err = self._get(pk)
        if err:
            return err
        # Snapshot key fields before mutation so the audit row can show diff
        before = {'title': obj.title, 'is_active': obj.is_active}
        ser = KnowledgeEntryDetailSerializer(obj, data=request.data, partial=True)
        if not ser.is_valid():
            return StandardResponse.error(ser.errors, status_code=400)
        entry = ser.save(updated_by=request.user)
        _audit(request.user, 'update', entry, extra={'changed_fields': list(request.data.keys()), 'before': before})
        return StandardResponse.success(KnowledgeEntryDetailSerializer(entry).data, 'KB entry updated')

    def delete(self, request, pk):
        obj, err = self._get(pk)
        if err:
            return err
        # Snapshot before delete — id becomes None after obj.delete()
        _audit(request.user, 'delete', obj)
        obj.delete()
        return StandardResponse.success(None, 'KB entry deleted')


@extend_schema(tags=['Admin — DPR Knowledge Base'])
class KnowledgeDeactivateView(APIView):
    """Soft-deactivate — flip is_active=False without deleting.

    Preferred over DELETE when there's a chance existing AI narratives cite
    this entry: they stay traceable via the id.
    """

    permission_classes = [IsAuthenticated, IsSuperAdminOrReadOnly]

    def post(self, request, pk):
        try:
            entry = DPRKnowledgeEntry.objects.get(pk=pk)
        except DPRKnowledgeEntry.DoesNotExist:
            return StandardResponse.error('KB entry not found', status_code=404)
        if not entry.is_active:
            return StandardResponse.success(
                KnowledgeEntryDetailSerializer(entry).data,
                'KB entry already inactive',
            )
        entry.is_active = False
        entry.updated_by = request.user
        entry.save(update_fields=['is_active', 'updated_by', 'updated_at'])
        _audit(request.user, 'deactivate', entry)
        return StandardResponse.success(
            KnowledgeEntryDetailSerializer(entry).data,
            'KB entry deactivated',
        )


@extend_schema(tags=['Admin — DPR Knowledge Base'])
class KnowledgeSupersedeView(APIView):
    """Create a new entry as a superseded version of an existing one.

    Request body: same shape as KnowledgeEntryDetailSerializer (the new
    entry's data). The old entry's `superseded_by` FK is set to the new
    entry, which (via model.save()) auto-flips old.is_active=False.
    """

    permission_classes = [IsAuthenticated, IsSuperAdminOrReadOnly]

    def post(self, request, pk):
        try:
            old = DPRKnowledgeEntry.objects.get(pk=pk)
        except DPRKnowledgeEntry.DoesNotExist:
            return StandardResponse.error('KB entry not found', status_code=404)
        ser = KnowledgeEntryDetailSerializer(data=request.data)
        if not ser.is_valid():
            return StandardResponse.error(ser.errors, status_code=400)
        new = ser.save(created_by=request.user, updated_by=request.user)
        old.superseded_by = new
        old.updated_by = request.user
        old.save()  # save() hook flips old.is_active=False
        _audit(request.user, 'supersede', new, extra={'supersedes_id': old.id})
        return StandardResponse.success(
            KnowledgeEntryDetailSerializer(new).data,
            f'KB entry #{old.id} superseded by new entry #{new.id}',
            status_code=201,
        )
