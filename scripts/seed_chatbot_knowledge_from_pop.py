"""
Turn KAU's CropPackageOfPractices rows into sectioned ChatKnowledgeEntry
rows so the chatbot can answer crop-related questions from KAU's own PoP
data with section-level retrieval precision.

Each crop yields up to 6 entries (one per section — empty sections are
skipped): Overview, Varieties, Spacing, Manuring & Fertilizer, Plant
Protection, Harvesting. Plus one entry per free-form `sections` dict
(rare — used for tree crops).

The actual entry-shape logic lives in apps/chatbot/services/pop_sync.py
so the post_save signal + this seed script stay in lockstep.

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/seed_chatbot_knowledge_from_pop.py').read())
    seed_chatbot_knowledge_from_pop()
    "
"""

from apps.chatbot.services.pop_sync import upsert_entries_for_crop
from apps.database.models import ChatKnowledgeEntry, CropPackageOfPractices


def seed_chatbot_knowledge_from_pop():
    # Purge legacy un-sectioned "POP: <Crop>" rows from earlier versions.
    old_qs = ChatKnowledgeEntry.objects.filter(
        topic__startswith='POP: ',
    ).exclude(topic__contains=' — ')
    old_count = old_qs.count()
    if old_count:
        old_qs.delete()
        print(f'🧹 Purged {old_count} legacy un-sectioned "POP: <Crop>" entries.')

    pops = CropPackageOfPractices.objects.filter(is_active=True, is_deleted=False).order_by('crop_name')
    print(f'Found {pops.count()} active POP crops.')

    total_created = total_updated = total_deleted = 0
    for pop in pops:
        c, u, d = upsert_entries_for_crop(pop)
        total_created += c
        total_updated += u
        total_deleted += d

    print()
    print(f'✅ POP → chatbot KB seed complete.')
    print(f'   Created: {total_created}  Updated: {total_updated}  Deleted stale: {total_deleted}')
    print(f'   Total chatbot KB entries: {ChatKnowledgeEntry.objects.count()}')
    print(f'   Sectioned POP entries:    {ChatKnowledgeEntry.objects.filter(topic__contains=" — ", topic__startswith="POP: ").count()}')
