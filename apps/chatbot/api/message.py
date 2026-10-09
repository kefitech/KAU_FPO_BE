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
from apps.chatbot.services.fallback_contacts import augment_reply as augment_fallback
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
    district = serializers.CharField(
        required=False,
        allow_blank=True,
        default='',
        max_length=5,
        help_text="Optional district code hint (e.g. 'TSR'). Used only for the "
                  "chatbot fallback message when we can't infer the district "
                  "from the caller's profile — mostly relevant for anonymous "
                  "users on the public widget.",
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
        district_hint = (ser.validated_data.get('district') or '').strip().upper()
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
            """Persist the assistant turn + build the standard response.

            KAU suggestion #2 — if the reply looks like a "can't help / off-topic"
            refusal, append the caller's district KVK + sub-admin contact info so
            the user has somewhere to go next.
            """
            reply_text = augment_fallback(reply_text, request.user, district_hint, lang, user_message=message)
            # BUG-15 — refusals shouldn't carry sources. The retrieved entries
            # didn't actually answer the question, so citing them is noise
            # (testers reported seeing e.g. "How to register an FPO" sources
            # attached to a feature-flag refusal). Strip after augment_fallback
            # so the detector sees the final text, including intent-aware
            # rewrites. Also drop sources on explicit low-confidence replies.
            from apps.chatbot.services.fallback_contacts import _looks_like_refusal
            if _looks_like_refusal(reply_text) or confidence < 0.5:
                sources = []
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

        # Pull the last few turns so Gemini gets multi-turn context and can
        # answer "yes, and what about X?" style follow-ups. Excludes the
        # user turn we just saved (recent_turns is oldest-first).
        prior = recent_turns(conversation)
        # Drop the last item — that's the message we're currently answering.
        if prior and prior[-1]['role'] == 'user' and prior[-1]['content'] == message:
            prior = prior[:-1]

        # KAU 2026-09-27 tester feedback: pronoun follow-ups ("what documents
        # do I need for that?") were retrieving generic entries because the
        # search used ONLY the short current message. Fix — for short + likely
        # elliptical follow-ups, append the previous user turn to the search
        # query so FTS pulls topically-relevant entries. Kept as a soft
        # heuristic: only fires when the current message looks like a
        # follow-up (short + contains a pronoun / connector) AND we have a
        # prior user turn to anchor on.
        search_query = message
        follow_up_markers = (
            'that', 'this', 'it', 'those', 'these', 'the same',
            'and ', 'also', 'what about',
        )
        looks_like_followup = (
            len(message.split()) <= 12
            and any(m in message.lower() for m in follow_up_markers)
        )
        if looks_like_followup and prior:
            last_user = next(
                (t['content'] for t in reversed(prior) if t['role'] == 'user'),
                '',
            )
            if last_user:
                search_query = f'{message} {last_user}'

        entries = retrieve(
            query=search_query,
            user_role=user_role,
            current_path=current_path,
        )

        if not entries:
            return _reply(_fallback_reply(lang), generator='none', confidence=0.0)

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
            user_role=user_role or 'public',
        )
        if gemini_result is not None:
            return _reply(
                gemini_result['text'],
                generator='gemini',
                sources=[{'topic': e.topic, 'id': e.id} for e in entries],
                extra={'model': gemini_result['model']},
            )

        # Fallback — extractive QA against the retrieved context.
        # Zero-hallucination literal quote, but readable (2026-10-09):
        # the raw model span can start mid-sentence ("required documents —
        # fpo_reg_cert, bank") and the old low-confidence path dumped the
        # entire KB body — both read as broken replies whenever Gemini was
        # down. The span is now snapped outward to full sentence
        # boundaries, and the low-confidence path quotes only the leading
        # sentences of the top entry. Still always a literal substring of
        # the retrieved KB.
        context = '\n\n'.join(f'{e.topic}. {e.body_en}' for e in entries)
        qa = qa_ask(question=message, context=context)

        if qa['confident']:
            reply = (
                _snap_to_sentences(context, qa['start'], qa['end'])
                or qa['answer']
            )
        else:
            reply = (
                _leading_sentences(entries[0].body_en)
                if entries else _fallback_reply(lang)
            )

        return _reply(
            reply,
            generator='extractive',
            sources=[{'topic': e.topic, 'id': e.id} for e in entries],
            confidence=qa['score'],
        )


_SENTENCE_ENDS = ('.', '!', '?', '\n')


def _snap_to_sentences(context: str, start: int, end: int,
                       max_chars: int = 480) -> str:
    """Expand a model span outward to whole sentence boundaries.

    The extractive model points at the minimal answering span; quoting it
    alone reads like a fragment. Expanding to the enclosing sentence(s)
    keeps the zero-hallucination property (still a literal substring of
    the retrieved KB) while reading like an actual reply. Returns '' on
    any inconsistency so the caller falls back to the raw span.
    """
    try:
        if not context or not (0 <= start < end <= len(context)):
            return ''
        # Walk left to the previous sentence terminator (or text start).
        left = start
        while left > 0 and context[left - 1] not in _SENTENCE_ENDS:
            left -= 1
        # Walk right to the next terminator (or text end), keeping it.
        right = end
        while right < len(context) and context[right - 1] not in _SENTENCE_ENDS:
            right += 1
        snippet = context[left:right].strip()
        if len(snippet) > max_chars:
            # Over budget — trim trailing sentences past the span's own end.
            cut = snippet.rfind('.', 0, max_chars)
            snippet = snippet[:cut + 1] if cut > (end - left) else snippet[:max_chars]
        return snippet.strip()
    except Exception:  # noqa: BLE001 — cosmetic helper must never break the reply
        return ''


def _leading_sentences(text: str, max_chars: int = 480) -> str:
    """First few sentences of a KB body — replaces the old full-body dump
    on low-confidence answers."""
    t = (text or '').strip()
    if len(t) <= max_chars:
        return t
    cut = t.rfind('.', 0, max_chars)
    return (t[:cut + 1] if cut > 80 else t[:max_chars]).strip()


def _fallback_reply(lang: str = 'en') -> str:
    """Static message when we can't find anything useful. Pulls the
    canonical wording from fallback_contacts so EN + ML stay in sync and
    the three generic-refusal paths (Gemini case C, extractive, no-KB)
    all read the same (BUG-12)."""
    from apps.chatbot.services.fallback_contacts import generic_refusal
    return generic_refusal(lang)
