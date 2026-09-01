from rest_framework import serializers

from apps.database.models.chat import ChatMessage


class ChatConversationOutputSerializer(serializers.Serializer):
    """Response shape for POST /api/chat/conversations/."""

    id = serializers.UUIDField()
    language = serializers.CharField()
    started_at = serializers.DateTimeField()


class ChatMessageInputSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=4000, allow_blank=False)


class ChatMessageOutputSerializer(serializers.Serializer):
    """Response shape for POST /api/chat/message/."""

    conversation_id = serializers.UUIDField()
    role = serializers.CharField()
    content = serializers.CharField()
    claude_model = serializers.CharField()
    tokens_used = serializers.IntegerField()
    created_at = serializers.DateTimeField()


class ChatHistoryMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ["id", "role", "content", "claude_model", "tokens_used", "created_at"]
        read_only_fields = fields