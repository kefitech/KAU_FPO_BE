from django.urls import path

from apps.chatbot.api.history import ChatHistoryView, ChatResetView
from apps.chatbot.api.message import ChatMessageView


app_name = 'chatbot'

urlpatterns = [
    path('message/', ChatMessageView.as_view(), name='chatbot-message'),
    path('history/', ChatHistoryView.as_view(), name='chatbot-history'),
    path('reset/',   ChatResetView.as_view(),   name='chatbot-reset'),
]
