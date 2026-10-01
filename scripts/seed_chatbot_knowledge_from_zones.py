"""
Seed District: / Zone: ChatKnowledgeEntry rows so the chatbot can answer
"what can I grow in Trivandrum?" style questions.

Reads CropZoneProfile (ML side, read-only) → builds 6 zone entries + 14
district entries. Idempotent. Rerunnable.

The actual entry-shape logic lives in apps/chatbot/services/zone_sync.py
so the post_save signal + this seed script stay in lockstep.

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/seed_chatbot_knowledge_from_zones.py').read())
    seed_chatbot_knowledge_from_zones()
    "
"""

from apps.chatbot.services.zone_sync import sync_all_zones_and_districts
from apps.database.models import ChatKnowledgeEntry


def seed_chatbot_knowledge_from_zones():
    result = sync_all_zones_and_districts()
    print()
    print('✅ CropZoneProfile → chatbot KB seed complete.')
    print(f'   Zone entries created/upserted:     {result["zones_created"]} (empty pruned: {result["zones_deleted_empty"]})')
    print(f'   District entries created/upserted: {result["districts_created"]} (empty pruned: {result["districts_deleted_empty"]})')
    print(f'   Total chatbot KB entries: {ChatKnowledgeEntry.objects.count()}')
    print(f'   District entries in KB:   {ChatKnowledgeEntry.objects.filter(topic__startswith="District: ").count()}')
    print(f'   Zone entries in KB:       {ChatKnowledgeEntry.objects.filter(topic__startswith="Zone: ").count()}')
