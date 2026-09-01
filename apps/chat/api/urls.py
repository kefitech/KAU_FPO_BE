from django.urls import path

from apps.chat.api.chatbot import (
    ChatConversationView,
    ChatHistoryView,
    ChatMessageView,
    ChatMetricsView,
)

app_name = "chat"

urlpatterns = [
    path("chat/conversations/", ChatConversationView.as_view(), name="chat-conversations"),
    path("chat/message/", ChatMessageView.as_view(), name="chat-message"),
    path("chat/history/", ChatHistoryView.as_view(), name="chat-history"),
    path("admin/chat/metrics/", ChatMetricsView.as_view(), name="chat-metrics"),
]