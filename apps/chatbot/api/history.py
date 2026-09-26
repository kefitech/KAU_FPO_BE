"""
Chatbot — history + reset endpoints.

GET  /api/chatbot/history/?session_id=<id>
    Return the persisted messages of a ChatConversation so the widget
    can render scrollback on mount. Empty list if the session_id doesn't
    resolve or belongs to a different owner.

POST /api/chatbot/reset/
    End the current conversation and return a fresh session_id. The FE
    widget stores it in localStorage. No data is deleted — the old
    conversation stays for admin audit + is subject to the retention
    task (30 days for anonymous).

Both endpoints are AllowAny — session_id + auth-user ownership handle
the access check inside the helpers.

Author: Athul Gopan (Kefi Tech Solutions)
"""
from __future__ import annotations

import uuid

from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.core.utils.responses import StandardResponse
from apps.database.models import ChatConversation


@extend_schema(tags=['Chatbot'])
class ChatHistoryView(APIView):
    """GET the persisted messages of an existing conversation."""

    permission_classes = [AllowAny]

    @extend_schema(
        summary='Retrieve chat history for a session',
        description=(
            'Return every message in the ChatConversation matching '
            'session_id (subject to owner check). Widget mounts this to '
            'restore scrollback.'
        ),
        parameters=[
            OpenApiParameter(
                'session_id',
                description='UUID from the widget localStorage',
                required=True,
                type=str,
            ),
        ],
        responses={200: dict},
    )
    def get(self, request):
        session_id = (request.query_params.get('session_id') or '').strip()
        if not session_id:
            return StandardResponse.success(
                data={'session_id': '', 'messages': []},
                message='No session_id supplied — empty history.',
            )

        qs = ChatConversation.objects.filter(session_id=session_id)
        if request.user and request.user.is_authenticated:
            conv = qs.filter(user=request.user).first() \
                or qs.filter(user__isnull=True).first()
        else:
            conv = qs.filter(user__isnull=True).first()

        if not conv:
            return StandardResponse.success(
                data={'session_id': session_id, 'messages': []},
                message='No conversation found for this session — empty history.',
            )

        messages = [
            {
                'role':       m.role,
                'content':    m.content,
                'generator':  m.generator or '',
                'source_ids': m.source_ids or [],
                'confidence': m.confidence,
                'created_at': m.created_at.isoformat(),
            }
            for m in conv.messages.order_by('created_at')
        ]
        return StandardResponse.success(
            data={'session_id': session_id, 'messages': messages},
            message='History retrieved.',
        )


class _ResetRequestSerializer(serializers.Serializer):
    session_id = serializers.CharField(
        required=False, allow_blank=True, default='', max_length=64,
        help_text='Ignored today — reset simply mints a new session_id. '
                  'Provided for symmetry with the message endpoint.',
    )


@extend_schema(tags=['Chatbot'])
class ChatResetView(APIView):
    """POST to end the current conversation and get a fresh session_id."""

    permission_classes = [AllowAny]

    @extend_schema(
        summary='Reset the chat session',
        description=(
            'Returns a fresh session_id for the widget to store. The old '
            'conversation is NOT deleted — kept for admin audit + retention '
            'task cleanup (30 days for anonymous).'
        ),
        request=_ResetRequestSerializer,
        responses={
            200: inline_serializer(
                name='ChatResetResponse',
                fields={'session_id': serializers.CharField()},
            ),
        },
    )
    def post(self, request):
        # No DB mutation — this is the widget's cue to forget its localStorage
        # session_id and store the one we return. The old conversation and
        # its messages are kept as-is for admin audit.
        return StandardResponse.success(
            data={'session_id': uuid.uuid4().hex},
            message='Session reset.',
        )
