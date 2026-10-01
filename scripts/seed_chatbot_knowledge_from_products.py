"""
Seed Product: <name> from <FPO> — Active Listing ChatKnowledgeEntry rows.

Reads apps.database.models.marketplace.ProductStock (read-only) → one
entry per active + public stock batch, so the chatbot can answer
product-level questions ("cheapest rice", "who has organic tomato").

Idempotent. Rerunnable. Same helper (`sync_all_active_products()`) is
fired by the ProductStock signal so entries stay in sync as sellers add,
edit, expire or delete stock.

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/seed_chatbot_knowledge_from_products.py').read())
    seed_chatbot_knowledge_from_products()
    "
"""

from apps.chatbot.services.product_sync import sync_all_active_products
from apps.database.models import ChatKnowledgeEntry


def seed_chatbot_knowledge_from_products():
    result = sync_all_active_products()
    print()
    print('✅ Product → chatbot KB seed complete.')
    print(f'   Stock batches processed:  {result["stocks_processed"]}')
    print(f'   Entries created:          {result["created"]}')
    print(f'   Entries updated:          {result["updated"]}')
    print(f'   Entries pruned:           {result["skipped"]}')
    print(f'   Total chatbot KB entries: {ChatKnowledgeEntry.objects.count()}')
    print(f'   Product entries in KB:    {ChatKnowledgeEntry.objects.filter(topic__startswith="Product: ").count()}')
