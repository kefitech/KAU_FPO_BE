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
from apps.chatbot.services.qa_client import ask as qa_ask
from apps.chatbot.services.retrieve import retrieve


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
        user_role = _resolve_role(request.user)

        entries = retrieve(query=message, user_role=user_role, current_path=current_path)

        if not entries:
            return StandardResponse.success(
                data={
                    'reply': _fallback_reply(),
                    'confident': False,
                    'confidence': 0.0,
                    'sources': [],
                },
                message='No relevant knowledge found.',
            )

        context = '\n\n'.join(f'{e.topic}. {e.body_en}' for e in entries)
        qa = qa_ask(question=message, context=context)

        if qa['confident']:
            reply = qa['answer']
        else:
            # Low-confidence: fall back to the top-ranked entry's body_en
            # verbatim. This is still grounded in retrieved KB (no
            # hallucination) and usually more useful than a bland fallback.
            reply = entries[0].body_en if entries else _fallback_reply()

        return StandardResponse.success(
            data={
                'reply': reply,
                'confident': qa['confident'],
                'confidence': round(qa['score'], 4),
                'sources': [
                    {'topic': e.topic, 'id': e.id}
                    for e in entries
                ],
            },
            message='Chatbot response.',
        )


def _fallback_reply() -> str:
    """Static message when we can't find anything useful.

    Post-UAT: swap for a translated version via TranslationService.
    """
    return (
        "I couldn't find an answer to that. Please rephrase your question, "
        "or contact KAU support at kau-fpo@kau.in for help."
    )
