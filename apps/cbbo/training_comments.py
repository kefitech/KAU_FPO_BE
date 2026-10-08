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

A new comment also sends the recorder an in-app notification
(`training_comment_added`) that opens the session on their training page.
"""
import logging

from django.utils import timezone
from django.utils.html import escape
from django.utils.text import Truncator
from rest_framework import serializers

from apps.core.permissions.fpo_scope import get_sub_admin_district, is_super_admin
from apps.core.utils.constants import get_district_name
from apps.database.models.cbbo import TrainingSessionComment, TrainingSessionCommentRead
from apps.database.models.government import GovernmentOfficialProfile

logger = logging.getLogger(__name__)

TRAINING_COMMENT_ADDED = 'training_comment_added'


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


def notify_comment_added(comment):
    """In-app alert to whoever recorded the session — a CBBO officer or a
    government official. The link opens the session on their own training page.
    Never raises: a failed notification must not fail the comment."""
    from apps.notifications.services import send_notification

    session  = comment.session
    recorder = session.cbbo
    if not recorder or not recorder.is_active:
        return
    is_govt = GovernmentOfficialProfile.objects.filter(user=recorder).exists()
    portal  = 'government' if is_govt else 'cbbo'
    try:
        send_notification(
            user=recorder,
            code=TRAINING_COMMENT_ADDED,
            channel='in_app',
            # In-app bodies render as HTML and the template engine substitutes verbatim.
            context={
                'author_name':        escape(comment.author_name),
                'author_designation': escape(comment.author_designation),
                'topic':              escape(session.topic),
                'fpo_name':           escape(session.fpo.name),
                'date':               str(session.date),
                'comment':            escape(Truncator(comment.comment).chars(160)),
                'link':               f'/{portal}/training?session={session.id}',
                'session_id':         session.id,
            },
        )
    except Exception:
        logger.exception('notify_comment_added: failed for comment %s', comment.pk)
