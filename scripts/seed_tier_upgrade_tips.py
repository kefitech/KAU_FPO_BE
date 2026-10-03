"""
Seed TierUpgradeTip rows — starter pool of rule-based upgrade tips.

Idempotent — uses update_or_create keyed on (question, trigger_type, target_tier).
Wording is editable by KAU Admin post-seed via /api/admin/tier-upgrade-tips/.

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/seed_tier_upgrade_tips.py').read())
    seed_tier_upgrade_tips()
    "
"""

from apps.database.models import TierQuestion, TierUpgradeTip


# One tip per question. `qno` maps to TierQuestion.question_no.
# Each entry: (qno, trigger_type, trigger_value, target_tier, priority, tip_en, tip_ml)
_TIPS = [
    # Domain I — Governance
    (2, 'value_below_threshold', {'threshold': 3}, 'A', 2,
        'Increase women directors on the Board to at least 3 (33% of a 9-member board) to strengthen governance score.',
        'ബോർഡിലെ വനിതാ ഡയറക്ടർമാരുടെ എണ്ണം 3 ആയി വർദ്ധിപ്പിക്കുക (9 അംഗ ബോർഡിന്റെ 33%).'),
    (3, 'value_below_threshold', {'threshold': 5}, 'A', 3,
        'Add more Small and Marginal Farmer directors on the Board — target at least 5 to reflect the FPO\'s membership base.',
        'ബോർഡിൽ ചെറുകിട-നാമമാത്ര കർഷക ഡയറക്ടർമാരുടെ എണ്ണം കുറഞ്ഞത് 5 ആയി ഉയർത്തുക.'),
    (4, 'value_below_threshold', {'threshold': 6}, 'A', 2,
        'Conduct at least 6 Board Meetings per financial year (one every two months) to meet good-governance benchmarks.',
        'ഒരു സാമ്പത്തിക വർഷത്തിൽ കുറഞ്ഞത് 6 ബോർഡ് മീറ്റിംഗുകൾ നടത്തുക.'),
    (5, 'boolean_no', {}, 'B', 1,
        'Hold your Annual General Meeting (AGM) — it is mandatory for compliance and directly impacts your tier.',
        'വാർഷിക പൊതുയോഗം (AGM) നടത്തുക — ഇത് കംപ്ലയൻസിനും ടയർ സ്കോറിനും അനിവാര്യമാണ്.'),
    (6, 'boolean_no', {}, 'B', 1,
        'Get the previous financial year\'s statements audited by a CA and upload the report — a hard requirement for Tier B and above.',
        'മുൻ സാമ്പത്തിക വർഷത്തിന്റെ കണക്കുകൾ CA യെക്കൊണ്ട് ഓഡിറ്റ് ചെയ്യിച്ച് അപ്‌ലോഡ് ചെയ്യുക.'),

    # Domain II — Human Resources
    (7, 'answer_not_in', {'values': ['full_time', 'contractual']}, 'A', 2,
        'Appoint a full-time or contractual CEO — professional leadership significantly lifts your tier.',
        'ഫുൾ ടൈം അല്ലെങ്കിൽ കരാർ അടിസ്ഥാനത്തിൽ CEO-യെ നിയമിക്കുക.'),
    (8, 'boolean_no', {}, 'B', 3,
        'Appoint a dedicated Accountant to maintain books of accounts and audit readiness.',
        'അക്കൗണ്ട് പുസ്തകങ്ങൾ സൂക്ഷിക്കാൻ ഒരു അക്കൗണ്ടന്റിനെ നിയമിക്കുക.'),
    (9, 'boolean_no', {}, 'B', 4,
        'Add administrative or field staff — even one person materially improves operational scoring.',
        'ഭരണപരമായ അല്ലെങ്കിൽ ഫീൽഡ് സ്റ്റാഫിനെ നിയമിക്കുക.'),
    (10, 'boolean_no', {}, 'A', 4,
        'Onboard a Digital / MIS Support person to streamline reporting and data flow.',
        'ഡിജിറ്റൽ / MIS പിന്തുണക്കായി ഒരാളെ നിയമിക്കുക.'),

    # Domain III — Membership
    (13, 'value_below_threshold', {'threshold': 300}, 'A', 2,
        'Grow active membership to 300+ farmers — a Tier A benchmark. Run enrolment drives in surrounding panchayats.',
        'സജീവ അംഗങ്ങളുടെ എണ്ണം 300+ ആയി ഉയർത്തുക.'),
    (13, 'value_below_threshold', {'threshold': 100}, 'B', 1,
        'Reach at least 100 active members to qualify for Tier B — recruit through village meetings and existing member referrals.',
        'ടയർ B-ക്ക് കുറഞ്ഞത് 100 സജീവ അംഗങ്ങൾ എത്തിക്കുക.'),
    (14, 'score_below_max', {}, 'A', 3,
        'Increase share-capital participation — encourage every member to purchase at least one share.',
        'ഓരോ അംഗവും കുറഞ്ഞത് ഒരു ഷെയർ വാങ്ങിയിട്ടുണ്ടെന്ന് ഉറപ്പാക്കുക.'),

    # Domain IV — Financials
    (16, 'value_below_threshold', {'threshold': 500000}, 'A', 2,
        'Mobilise share capital of at least ₹5,00,000 — critical for institutional credit eligibility and Tier A.',
        'കുറഞ്ഞത് ₹5 ലക്ഷം ഷെയർ ക്യാപിറ്റൽ സമാഹരിക്കുക.'),
    (17, 'value_below_threshold', {'threshold': 5000000}, 'A', 1,
        'Target annual turnover of ₹50 lakh+ — expand market linkages and add value-added products to grow revenue.',
        'വാർഷിക വരുമാനം ₹50 ലക്ഷം+ ആയി ഉയർത്തുക.'),
    (17, 'value_below_threshold', {'threshold': 1000000}, 'B', 1,
        'Cross ₹10 lakh annual turnover for Tier B — increase transaction volume with existing buyers.',
        'ടയർ B-ക്ക് വാർഷിക വരുമാനം ₹10 ലക്ഷം കടക്കുക.'),
    (18, 'boolean_no', {}, 'A', 2,
        'Avail institutional credit — approach NABARD, cooperative banks, or scheduled banks with your business plan and audited statements.',
        'NABARD-ഓ ബാങ്കുകളോ വഴി സ്ഥാപനപരമായ വായ്പ എടുക്കുക.'),

    # Domain V — Infrastructure
    (21, 'answer_not_in', {'values': ['owned', 'rented_with_agreement']}, 'A', 3,
        'Secure a dedicated FPO office — owned or under a formal rental agreement — for a professional operating base.',
        'ഒരു സ്ഥിരം FPO ഓഫീസ് ഏർപ്പെടുത്തുക (സ്വന്തമായതോ കരാർ അടിസ്ഥാനത്തിലോ).'),
    (22, 'boolean_no', {}, 'B', 4,
        'Set up a computer with internet access — required for MIS, invoicing, and scheme applications.',
        'ഇന്റർനെറ്റ് ഉള്ള ഒരു കമ്പ്യൂട്ടർ സ്ഥാപിക്കുക.'),
    (23, 'boolean_no', {}, 'A', 3,
        'Arrange storage — a warehouse, godown, or cold-storage facility — to hold produce and reduce distress sales.',
        'സംഭരണ സൗകര്യം (വെയർഹൗസ്, ഗോഡൗൺ, കോൾഡ് സ്റ്റോറേജ്) ഉറപ്പാക്കുക.'),
    (24, 'boolean_no', {}, 'A', 4,
        'Add a processing or value-addition facility — even small-scale cleaning/grading equipment improves margins.',
        'പ്രോസസ്സിംഗ് അല്ലെങ്കിൽ മൂല്യവർദ്ധിത സൗകര്യം കൂട്ടിച്ചേർക്കുക.'),
    (25, 'boolean_no', {}, 'A', 5,
        'Acquire transport/logistics assets (owned or via tie-up) to reduce farmer dependence on intermediaries.',
        'ഗതാഗത / ലോജിസ്റ്റിക്സ് സൗകര്യം ഉറപ്പാക്കുക.'),

    # Domain VI — Market & Planning
    (26, 'score_below_max', {}, 'A', 2,
        'Diversify market channels — combine local markets, direct-to-consumer, ONDC/e-commerce, and institutional buyers.',
        'വിപണന ചാനലുകൾ വൈവിധ്യവൽക്കരിക്കുക (പ്രാദേശിക വിപണി, ഉപഭോക്താക്കൾക്ക് നേരിട്ട്, ONDC, സ്ഥാപനങ്ങൾ).'),
    (27, 'answer_not_in', {'values': ['documented_current']}, 'B', 1,
        'Prepare a documented, current-year Business Plan and upload it — this is the strongest single lever for tier improvement.',
        'ഈ വർഷത്തെ വിശദമായ ബിസിനസ് പ്ലാൻ തയ്യാറാക്കി അപ്‌ലോഡ് ചെയ്യുക.'),
    (28, 'score_below_max', {}, 'A', 3,
        'Access convergence schemes — apply for support under PM-KISAN FPO, NABARD, SFAC, and state agriculture schemes.',
        'PM-KISAN FPO, NABARD, SFAC, സംസ്ഥാന കാർഷിക പദ്ധതികളിലേക്ക് അപേക്ഷിക്കുക.'),

    # ─────────────────────────────────────────────────────────────────────
    # Tier C tips — basic-compliance jumps for Tier D FPOs (D → C step).
    # Thresholds are deliberately lower than the existing Tier B/A set so
    # a Tier D FPO sees achievable short-term actions first.
    # ─────────────────────────────────────────────────────────────────────

    # Domain I — Governance
    (2, 'value_below_threshold', {'threshold': 1}, 'C', 1,
        'Add at least 1 woman director to the Board — a basic representation requirement for Tier C.',
        'ടയർ C-ക്ക് ബോർഡിൽ കുറഞ്ഞത് 1 വനിതാ ഡയറക്ടറെ ഉൾപ്പെടുത്തുക.'),
    (3, 'value_below_threshold', {'threshold': 2}, 'C', 2,
        'Have at least 2 Small and Marginal Farmer directors on the Board to reflect your membership base.',
        'ബോർഡിൽ കുറഞ്ഞത് 2 ചെറുകിട-നാമമാത്ര കർഷക ഡയറക്ടർമാരെ ഉൾപ്പെടുത്തുക.'),
    (4, 'value_below_threshold', {'threshold': 2}, 'C', 1,
        'Hold at least 2 Board Meetings in the financial year (one every six months) — the minimum for Tier C.',
        'ടയർ C-ക്ക് ഒരു സാമ്പത്തിക വർഷത്തിൽ കുറഞ്ഞത് 2 ബോർഡ് മീറ്റിംഗുകൾ (ആറ് മാസത്തിലൊരിക്കൽ) നടത്തുക.'),

    # Domain II — Human Resources
    (7, 'answer_not_in', {'values': ['fulltime_ceo', 'parttime_ceo']}, 'C', 2,
        'Appoint at least a part-time CEO or Manager to coordinate FPO activities — a basic Tier C requirement.',
        'ടയർ C-ക്ക് ഒരു പാർട്ട്-ടൈം CEO/മാനേജർ നിയമിക്കുക.'),

    # Domain III — Membership
    (13, 'value_below_threshold', {'threshold': 50}, 'C', 1,
        'Reach at least 50 active members for Tier C — enrol through village meetings and member-referral drives.',
        'ടയർ C-ക്ക് കുറഞ്ഞത് 50 സജീവ അംഗങ്ങൾ എത്തിക്കുക.'),

    # Domain IV — Financials
    (16, 'value_below_threshold', {'threshold': 50000}, 'C', 1,
        'Mobilise at least ₹50,000 in share capital — ask every member to purchase at least one share.',
        'ടയർ C-ക്ക് കുറഞ്ഞത് ₹50,000 ഷെയർ ക്യാപിറ്റൽ സമാഹരിക്കുക.'),
    (17, 'value_below_threshold', {'threshold': 200000}, 'C', 1,
        'Cross ₹2 lakh annual turnover for Tier C — start regular transactions with buyers and establish steady revenue.',
        'ടയർ C-ക്ക് വാർഷിക വരുമാനം ₹2 ലക്ഷം കടക്കുക.'),

    # Domain V — Infrastructure
    (21, 'answer_not_in', {'values': ['own_office', 'rented_office', 'shared_office']}, 'C', 2,
        'Arrange at least a shared office space — have a basic operating base to meet Tier C.',
        'ടയർ C-ക്ക് കുറഞ്ഞത് ഒരു പങ്കിട്ട ഓഫീസ് ഇടം ഏർപ്പെടുത്തുക.'),

    # Domain VI — Market & Planning
    (26, 'score_below_max', {}, 'C', 2,
        'Use at least 2 market channels (e.g. local market + direct-to-consumer) — basic diversification for Tier C.',
        'ടയർ C-ക്ക് കുറഞ്ഞത് 2 വിപണന ചാനലുകൾ ഉപയോഗിക്കുക.'),
    (27, 'answer_not_in', {'values': ['3year_plan', 'annual_plan']}, 'C', 1,
        'Prepare at least an Annual Business Plan — basic planning is required for Tier C.',
        'ടയർ C-ക്ക് കുറഞ്ഞത് ഒരു വാർഷിക ബിസിനസ് പ്ലാൻ തയ്യാറാക്കുക.'),
    (28, 'score_below_max', {}, 'C', 2,
        'Apply to at least 1 convergence scheme — PM-KISAN FPO, NABARD, or a state agriculture scheme.',
        'ടയർ C-ക്ക് കുറഞ്ഞത് 1 കൺവർജൻസ് സ്കീമിലേക്ക് അപേക്ഷിക്കുക.'),
]


def seed_tier_upgrade_tips():
    created = updated = skipped = 0
    for qno, trigger, trig_val, target, priority, tip_en, tip_ml in _TIPS:
        try:
            question = TierQuestion.objects.get(question_no=qno)
        except TierQuestion.DoesNotExist:
            print(f'  ⚠  Q{qno} not found — skipped')
            skipped += 1
            continue
        _obj, was_new = TierUpgradeTip.objects.update_or_create(
            question    = question,
            trigger_type= trigger,
            target_tier = target,
            defaults    = {
                'trigger_value': trig_val,
                'tip_en':        tip_en,
                'tip_ml':        tip_ml,
                'priority':      priority,
                'is_active':     True,
            },
        )
        if was_new: created += 1
        else:       updated += 1
        print(f'  ✓ Q{qno:2d} [{trigger}] → Tier {target}  (priority {priority})')

    print(f'\n✅ Tier Upgrade Tips seeded — Created: {created}  Updated: {updated}  Skipped: {skipped}')
    print(f'Total active tips: {TierUpgradeTip.objects.filter(is_active=True).count()}')
