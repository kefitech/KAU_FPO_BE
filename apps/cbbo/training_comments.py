"""
Training Session Comments — shared by the three training APIs.

Used by:
    apps/accounts/api/admin/applications.py  — super admin / sub-admin add + read
    apps/cbbo/api/training.py                — CBBO officer reads
    apps/government/api/training.py          — government official reads

KAU admins comment from the Training tab on an FPO application; the CBBO
officer or government official who recorded the session sees those comments
on their own training page. One serializer keeps all three responses identical.

Unread tracking (CBBO + government tables): a comment is unread for a user
until they open the session, which records `last_read_at` for them.
"""
from django.utils import timezone
from rest_framework import serializers

from apps.core.permissions.fpo_scope import get_sub_admin_district, is_super_admin
from apps.core.utils.constants import get_district_name
from apps.database.models.cbbo import TrainingSessionComment, TrainingSessionCommentRead


def admin_designation(user):
    """'Super Admin', or 'Sub-Admin, <district>' — snapshotted onto each comment."""
    if is_super_admin(user):
        return 'Super Admin'
    district = get_sub_admin_district(user)
    return f'Sub-Admin, {get_district_name(district)}' if district else 'Sub-Admin'


class TrainingSessionCommentSerializer(serializers.ModelSerializer):
    class Meta:
        model  = TrainingSessionComment
        fields = ['id', 'comment', 'author_name', 'author_designation', 'created_at', 'edited_at']
        read_only_fields = fields


def comment_read_map(user, sessions):
    """{session_id: last_read_at} for `sessions` (one list page) — a single query.

    Pass as serializer context `comment_reads`; list serializers use it for
    `has_unread_comments`.
    """
    return dict(
        TrainingSessionCommentRead.objects
        .filter(user=user, session_id__in=[s.id for s in sessions])
        .values_list('session_id', 'last_read_at')
    )


def has_unread_comments(session, read_map):
    """True if any comment was posted or edited after the user's last read.

    Needs `admin_comments` prefetched.
    """
    last_read = read_map.get(session.id)
    return any(
        last_read is None or (c.edited_at or c.created_at) > last_read
        for c in session.admin_comments.all()
    )


def mark_comments_read(user, session):
    TrainingSessionCommentRead.objects.update_or_create(
        session=session, user=user, defaults={'last_read_at': timezone.now()},
    )
