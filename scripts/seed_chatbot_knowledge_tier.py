"""
Chatbot Knowledge — Tier Classification Entries (2026-09-26)

Hand-crafted KB entries covering the FPO tier assessment: what tiers
exist, thresholds, how the score is calculated, promotions, visibility,
supporting documents, and reopen flow.

The generic auto-generation script (seed_chatbot_knowledge_auto.py) only
picks up sidebar navigation labels and .docx section headings — tier
mechanics need a proper hand-written explanation, so they live here.

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/seed_chatbot_knowledge_tier.py').read())
    seed_chatbot_knowledge_tier()
    "

Idempotent — safe to re-run. Uses update_or_create keyed on `topic`, so
edits here will overwrite existing rows next run (unlike the auto script
which get_or_creates and preserves old text).

Author: Athul Gopan (Kefi Tech Solutions)
"""
from __future__ import annotations


TIER_ENTRIES = [
    dict(
        topic='FPO Tier Classification — Overview',
        body_en=(
            'Every registered FPO is graded on a 4-tier scale — Tier A, B, C, or D — based on a 28-question '
            'assessment covering governance, financial health, member engagement, market linkages and operations. '
            'The tier appears as a badge on the FPO dashboard and is used by KAU + partner agencies when '
            'allocating schemes, subsidies and capacity-building programmes.'
        ),
        audiences=['fpo_manager', 'government', 'cbbo', 'super_admin', 'sub_admin', 'all'],
        pages=['/fpo/tier-assessment*', '/fpo/dashboard*'],
        keywords='tier grading rating classification A B C D score assessment',
    ),
    dict(
        topic='Tier Score Thresholds',
        body_en=(
            'The tier is assigned from the total assessment score out of 100: '
            'Tier A requires 80 or higher, Tier B is 65 to 79, Tier C is 50 to 64, and Tier D is below 50. '
            'Thresholds are set in code and are the same for every financial year.'
        ),
        audiences=['fpo_manager', 'government', 'cbbo', 'super_admin', 'sub_admin', 'all'],
        pages=['/fpo/tier-assessment*'],
        keywords='tier threshold score cutoff 80 65 50 A B C D',
    ),
    dict(
        topic='How the Tier Score is Calculated',
        body_en=(
            'The FPO answers 28 questions grouped into scoring criteria and domains (Governance, Finance, '
            'Operations, Market Linkage, etc.). Each criterion has a max marks cap and a scoring rule; the '
            'total is the sum of capped criterion scores across all active criteria. Answers can be text, '
            'numeric, or based on uploaded supporting documents.'
        ),
        audiences=['fpo_manager', 'government', 'cbbo', 'super_admin', 'sub_admin'],
        pages=['/fpo/tier-assessment*'],
        keywords='scoring criteria domain question weight max marks calculation',
    ),
    dict(
        topic='Tier Assessment — When to Submit',
        body_en=(
            'The FPO must complete one tier assessment per financial year (April to March). '
            'Answers can be saved as a draft and revisited from /fpo/tier-assessment. Submit when all required '
            'questions are answered — the score and tier are computed and locked immediately on submit.'
        ),
        audiences=['fpo_manager'],
        pages=['/fpo/tier-assessment*'],
        keywords='submit financial year draft complete assessment when',
    ),
    dict(
        topic='Tier History and Promotions',
        body_en=(
            'Every completed assessment writes an append-only row in the tier history for that financial year — '
            'previous tiers are never overwritten. An FPO can be promoted (e.g. Tier C → Tier B) or demoted '
            'between financial years. The current tier is the most recent history row.'
        ),
        audiences=['fpo_manager', 'government', 'cbbo', 'super_admin', 'sub_admin'],
        pages=['/fpo/tier-assessment*', '/admin/fpo-applications*'],
        keywords=(
            'history promotion demotion append financial year record '
            'change over time promoted demoted next year evolve improve tier movement'
        ),
    ),
    dict(
        topic='Who Can See the Tier',
        body_en=(
            'The FPO sees its own tier on the FPO dashboard and tier assessment page. '
            'KAU admins, sub-admins with the assigned FPO, government officials in the jurisdiction, and the '
            'assigned CBBO can also see it. Other FPOs never see one another\'s tier.'
        ),
        audiences=['fpo_manager', 'government', 'cbbo', 'super_admin', 'sub_admin'],
        pages=['/fpo/dashboard*', '/admin/*'],
        keywords='visibility privacy dashboard scoping who sees tier',
    ),
    dict(
        topic='Reopening a Submitted Tier Assessment',
        body_en=(
            'A submitted assessment is locked. Only a super admin can reopen it — usually to fix a data-entry '
            'error before the KAU review window closes. Reopening does NOT delete the previous score; the FPO '
            'can edit answers and resubmit, which creates a new score for the same financial year.'
        ),
        audiences=['super_admin', 'sub_admin', 'fpo_manager'],
        pages=['/fpo/tier-assessment*', '/admin/fpo-applications*'],
        keywords='reopen unlock edit resubmit lock super admin correction',
    ),
    dict(
        topic='Tier Assessment — Supporting Documents',
        body_en=(
            'Some questions ask for supporting documents (audit report, AGM minutes, bank statement, etc.). '
            'Upload them from the tier assessment page — accepted formats are PDF, JPG, PNG, and the size cap '
            'is 5 MB per file. Missing documents may reduce your score for the associated criterion.'
        ),
        audiences=['fpo_manager'],
        pages=['/fpo/tier-assessment*'],
        keywords='documents upload supporting evidence audit AGM PDF proof',
    ),
]


def seed_chatbot_knowledge_tier():
    """Insert or update the 8 tier classification KB entries.

    Uses update_or_create keyed on `topic` — safe to re-run, and any body
    tweaks in this file overwrite the DB copy on next run (unlike the
    auto-generator which preserves existing rows).
    """
    from apps.database.models import ChatKnowledgeEntry

    print('=' * 60)
    print('CHATBOT KB — TIER CLASSIFICATION ENTRIES')
    print('=' * 60)

    created, updated = 0, 0
    for e in TIER_ENTRIES:
        _obj, was_new = ChatKnowledgeEntry.objects.update_or_create(
            topic=e['topic'],
            defaults={
                'body_en':   e['body_en'],
                'audiences': e['audiences'],
                'pages':     e['pages'],
                'keywords':  e['keywords'],
                'is_active': True,
            },
        )
        if was_new:
            created += 1
        else:
            updated += 1

    print(f'✅ Tier entries — Created: {created}  Updated: {updated}')
    print(f'Total KB entries now: {ChatKnowledgeEntry.objects.count()}')
