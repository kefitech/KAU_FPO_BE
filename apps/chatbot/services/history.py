"""
Chatbot — conversation history helpers.

Three tiny helpers used by the message endpoint:
  * ensure_conversation() — session_id resolution + auth precedence
  * save_turn()           — persist one user or assistant message
  * recent_turns()        — last N turns for Gemini multi-turn context

Session ownership rules:
  * If session_id is passed AND matches an existing ChatConversation:
      - For authenticated user: reuse only if the conversation belongs to
        this user (or is orphan — anonymous → user upgrade).
      - For anonymous: reuse only if the conversation is also anonymous.
    → Guards against a leaked session_id being replayed to hijack history.
  * If session_id is empty or doesn't resolve: create a fresh conversation.

Author: Athul Gopan (Kefi Tech Solutions)
"""
from __future__ import annotations

import uuid
from typing import List, Optional

from apps.database.models import ChatConversation, ChatMessage


# Number of previous turns to include in the Gemini prompt. 6 = 3 exchanges;
# balances context quality vs prompt size / cost. Bump if UAT shows the bot
# forgets recent context; halve if budget bites.
_HISTORY_WINDOW = 6


def ensure_conversation(
    session_id: str,
    user,
    audience: str,
) -> ChatConversation:
    """Get an existing conversation matching session_id + owner, or create.

    Returns a saved ChatConversation. The caller should use its .session_id
    (server may have generated a fresh one) when responding to the FE.
    """
    is_auth = bool(user and user.is_authenticated)

    if session_id:
        qs = ChatConversation.objects.filter(session_id=session_id)
        if is_auth:
            # Authenticated user — accept an existing conversation only when
            # they own it, OR when it's anonymous and we're upgrading it.
            existing = qs.filter(user=user).first() or qs.filter(user__isnull=True).first()
            if existing:
                if existing.user_id is None:
                    existing.user = user
                    existing.audience = audience
                    existing.save(update_fields=['user', 'audience', 'updated_at'])
                return existing
        else:
            # Anonymous — accept only if the stored session is also anonymous.
            existing = qs.filter(user__isnull=True).first()
            if existing:
                return existing

    # Nothing matched — start a fresh session.
    return ChatConversation.objects.create(
        user=user if is_auth else None,
        session_id=session_id or uuid.uuid4().hex,
        audience=audience,
    )


def save_turn(
    conversation: ChatConversation,
    role: str,
    content: str,
    generator: str = '',
    source_ids: Optional[list] = None,
    confidence: Optional[float] = None,
) -> ChatMessage:
    """Persist one message turn. `role` must be 'user' or 'assistant'."""
    return ChatMessage.objects.create(
        conversation=conversation,
        role=role,
        content=content,
        generator=generator or '',
        source_ids=source_ids or [],
        confidence=confidence,
    )


def recent_turns(
    conversation: ChatConversation,
    limit: int = _HISTORY_WINDOW,
) -> List[dict]:
    """Return the last `limit` message turns, oldest first.

    Shape: [{'role': 'user' | 'assistant', 'content': str}, ...]
    Passed straight to the Gemini prompt as multi-turn context.
    """
    qs = conversation.messages.order_by('-created_at')[:limit]
    return [
        {'role': m.role, 'content': m.content}
        for m in reversed(list(qs))
    ]
