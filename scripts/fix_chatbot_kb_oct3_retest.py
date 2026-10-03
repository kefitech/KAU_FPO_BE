"""
Chatbot KB corrections — Oct-3 retest round.

Idempotent: safe to run multiple times, safe to run on local or server.
Applies the fixes called out in `Documents/BUG-REPORT/KAU_FPO_Chatbot_Test_Report_new.xlsx`
sheet 'Retest 03-Oct' for BUG-01, BUG-11, BUG-14.

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/fix_chatbot_kb_oct3_retest.py').read())
    fix_chatbot_kb_oct3_retest()
    "
"""

from apps.database.models.chatbot import ChatKnowledgeEntry


def _update_or_log(topic_match: str, patch: dict) -> None:
    qs = ChatKnowledgeEntry.objects.filter(topic__iexact=topic_match)
    if not qs.exists():
        print(f'  ! topic not found: {topic_match!r} — skipped')
        return
    for e in qs:
        before = {k: getattr(e, k) for k in patch}
        for k, v in patch.items():
            setattr(e, k, v)
        e.save()
        print(f'  ✓ id={e.id} updated → {patch}')
        print(f'    was: {before}')


def fix_chatbot_kb_oct3_retest():
    print('BUG-01 — CBBO Portal — FPO Verifications: rewrite body so Gemini stops saying "approve"')
    _update_or_log(
        'CBBO Portal — FPO Verifications',
        {
            'body_en': (
                'CBBO users use this page at /cbbo/verifications to VERIFY member '
                'details for FPOs in their assigned districts — confirming that '
                'the FPO\'s member list, documents and declared counts are '
                'accurate. CBBOs do NOT approve FPO applications: application '
                'approval is fully automated on submission (see the Admin '
                'applications workflow for details). The page lets you search '
                'by Application ID, FPO Name or District, open an FPO to review '
                'its members and documents, and record your verification notes.'
            ),
            'keywords': (
                'cbbo verifications verify member details assigned districts '
                'application id fpo name district search review notes '
                'does not approve application auto approved'
            ),
        },
    )

    print('BUG-11 — rename "Admin Portal — DPR Knowledge Base" so it stops matching "knowledge base"')
    _update_or_log(
        'Admin Portal — DPR Knowledge Base',
        {
            'topic': 'Admin Portal — DPR educational content (admin-only)',
            'keywords': (
                'admin dpr educational content business types commodities '
                'components create version supersede edit in place hard delete '
                'one line summary'
            ),
        },
    )

    print('BUG-14 — add fpo_manager to CBBO Portal landing entry so FPO users can learn about the CBBO portal')
    for e in ChatKnowledgeEntry.objects.filter(topic='CBBO Portal — CBBO/NGO Portal'):
        aud = list(e.audiences or [])
        if 'fpo_manager' not in aud:
            aud.append('fpo_manager')
            e.audiences = aud
            e.save()
            print(f'  ✓ id={e.id} audiences now {aud}')
        else:
            print(f'  = id={e.id} already includes fpo_manager')

    print()
    print('Done.')


if __name__ == '__main__':
    fix_chatbot_kb_oct3_retest()
