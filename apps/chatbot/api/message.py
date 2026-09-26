"""
POST /api/chatbot/message/ — the FE chat panel calls this on every user
message.

Flow:
  1. Determine the user's audience (Django Group name, or None for anon).
  2. Retrieve top-3 KB entries scoped to that audience + boosted by page.
  3. Ship {question, concatenated context} to chatbot_service /qa/answer.
  4. If confident, return the model's extracted span.
     If not, return a friendly fallback message that points the user to
     KAU support.

Public + authenticated both allowed (AllowAny). The `_resolve_role`
helper distinguishes them.
"""

from typing import List, Optional

from drf_spectacular.utils import OpenApiExample, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.core.utils.responses import StandardResponse
from apps.chatbot.services.gemini_answer import generate_answer as gemini_generate
from apps.chatbot.services.history import ensure_conversation, recent_turns, save_turn
from apps.chatbot.services.qa_client import ask as qa_ask
from apps.chatbot.services.retrieve import retrieve
from apps.chatbot.services.small_talk import handle_small_talk


# Priority list must stay in sync with apps.accounts.api.auth._get_user_role.
# When a user has multiple groups, this picks the one the KB is most
# likely to be tagged for.
_ROLE_PRIORITY = [
    'super_admin',
    'sub_admin',
    'fpo_manager',
    'government',
    'cbbo',
    'expert',
    'external_buyer',
    'viewer',
]


def _resolve_role(user) -> Optional[str]:
    """Pick the highest-priority Django Group name the user belongs to.

    Returns None for anonymous users -- callers must handle that as the
    'public' audience.
    """
    if not user or not user.is_authenticated:
        return None
    groups = set(user.groups.values_list('name', flat=True))
    for role in _ROLE_PRIORITY:
        if role in groups:
            return role
    return None


class _MessageRequestSerializer(serializers.Serializer):
    message = serializers.CharField(
        min_length=1,
        max_length=500,
        help_text="The user's question, natural language.",
    )
    current_path = serializers.CharField(
        required=False,
        allow_blank=True,
        default='',
        max_length=200,
        help_text="Route the user is currently on, e.g. '/fpo/dashboard'. "
                  "Used as a retrieval boost.",
    )
    session_id = serializers.CharField(
        required=False,
        allow_blank=True,
        default='',
        max_length=64,
        help_text="UUID from the widget's localStorage. Empty on the first "
                  "message of a new session — server assigns one and returns "
                  "it. Same session_id → same ChatConversation → multi-turn "
                  "context passed to Gemini.",
    )


class ChatMessageView(APIView):
    """POST /api/chatbot/message/ — answer a user's question (RAG + QA)."""

    permission_classes = [AllowAny]

    @extend_schema(
        tags=['Chatbot'],
        summary='Ask the chatbot',
        description=(
            "RAG-backed help assistant. Retrieves top-3 knowledge-base "
            "entries scoped to the user's role and current page, then "
            "extracts an answer span via chatbot_service's QA model."
        ),
        request=_MessageRequestSerializer,
        responses={
            200: inline_serializer(
                name='ChatbotMessageResponse',
                fields={
                    'reply':      serializers.CharField(),
                    'confident':  serializers.BooleanField(),
                    'confidence': serializers.FloatField(),
                    'sources':    serializers.ListField(child=serializers.DictField()),
                },
            ),
        },
        examples=[
            OpenApiExample(
                'Public user asks about registration',
                value={'message': 'How do I register my FPO?', 'current_path': '/'},
                request_only=True,
            ),
        ],
    )
    def post(self, request, *args, **kwargs):
        ser = _MessageRequestSerializer(data=request.data)
        if not ser.is_valid():
            return StandardResponse.error(
                'Invalid request.',
                errors=ser.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        message = ser.validated_data['message'].strip()
        current_path = ser.validated_data.get('current_path') or ''
        client_session_id = ser.validated_data.get('session_id') or ''
        user_role = _resolve_role(request.user)

        # Preferred language — used for both small-talk lookup below and
        # the Gemini prompt further down.
        #
        # Priority: the X-Language header set by the FE on every request
        # WINS, because it reflects what language the user is currently
        # reading on the page. The user profile's `preferred_language` is
        # only a fallback for the rare case where no header was sent
        # (e.g. direct API caller, curl). If we let the profile override
        # the header, a user whose account was created in Malayalam would
        # keep getting Malayalam replies even after switching the site to
        # English — that surprised testers, see 2026-09-26 bug report.
        header_lang = getattr(request, 'language', None)
        if header_lang:
            lang = header_lang
        else:
            lang = 'en'
            if request.user and request.user.is_authenticated:
                prof = getattr(request.user, 'profile', None)
                if prof and getattr(prof, 'preferred_language', None):
                    lang = prof.preferred_language

        # Resolve / create the ChatConversation this turn belongs to. The
        # helper handles session_id validation + auth ownership. Every turn
        # gets persisted so the widget can scroll back on reload.
        conversation = ensure_conversation(
            session_id=client_session_id,
            user=request.user,
            audience=user_role or 'public',
        )
        session_id = conversation.session_id
        save_turn(conversation, role='user', content=message)

        def _reply(reply_text, generator, sources=None, confidence=1.0, extra=None):
            """Persist the assistant turn + build the standard response."""
            save_turn(
                conversation,
                role='assistant',
                content=reply_text,
                generator=generator,
                source_ids=[s['id'] for s in (sources or [])],
                confidence=confidence,
            )
            payload = {
                'reply':      reply_text,
                'confident':  confidence >= 0.5,
                'confidence': round(confidence, 4),
                'sources':    sources or [],
                'generator':  generator,
                'session_id': session_id,
            }
            if extra:
                payload.update(extra)
            return StandardResponse.success(data=payload, message='Chatbot response.')

        # Small-talk (greetings / thanks / who-are-you / help). Handled at
        # the top of the flow — zero cost, sub-ms latency, avoids the
        # "no KB entries" fallback for a friendly "hi".
        canned = handle_small_talk(message, user_role=user_role, lang=lang)
        if canned:
            return _reply(canned, generator='small_talk')

        entries = retrieve(query=message, user_role=user_role, current_path=current_path)

        if not entries:
            return _reply(_fallback_reply(), generator='none', confidence=0.0)

        # Pull the last few turns so Gemini gets multi-turn context and can
        # answer "yes, and what about X?" style follow-ups. Excludes the
        # user turn we just saved (recent_turns is oldest-first).
        prior = recent_turns(conversation)
        # Drop the last item — that's the message we're currently answering.
        if prior and prior[-1]['role'] == 'user' and prior[-1]['content'] == message:
            prior = prior[:-1]

        # Primary path — Gemini via the shared LLM gateway. Returns None if
        # the service is disabled, over budget, or the call errors — in any
        # of those cases we fall through to the extractive QA fallback.
        gemini_result = gemini_generate(
            question=message,
            entries=entries,
            user=request.user,
            current_path=current_path,
            lang=lang,
            prior_turns=prior,
        )
        if gemini_result is not None:
            return _reply(
                gemini_result['text'],
                generator='gemini',
                sources=[{'topic': e.topic, 'id': e.id} for e in entries],
                extra={'model': gemini_result['model']},
            )

        # Fallback — extractive QA against the retrieved context. Same
        # behaviour as before Phase 2 — zero-hallucination literal span quote.
        context = '\n\n'.join(f'{e.topic}. {e.body_en}' for e in entries)
        qa = qa_ask(question=message, context=context)

        if qa['confident']:
            reply = qa['answer']
        else:
            # Low-confidence: fall back to the top-ranked entry's body_en
            # verbatim. Still grounded in retrieved KB (no hallucination)
            # and usually more useful than a bland fallback.
            reply = entries[0].body_en if entries else _fallback_reply()

        return _reply(
            reply,
            generator='extractive',
            sources=[{'topic': e.topic, 'id': e.id} for e in entries],
            confidence=qa['score'],
        )


def _fallback_reply() -> str:
    """Static message when we can't find anything useful.

    Post-UAT: swap for a translated version via TranslationService.
    """
    return (
        "I couldn't find an answer to that. Please rephrase your question, "
        "or contact KAU support at kau-fpo@kau.in for help."
    )
