from django.urls import path

from apps.chatbot.api.message import ChatMessageView


app_name = 'chatbot'

urlpatterns = [
    path('message/', ChatMessageView.as_view(), name='chatbot-message'),
]
