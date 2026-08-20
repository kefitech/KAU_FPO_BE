"""
AI Chatbot Models — P2-10

FPO Primary and Secondary users only — SRS §3.2.9.
Claude API key stored in ExternalAPISettings (service_name='claude').
Full conversation history sent to Claude on each message.
"""
from django.contrib.auth.models import User
from django.db import models
from apps.core.models.base import BaseModel, TimeStampedModel


class ChatConversation(BaseModel):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='chat_conversations'
    )
    language = models.CharField(max_length=10, default='en')
    started_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Chat Conversation'
        verbose_name_plural = 'Chat Conversations'
        ordering = ['-started_at']

    def __str__(self):
        return f"{self.user} — {self.started_at:%Y-%m-%d %H:%M}"


class ChatMessage(TimeStampedModel):
    conversation = models.ForeignKey(
        ChatConversation, on_delete=models.CASCADE, related_name='messages'
    )
    role = models.CharField(
        max_length=20,
        choices=[('user', 'User'), ('assistant', 'Assistant')]
    )
    content = models.TextField()
    claude_model = models.CharField(
        max_length=100, blank=True,
        help_text='e.g. claude-sonnet-4-6'
    )
    tokens_used = models.IntegerField(
        default=0,
        help_text='Tracked for admin cost monitoring'
    )

    class Meta:
        verbose_name = 'Chat Message'
        verbose_name_plural = 'Chat Messages'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.role} — {self.conversation}"
