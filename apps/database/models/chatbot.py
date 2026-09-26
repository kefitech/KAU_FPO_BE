"""
Chatbot Knowledge Base Models.

Storage for the RAG knowledge the chatbot answers questions from. Each
entry is a small piece of help content (1–3 sentences) tagged with:
  - `audiences`: WHO can see this entry
  - `pages`:     glob patterns of routes where this entry is most relevant

Retrieval at request time is a Postgres FTS search filtered by the user's
audience, then the top few hits are handed to chatbot_service's extractive
QA model as context.

## Audience values

`audiences` is a JSON list of strings. Two special values plus any
`auth.Group.name` are accepted:

  - `'public'`  — visible to anonymous / not-logged-in users
  - `'all'`     — visible to any logged-in user (any role)
  - `'<group>'` — visible to users in that Django Group
                  (e.g. 'fpo_manager', 'super_admin', 'external_buyer',
                   'government', 'cbbo', 'expert', 'sub_admin')

**Design intent**: adding a new role/portal later requires zero code
change here. Whoever creates the new Group also tags relevant KB entries
with that group name in the admin UI. No migration, no enum bump.

The admin UI's dropdown builds its option list from
`Group.objects.values_list('name', flat=True)` at render time plus the
two special values above — so it stays in sync automatically.

Convention: all business models live under apps.database.models per this
project's rule (see CLAUDE.md § "Centralized Database App").
"""

from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector
from django.db import models

from apps.core.models.base import BaseModel


# Special (non-Group) audience tokens. Extend here only if you introduce
# another cross-cutting audience concept (e.g. 'admin_or_gov') — day-to-day
# per-role tagging uses Group names directly.
AUDIENCE_PUBLIC = 'public'   # anonymous, not logged in
AUDIENCE_ALL    = 'all'      # any logged-in user

SPECIAL_AUDIENCES = (AUDIENCE_PUBLIC, AUDIENCE_ALL)


class ChatKnowledgeEntry(BaseModel):
    """One RAG knowledge entry — a short help snippet the chatbot may quote."""

    topic = models.CharField(
        max_length=200,
        help_text="Short label for admin UI (e.g. 'FPO Registration', 'Reset Password')",
    )
    audiences = models.JSONField(
        default=list,
        help_text=(
            "List of audience tokens. Each token is either 'public', 'all', "
            "or a Django auth.Group name (e.g. 'fpo_manager', 'super_admin'). "
            "Adding a new portal role = create the Group + tag entries with "
            "its name here — no code change needed."
        ),
    )
    pages = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "Glob patterns of routes this entry is most relevant on — used "
            "as a retrieval boost, not a filter. Example: ['/fpo/register*']"
        ),
    )
    body_en = models.TextField(
        help_text="The answer text (English). Keep it 1–3 sentences and "
                  "concrete — the QA model quotes literal spans, so long "
                  "rambling entries produce worse answers.",
    )
    body_ml = models.TextField(
        blank=True, default='',
        help_text="Malayalam translation of body_en. Filled in Phase 3.",
    )
    keywords = models.TextField(
        blank=True, default='',
        help_text="Extra search terms not in the body — synonyms, misspellings, "
                  "alternate phrasings. Included in the FTS index.",
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Inactive entries are hidden from retrieval — use for "
                  "content that's outdated but you want to keep for history.",
    )
    display_order = models.IntegerField(
        default=0,
        help_text="Tiebreaker for equal-relevance retrievals. Lower = earlier.",
    )

    class Meta:
        verbose_name = 'Chatbot Knowledge Entry'
        verbose_name_plural = 'Chatbot Knowledge Entries'
        ordering = ['display_order', 'topic']
        indexes = [
            # Postgres GIN index over the searchable text for fast FTS.
            # Weights: topic (A) > keywords (B) > body (C) so the ranking
            # favors entries whose title matches the query.
            GinIndex(
                SearchVector('topic', weight='A', config='english'),
                SearchVector('keywords', weight='B', config='english'),
                SearchVector('body_en', weight='C', config='english'),
                name='chat_kb_search_idx',
            ),
        ]

    def __str__(self):
        return self.topic


# ─────────────────────────────────────────────────────────────────────────────
# Conversation history (Phase 3, 2026-09-25)
# ─────────────────────────────────────────────────────────────────────────────
# `ChatConversation` is one open session — anonymous callers own it via a
# random session_id kept in localStorage; authenticated callers own it via
# `user` FK. `ChatMessage` is one turn (user OR assistant). Together they
# let the widget show scrollback on mount and let the answer service pass
# prior turns to Gemini for multi-turn context.
#
# Retention: a Celery beat task purges anonymous conversations older than
# 30 days. Authenticated conversations are kept until the user deletes the
# account or asks for their data to be purged.

from django.contrib.auth import get_user_model
User = get_user_model()


class ChatConversation(BaseModel):
    """One chatbot session — a container for messages exchanged in a widget."""

    user = models.ForeignKey(
        User, on_delete=models.CASCADE,
        null=True, blank=True, related_name='chat_conversations',
        help_text='Null when the session is anonymous (public widget).',
    )
    session_id = models.CharField(
        max_length=64, db_index=True, default='',
        help_text='UUID from the FE widget. Kept in localStorage so a return '
                  'visit reuses the same conversation. Reset endpoint creates '
                  'a new session_id. Default empty just for the schema — the '
                  'API layer always writes a real UUID before saving.',
    )
    audience = models.CharField(
        max_length=32, blank=True, default='',
        help_text="'public' for anonymous, else the Django Group name we "
                  'served this session under. Denormalised for cheap admin '
                  'filtering.',
    )
    started_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Chatbot Conversation'
        verbose_name_plural = 'Chatbot Conversations'
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['user', '-started_at']),
            models.Index(fields=['session_id']),
        ]

    def __str__(self):
        who = self.user.username if self.user_id else f'anon:{self.session_id[:8]}'
        return f'chat({who}, started {self.started_at:%Y-%m-%d %H:%M})'


class ChatMessage(BaseModel):
    """One turn in a chat conversation — either from the user or the assistant."""

    class Role(models.TextChoices):
        USER      = 'user',      'User'
        ASSISTANT = 'assistant', 'Assistant'

    class Generator(models.TextChoices):
        # Which path produced the assistant reply. NULL/blank for user turns.
        GEMINI      = 'gemini',      'Gemini (RAG grounded)'
        EXTRACTIVE  = 'extractive',  'Extractive QA (fallback)'
        SMALL_TALK  = 'small_talk',  'Canned small-talk reply'
        NONE        = 'none',        'No context found — static fallback'

    conversation = models.ForeignKey(
        ChatConversation, on_delete=models.CASCADE, related_name='messages',
    )
    role       = models.CharField(max_length=10, choices=Role.choices)
    content    = models.TextField()
    source_ids = models.JSONField(
        default=list, blank=True,
        help_text='List of ChatKnowledgeEntry ids used as context. Empty for '
                  'user turns and small-talk replies.',
    )
    generator = models.CharField(
        max_length=20, choices=Generator.choices, blank=True, default='',
        help_text='Which generator produced this reply. Blank for user turns.',
    )
    confidence = models.FloatField(
        null=True, blank=True,
        help_text='Model / retrieval confidence 0-1. Null for user turns.',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Chatbot Message'
        verbose_name_plural = 'Chatbot Messages'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['conversation', 'created_at']),
        ]

    def __str__(self):
        preview = (self.content or '')[:60].replace('\n', ' ')
        return f'[{self.get_role_display()}] {preview}'
