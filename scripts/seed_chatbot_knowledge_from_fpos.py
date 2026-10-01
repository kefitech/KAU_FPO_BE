"""
Seed FPO: <Name> — Details & Products ChatKnowledgeEntry rows.

Reads apps.database.models.FPO + apps.database.models.marketplace.Product
(read-only) → one entry per APPROVED FPO.

Idempotent. Rerunnable. Same helper (`sync_all_approved_fpos()`) is fired
by the post_save signal so the KB stays fresh as admin approves FPOs or
sellers add/remove product stock.

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/seed_chatbot_knowledge_from_fpos.py').read())
    seed_chatbot_knowledge_from_fpos()
    "
"""

from apps.chatbot.services.fpo_sync import sync_all_approved_fpos
from apps.database.models import ChatKnowledgeEntry


def seed_chatbot_knowledge_from_fpos():
    result = sync_all_approved_fpos()
    print()
    print('✅ FPO → chatbot KB seed complete.')
    print(f'   FPOs processed:      {result["total_fpos_processed"]}')
    print(f'   Entries created:     {result["created"]}')
    print(f'   Entries updated:     {result["updated"]}')
    print(f'   Entries pruned:      {result["skipped"]}')
    print(f'   Total chatbot KB entries: {ChatKnowledgeEntry.objects.count()}')
    print(f'   FPO entries in KB:   {ChatKnowledgeEntry.objects.filter(topic__startswith="FPO: ").count()}')
