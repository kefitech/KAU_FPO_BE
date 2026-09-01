"""
Views for P2-10: AI Chatbot -- skeleton build (worksheet tasks #12-#15).

Endpoints:
  POST   /api/chat/conversations/    -> ChatConversationView (FPO only) [task 13]
  POST   /api/chat/message/          -> ChatMessageView      (FPO only) [task 13]
  GET    /api/chat/history/          -> ChatHistoryView       (FPO only) [task 13]
  DELETE /api/chat/history/          -> ChatHistoryView       (FPO only)
  GET    /api/admin/chat/metrics/    -> ChatMetricsView       (Super Admin only)

Task #14: when Claude isn't configured yet, ChatMessageView still returns a
normal 200 with a mock assistant reply (see services.get_assistant_reply) --
this is intentional skeleton behavior, not an error case. A 503 is only
returned if Claude IS configured but the live call itself fails.
"""
from datetime import timedelta

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions.rbac import IsFPOManager, IsSuperAdmin
from apps.chat.api.serializers import (
    ChatConversationOutputSerializer,
    ChatHistoryMessageSerializer,
    ChatMessageInputSerializer,
    ChatMessageOutputSerializer,
)
from apps.chat.api.services import ChatServiceUnavailable, get_assistant_reply
from apps.database.models.chat import ChatConversation, ChatMessage

DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES = {"en", "ml"}


def _get_or_create_conversation(user, language: str) -> ChatConversation:
    """
    One ongoing conversation per user (per spec: "conversation history
    stored per user"). Reuses the most recent conversation; updates its
    language if the user switches via X-Language.
    """
    conversation = (
        ChatConversation.objects.filter(user=user).order_by("-started_at").first()
    )
    if conversation is None:
        conversation = ChatConversation.objects.create(user=user, language=language)
    elif conversation.language != language:
        conversation.language = language
        conversation.save(update_fields=["language"])
    return conversation


class ChatConversationView(APIView):
    """
    POST /api/chat/conversations/ -- explicitly start a new conversation.
    """

    permission_classes = [IsAuthenticated, IsFPOManager]

    @extend_schema(tags=["Chat"], responses=ChatConversationOutputSerializer)
    def post(self, request):
        language = request.headers.get("X-Language", DEFAULT_LANGUAGE).lower()
        if language not in SUPPORTED_LANGUAGES:
            language = DEFAULT_LANGUAGE

        conversation = ChatConversation.objects.create(
            user=request.user, language=language
        )
        output = ChatConversationOutputSerializer(
            {
                "id": conversation.id,
                "language": conversation.language,
                "started_at": conversation.started_at,
            }
        )
        return Response(output.data, status=status.HTTP_201_CREATED)


class ChatMessageView(APIView):
    """POST /api/chat/message/ -- send a message, get an AI response (or the
    task #14 mock reply if Claude isn't configured yet)."""

    permission_classes = [IsFPOManager]

    @extend_schema(tags=["Chat"], request=ChatMessageInputSerializer, responses=ChatMessageOutputSerializer)
    def post(self, request):
        input_serializer = ChatMessageInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        user_message = input_serializer.validated_data["message"]

        language = request.headers.get("X-Language", DEFAULT_LANGUAGE).lower()
        if language not in SUPPORTED_LANGUAGES:
            language = DEFAULT_LANGUAGE

        conversation = _get_or_create_conversation(request.user, language)

        ChatMessage.objects.create(
            conversation=conversation, role="user", content=user_message
        )

        history = list(
            conversation.messages.order_by("created_at").values("role", "content")
        )

        try:
            result = get_assistant_reply(
                user=request.user,
                language=language,
                conversation_history=history[:-1],
                message=user_message,
                reference_id=str(conversation.id),
            )
        except ChatServiceUnavailable:
            return Response(
                {
                    "detail": (
                        "The AI assistant is temporarily unavailable. "
                        "Please try again later, or contact your admin if "
                        "this persists."
                    )
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        assistant_message = ChatMessage.objects.create(
            conversation=conversation,
            role="assistant",
            content=result["content"],
            claude_model=result["claude_model"],
            tokens_used=result["tokens_used"],
        )

        output = ChatMessageOutputSerializer(
            {
                "conversation_id": conversation.id,
                "role": assistant_message.role,
                "content": assistant_message.content,
                "claude_model": assistant_message.claude_model,
                "tokens_used": assistant_message.tokens_used,
                "created_at": assistant_message.created_at,
            }
        )
        return Response(output.data, status=status.HTTP_200_OK)


class ChatHistoryView(APIView):
    """
    GET    /api/chat/history/ -- return FPO's past messages in order.
    DELETE /api/chat/history/ -- clear all conversation history for the user.
    """

    permission_classes = [IsAuthenticated, IsFPOManager]

    @extend_schema(tags=["Chat"], responses=ChatHistoryMessageSerializer(many=True))
    def get(self, request):
        messages = ChatMessage.objects.filter(
            conversation__user=request.user
        ).order_by("created_at")
        serializer = ChatHistoryMessageSerializer(messages, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(tags=["Chat"])
    def delete(self, request):
        ChatConversation.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ChatMetricsView(APIView):
    """
    GET /api/admin/chat/metrics/ -- Super Admin only.
    """

    permission_classes = [IsAuthenticated, IsSuperAdmin]

    @extend_schema(tags=["Chat"])
    def get(self, request):
        try:
            days = int(request.query_params.get("days", 30))
        except ValueError:
            days = 30
        since = timezone.now() - timedelta(days=days)

        daily = (
            ChatMessage.objects.filter(created_at__gte=since, role="assistant")
            .annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(message_count=Count("id"), tokens_used=Sum("tokens_used"))
            .order_by("day")
        )

        totals = ChatMessage.objects.filter(
            created_at__gte=since, role="assistant"
        ).aggregate(
            total_messages=Count("id"),
            total_tokens=Sum("tokens_used"),
        )

        active_users = (
            ChatConversation.objects.filter(started_at__gte=since)
            .values("user")
            .distinct()
            .count()
        )

        return Response(
            {
                "period_days": days,
                "total_messages": totals["total_messages"] or 0,
                "total_tokens": totals["total_tokens"] or 0,
                "active_users": active_users,
                "daily_breakdown": list(daily),
            },
            status=status.HTTP_200_OK,
        )