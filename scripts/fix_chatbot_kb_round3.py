"""
Chatbot KB corrections — Round 3 retest.

Addresses:
- BUG-11 (still Fail): "How do I add a new knowledge base entry?" keeps
  matching POP + FAQ workflow entries. Add an explicit, high-rank
  super_admin entry stating the chatbot KB has no admin UI so Gemini
  grounds its answer on it instead of inferring from unrelated matches.

Idempotent — safe to re-run on local and server.

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/fix_chatbot_kb_round3.py').read())
    fix_chatbot_kb_round3()
    "
"""

from apps.database.models.chatbot import ChatKnowledgeEntry


_CHATBOT_KB_MGMT_TOPIC = 'Chatbot knowledge base — managed by developers (no admin UI)'
_CHATBOT_KB_MGMT_BODY = (
    'The chatbot knowledge base is maintained by the development team '
    'through seed scripts in the repository. There is no admin UI to '
    'add, edit, or delete chatbot knowledge entries from the platform. '
    'If you need a new chatbot entry (or need an existing one corrected), '
    'send the proposed topic, body text, audience roles and keywords to '
    'the development team and they will add it in the next release.'
)
_CHATBOT_KB_MGMT_KEYWORDS = (
    'chatbot knowledge base kb add new entry create edit delete manage '
    'maintain admin ui developer seed script no admin panel'
)


def fix_chatbot_kb_round3():
    print('BUG-11 round 3 — add explicit chatbot-KB-management entry')
    obj, created = ChatKnowledgeEntry.objects.update_or_create(
        topic=_CHATBOT_KB_MGMT_TOPIC,
        defaults={
            'body_en': _CHATBOT_KB_MGMT_BODY,
            'keywords': _CHATBOT_KB_MGMT_KEYWORDS,
            'audiences': ['super_admin', 'sub_admin'],
        },
    )
    verb = 'created' if created else 'updated'
    print(f'  ✓ id={obj.id} {verb}: {obj.topic!r}')
    print(f'    aud: {obj.audiences}')

    print()
    print('Done.')


if __name__ == '__main__':
    fix_chatbot_kb_round3()
