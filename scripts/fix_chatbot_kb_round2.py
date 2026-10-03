"""
Chatbot KB corrections — Round 2 retest (post Oct-3 fixes).

Addresses:
- BUG-11 Fail: renamed POP entry still matches "add" + "entry" tokens.
  Rename again to drop both ambiguous words.
- BUG-14 Partial: CBBO Portal landing entry still invisible to
  super_admin / sub_admin (never had them). Body also reads as if the
  user is the CBBO ("your jurisdiction") which confuses FPO viewers.
  Add admin audiences and role-neutralise the body.

Idempotent — safe to re-run on local and server.

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/fix_chatbot_kb_round2.py').read())
    fix_chatbot_kb_round2()
    "
"""

from apps.database.models.chatbot import ChatKnowledgeEntry


def fix_chatbot_kb_round2():
    print('BUG-11 round 2 — drop "add" + "entry" from the POP topic')
    # Match either the current title or the one from previous round so this
    # patch is safe wherever it runs.
    pop_candidates = (
        'Add crop Package-of-Practices (POP) entry — admin only',
        'Add crop knowledge base entry',
    )
    updated_pop = 0
    for topic in pop_candidates:
        for e in ChatKnowledgeEntry.objects.filter(topic=topic):
            new_topic = 'Register a POP (Package of Practices) record for a crop — admin only'
            e.topic = new_topic
            e.keywords = (
                'crop pop package practices register record varieties spacing '
                'manuring season admin only'
            )
            e.save()
            print(f'  ✓ id={e.id} renamed → {new_topic!r}')
            updated_pop += 1
    if not updated_pop:
        print('  = already renamed in a prior run')

    print('BUG-14 round 2 — CBBO Portal landing: broaden audience + role-neutral body')
    for e in ChatKnowledgeEntry.objects.filter(topic='CBBO Portal — CBBO/NGO Portal'):
        aud = list(e.audiences or [])
        for role in ('cbbo', 'fpo_manager', 'super_admin', 'sub_admin'):
            if role not in aud:
                aud.append(role)
        e.audiences = aud
        e.body_en = (
            'The CBBO/NGO Portal at /cbbo/dashboard is where CBBO (Capacity '
            'Building Business Organisation) users work. CBBOs manage the '
            'FPOs they have been assigned, verify member details at '
            '/cbbo/verifications, submit capacity-building reports at '
            '/cbbo/reports, and maintain their profile. CBBOs do NOT approve '
            'FPO applications — application approval is fully automated on '
            'submission. Super admins create and manage CBBO user accounts '
            'at /admin/cbbos.'
        )
        e.keywords = (
            'cbbo ngo portal dashboard capacity building assigned fpos '
            'verifications reports profile does not approve application'
        )
        e.save()
        print(f'  ✓ id={e.id} audiences now {aud}')

    print()
    print('Done.')


if __name__ == '__main__':
    fix_chatbot_kb_round2()
