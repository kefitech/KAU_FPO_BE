"""
Seed KAU Tier Framework v1.0

Seeds 6 domains, 16 criteria, 29 questions with exact answer options and
scores from the KAU-FPO Tier Framework v1.0 document.

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/seed_tier_framework.py').read())
    seed_tier_framework()
    "

Idempotent — safe to re-run.
"""

from apps.database.models.fpo import (
    TierDomain, TierCriterion, TierQuestion,
)


# =============================================================================
# DOMAINS
# =============================================================================

DOMAINS = [
    # code, name, max_marks, order
    ('I',   'Institutional Governance',       20, 1),
    ('II',  'Management Capacity',            15, 2),
    ('III', 'Membership Strength',            15, 3),
    ('IV',  'Financial Strength',             20, 4),
    ('V',   'Infrastructure & Assets',        10, 5),
    ('VI',  'Business & Market Performance',  20, 6),
]


# =============================================================================
# CRITERIA
# =============================================================================

CRITERIA = [
    # (domain_code, code, name, max_marks, scoring_type, order)
    ('I',   'age_of_fpo',                  'Age of FPO',                        5,  'computed',       1),
    ('I',   'board_representation',        'Director Board Representation',      5,  'additive_bool',  2),
    ('I',   'governance_practices',        'Governance Practices',               10, 'additive_bool',  3),
    ('II',  'ceo_availability',            'CEO Availability',                   5,  'single_select',  1),
    ('II',  'human_resources',             'Human Resources',                    5,  'additive_bool',  2),
    ('II',  'capacity_building',           'Capacity Building',                  5,  'percentage',     3),
    ('III', 'active_membership',           'Active Membership',                  10, 'numeric_range',  1),
    ('III', 'share_capital_participation', 'Share Capital Participation',         5,  'percentage',     2),
    ('IV',  'share_capital_mobilised',     'Share Capital Mobilised',             5,  'numeric_range',  1),
    ('IV',  'annual_turnover',             'Annual Turnover',                    10, 'numeric_range',  2),
    ('IV',  'credit_linkage',              'Credit Linkage',                      5,  'conditional',    3),
    ('V',   'office_infrastructure',       'Office Infrastructure',               5,  'single_select',  1),
    ('V',   'operational_infrastructure',  'Operational Infrastructure',          5,  'additive_bool',  2),
    ('VI',  'market_linkage',              'Market Linkage',                      5,  'multi_select',   1),
    ('VI',  'business_planning',           'Business Planning',                   5,  'single_select',  2),
    ('VI',  'convergence_support',         'Convergence & External Support',      5,  'multi_select',   3),
]


# =============================================================================
# QUESTIONS
# =============================================================================

QUESTIONS = [
    # Q1 — Board total directors (used in board_representation criterion)
    {
        'question_no': 1,
        'criterion_code': 'board_representation',
        'text': 'Total number of directors on the Board?',
        'input_type': 'number',
        'answer_config': {
            'score_rule': 'board_strength',
            'ranges': [
                {'condition': 'between', 'min': 5, 'max': 15, 'score': 1},
                {'condition': 'lt', 'max': 5, 'score': 0},
            ]
        },
        'order': 1,
    },
    # Q2 — Women directors
    {
        'question_no': 2,
        'criterion_code': 'board_representation',
        'text': 'Number of women directors on the Board?',
        'input_type': 'number',
        'answer_config': {
            'score_rule': 'women_directors',
            'ranges': [
                {'condition': 'gt', 'min': 2, 'score': 2},
                {'condition': 'between', 'min': 1, 'max': 2, 'score': 1},
                {'condition': 'eq', 'value': 0, 'score': 0},
            ]
        },
        'order': 2,
    },
    # Q3 — Small/Marginal farmer directors
    {
        'question_no': 3,
        'criterion_code': 'board_representation',
        'text': 'Number of directors belonging to Small and Marginal Farmer category?',
        'input_type': 'number',
        'answer_config': {
            'score_rule': 'sm_directors',
            'ranges': [
                {'condition': 'gt', 'min': 2, 'score': 2},
                {'condition': 'eq', 'value': 1, 'score': 1},
                {'condition': 'eq', 'value': 0, 'score': 0},
            ]
        },
        'order': 3,
    },
    # Q4 — Board meetings
    {
        'question_no': 4,
        'criterion_code': 'governance_practices',
        'text': 'Number of Board Meetings conducted during the last financial year?',
        'input_type': 'number',
        'answer_config': {
            'score_rule': 'meetings',
            'ranges': [
                {'condition': 'gte', 'min': 4, 'score': 4},
                {'condition': 'lt',  'max': 4, 'score': 0},
            ],
            'note': 'Regularly = 4 or more meetings per year'
        },
        'order': 4,
    },
    # Q5 — AGM conducted
    {
        'question_no': 5,
        'criterion_code': 'governance_practices',
        'text': 'Was Annual General Meeting (AGM) conducted during the last financial year?',
        'input_type': 'boolean',
        'answer_config': {
            'options': [
                {'value': 'yes', 'label': 'Yes', 'score': 2},
                {'value': 'no',  'label': 'No',  'score': 0},
            ]
        },
        'order': 5,
    },
    # Q6 — Audited statements
    {
        'question_no': 6,
        'criterion_code': 'governance_practices',
        'text': 'Are audited financial statements available for the previous financial year?',
        'input_type': 'boolean',
        'answer_config': {
            'options': [
                {'value': 'yes', 'label': 'Yes', 'score': 4},
                {'value': 'no',  'label': 'No',  'score': 0},
            ]
        },
        'has_upload': True,
        'upload_label': 'Audited Balance Sheet and Audit Report (PDF)',
        'order': 6,
    },
    # Q7 — CEO availability
    {
        'question_no': 7,
        'criterion_code': 'ceo_availability',
        'text': 'Does the FPO have a Chief Executive Officer (CEO)?',
        'input_type': 'single_select',
        'answer_config': {
            'options': [
                {'value': 'fulltime_ceo', 'label': 'Full-time Professional CEO', 'score': 5},
                {'value': 'parttime_ceo', 'label': 'Part-time CEO',              'score': 3},
                {'value': 'no_ceo',       'label': 'No CEO',                     'score': 0},
            ]
        },
        'order': 7,
    },
    # Q8 — Accountant
    {
        'question_no': 8,
        'criterion_code': 'human_resources',
        'text': 'Does the FPO have a designated Accountant?',
        'input_type': 'boolean',
        'answer_config': {
            'options': [
                {'value': 'yes', 'label': 'Yes', 'score': 2},
                {'value': 'no',  'label': 'No',  'score': 0},
            ]
        },
        'order': 8,
    },
    # Q9 — Admin/Field staff
    {
        'question_no': 9,
        'criterion_code': 'human_resources',
        'text': 'Does the FPO have Administrative or Field Staff?',
        'input_type': 'boolean',
        'answer_config': {
            'options': [
                {'value': 'yes', 'label': 'Yes', 'score': 2},
                {'value': 'no',  'label': 'No',  'score': 0},
            ]
        },
        'order': 9,
    },
    # Q10 — Digital operator
    {
        'question_no': 10,
        'criterion_code': 'human_resources',
        'text': 'Does the FPO have a Digital Operator / MIS Support Person?',
        'input_type': 'boolean',
        'answer_config': {
            'options': [
                {'value': 'yes', 'label': 'Yes', 'score': 1},
                {'value': 'no',  'label': 'No',  'score': 0},
            ]
        },
        'order': 10,
    },
    # Q11 — Members trained
    {
        'question_no': 11,
        'criterion_code': 'capacity_building',
        'text': 'How many Board Members received formal training during the last 3 years?',
        'input_type': 'number',
        'answer_config': {
            'score_rule': 'percentage_of_q12',
            'note': 'System calculates (Q11 / Q12) × 100 to get training %'
        },
        'order': 11,
    },
    # Q12 — Total board members (denominator for Q11)
    {
        'question_no': 12,
        'criterion_code': 'capacity_building',
        'text': 'Total number of Board Members',
        'input_type': 'number',
        'answer_config': {
            'score_rule': 'denominator_for_q11',
            'percentage_ranges': [
                {'condition': 'gt',      'min': 80, 'score': 5},
                {'condition': 'between', 'min': 50, 'max': 80, 'score': 3},
                {'condition': 'between', 'min': 1,  'max': 50, 'score': 1},
                {'condition': 'eq',      'value': 0,            'score': 0},
            ]
        },
        'order': 12,
    },
    # Q13 — Active members
    {
        'question_no': 13,
        'criterion_code': 'active_membership',
        'text': 'Total number of active members in the FPO',
        'input_type': 'number',
        'answer_config': {
            'score_rule': 'numeric_range',
            'ranges': [
                {'condition': 'gt',      'min': 1000, 'score': 10},
                {'condition': 'between', 'min': 501,  'max': 1000, 'score': 8},
                {'condition': 'between', 'min': 201,  'max': 500,  'score': 6},
                {'condition': 'between', 'min': 101,  'max': 200,  'score': 4},
                {'condition': 'lte',     'max': 100,  'score': 2},
            ]
        },
        'order': 13,
    },
    # Q14 — Members with shares
    {
        'question_no': 14,
        'criterion_code': 'share_capital_participation',
        'text': 'Number of members who have purchased shares in the FPO',
        'input_type': 'number',
        'answer_config': {
            'score_rule': 'percentage_of_q15',
            'note': 'System calculates (Q14 / Q15) × 100 to get share participation %'
        },
        'order': 14,
    },
    # Q15 — Total members (denominator for Q14)
    {
        'question_no': 15,
        'criterion_code': 'share_capital_participation',
        'text': 'Total members in the FPO',
        'input_type': 'number',
        'answer_config': {
            'score_rule': 'denominator_for_q14',
            'percentage_ranges': [
                {'condition': 'gt',      'min': 90, 'score': 5},
                {'condition': 'between', 'min': 70, 'max': 90, 'score': 4},
                {'condition': 'between', 'min': 50, 'max': 69, 'score': 2},
                {'condition': 'lt',      'max': 50, 'score': 0},
            ]
        },
        'order': 15,
    },
    # Q16 — Share capital mobilised
    {
        'question_no': 16,
        'criterion_code': 'share_capital_mobilised',
        'text': 'Total share capital mobilized from members (₹)',
        'input_type': 'number',
        'answer_config': {
            'score_rule': 'numeric_range',
            'unit': 'rupees',
            'ranges': [
                {'condition': 'gt',      'min': 1000000, 'score': 5},
                {'condition': 'between', 'min': 500000,  'max': 1000000, 'score': 4},
                {'condition': 'between', 'min': 200000,  'max': 499999,  'score': 2},
                {'condition': 'lt',      'max': 200000,  'score': 1},
            ]
        },
        'order': 16,
    },
    # Q17 — Annual turnover
    {
        'question_no': 17,
        'criterion_code': 'annual_turnover',
        'text': 'Annual turnover during the previous financial year (₹)',
        'input_type': 'number',
        'answer_config': {
            'score_rule': 'numeric_range',
            'unit': 'rupees',
            'ranges': [
                {'condition': 'gt',      'min': 10000000, 'score': 10},
                {'condition': 'between', 'min': 5000000,  'max': 10000000, 'score': 8},
                {'condition': 'between', 'min': 2500000,  'max': 4999999,  'score': 5},
                {'condition': 'between', 'min': 1000000,  'max': 2499999,  'score': 3},
                {'condition': 'lt',      'max': 1000000,  'score': 1},
            ]
        },
        'has_upload': True,
        'upload_label': 'Audited Financial Statement (PDF)',
        'order': 17,
    },
    # Q18 — Credit availed
    {
        'question_no': 18,
        'criterion_code': 'credit_linkage',
        'text': 'Has the FPO availed institutional credit?',
        'input_type': 'boolean',
        'answer_config': {
            'options': [
                {'value': 'yes', 'label': 'Yes', 'score': 5},
                {'value': 'no',  'label': 'No',  'score': 0},
            ],
            'score_rule': 'conditional_q20_if_no'
        },
        'order': 18,
    },
    # Q19 — Lender details (conditional on Q18=yes, informational only)
    {
        'question_no': 19,
        'criterion_code': 'credit_linkage',
        'text': 'If yes, please provide lender details',
        'input_type': 'single_select',
        'answer_config': {
            'options': [
                {'value': 'bank',             'label': 'Bank',                      'score': 0},
                {'value': 'nabard',           'label': 'NABARD linked project',     'score': 0},
                {'value': 'other_institution','label': 'Other Institution',         'score': 0},
            ],
            'note': 'Informational only — does not affect score'
        },
        'is_conditional': True,
        'condition_value': 'yes',
        'is_required': False,
        'order': 19,
    },
    # Q20 — Credit application in process (conditional on Q18=no)
    {
        'question_no': 20,
        'criterion_code': 'credit_linkage',
        'text': 'If no, is a credit application currently under process?',
        'input_type': 'boolean',
        'answer_config': {
            'options': [
                {'value': 'yes', 'label': 'Yes', 'score': 3},
                {'value': 'no',  'label': 'No',  'score': 0},
            ]
        },
        'is_conditional': True,
        'condition_value': 'no',
        'order': 20,
    },
    # Q21 — Office infrastructure
    {
        'question_no': 21,
        'criterion_code': 'office_infrastructure',
        'text': 'What is the office status of the FPO?',
        'input_type': 'single_select',
        'answer_config': {
            'options': [
                {'value': 'own_office',    'label': 'Own Office Building', 'score': 5},
                {'value': 'rented_office', 'label': 'Rented Office',       'score': 3},
                {'value': 'shared_office', 'label': 'Shared Office',       'score': 1},
                {'value': 'no_office',     'label': 'No Office',           'score': 0},
            ]
        },
        'order': 21,
    },
    # Q22 — Computer with internet
    {
        'question_no': 22,
        'criterion_code': 'operational_infrastructure',
        'text': 'Computer with internet access available?',
        'input_type': 'boolean',
        'answer_config': {
            'options': [
                {'value': 'yes', 'label': 'Yes', 'score': 1},
                {'value': 'no',  'label': 'No',  'score': 0},
            ]
        },
        'order': 22,
    },
    # Q23 — Storage facility
    {
        'question_no': 23,
        'criterion_code': 'operational_infrastructure',
        'text': 'Storage facility available? (Warehouse / Godown / Cold Storage)',
        'input_type': 'boolean',
        'answer_config': {
            'options': [
                {'value': 'yes', 'label': 'Yes', 'score': 1},
                {'value': 'no',  'label': 'No',  'score': 0},
            ],
            'sub_type_options': ['Warehouse', 'Godown', 'Cold Storage']
        },
        'order': 23,
    },
    # Q24 — Processing facility
    {
        'question_no': 24,
        'criterion_code': 'operational_infrastructure',
        'text': 'Processing / Value Addition Facility available?',
        'input_type': 'boolean',
        'answer_config': {
            'options': [
                {'value': 'yes', 'label': 'Yes', 'score': 1},
                {'value': 'no',  'label': 'No',  'score': 0},
            ]
        },
        'order': 24,
    },
    # Q25 — Transport
    {
        'question_no': 25,
        'criterion_code': 'operational_infrastructure',
        'text': 'Transport / Logistics Asset available?',
        'input_type': 'boolean',
        'answer_config': {
            'options': [
                {'value': 'yes', 'label': 'Yes', 'score': 1},
                {'value': 'no',  'label': 'No',  'score': 0},
            ],
            'sub_type_options': ['Own vehicle', 'Contract transport', 'Other']
        },
        'order': 25,
    },
    # Q26 — Market linkage (multi-select, cap at 5)
    {
        'question_no': 26,
        'criterion_code': 'market_linkage',
        'text': 'Select all market channels currently used by the FPO',
        'input_type': 'multi_select',
        'answer_config': {
            'score_rule': 'count_capped',
            'cap': 5,
            'options': [
                {'value': 'local_market',        'label': 'Local Market',                  'score': 1},
                {'value': 'trader_wholesaler',    'label': 'Trader / Wholesaler',           'score': 1},
                {'value': 'retail_chain',         'label': 'Retail Chain',                  'score': 1},
                {'value': 'processor',            'label': 'Processor',                     'score': 1},
                {'value': 'institutional_buyer',  'label': 'Institutional Buyer',           'score': 1},
                {'value': 'exporter',             'label': 'Exporter',                      'score': 1},
            ],
            'note': 'Score = number of channels selected, capped at 5 (KAU to confirm per-channel weight)'
        },
        'order': 26,
    },
    # Q27 — Business plan
    {
        'question_no': 27,
        'criterion_code': 'business_planning',
        'text': 'Does the FPO have a documented Business Plan?',
        'input_type': 'single_select',
        'answer_config': {
            'options': [
                {'value': '3year_plan',  'label': '3-Year Business Plan available',    'score': 5},
                {'value': 'annual_plan', 'label': 'Annual Business Plan available',    'score': 3},
                {'value': 'no_plan',     'label': 'No Business Plan',                  'score': 0},
            ]
        },
        'has_upload': True,
        'upload_label': 'Business Plan Document (PDF) — optional',
        'is_required': False,
        'order': 27,
    },
    # Q28 — Convergence / external support
    {
        'question_no': 28,
        'criterion_code': 'convergence_support',
        'text': 'Has the FPO received support under any of the following?',
        'input_type': 'multi_select',
        'answer_config': {
            'score_rule': 'count_based',
            'options': [
                {'value': 'sfac',             'label': 'SFAC',                        'score': 0},
                {'value': 'nabard',           'label': 'NABARD',                      'score': 0},
                {'value': 'cbbo',             'label': 'CBBO',                        'score': 0},
                {'value': 'state_scheme',     'label': 'State Government Scheme',     'score': 0},
                {'value': 'central_scheme',   'label': 'Central Government Scheme',   'score': 0},
                {'value': 'ngo',              'label': 'NGO Support',                 'score': 0},
                {'value': 'other',            'label': 'Other',                       'score': 0},
            ],
            'count_ranges': [
                {'condition': 'gte', 'min': 2, 'score': 5},
                {'condition': 'eq',  'value': 1, 'score': 3},
                {'condition': 'eq',  'value': 0, 'score': 0},
            ]
        },
        'order': 28,
    },
    # Q29 — Financial year (meta question — system sets this)
    {
        'question_no': 29,
        'criterion_code': 'age_of_fpo',
        'text': 'Assessment Financial Year',
        'input_type': 'computed',
        'answer_config': {
            'source': 'financial_year',
            'note': 'Set by system when assessment is created'
        },
        'is_required': False,
        'order': 29,
    },
]


# =============================================================================
# SEED FUNCTION
# =============================================================================

def seed_tier_framework():
    print('=' * 60)
    print('SEEDING KAU TIER FRAMEWORK v1.0')
    print('=' * 60)

    # Domains
    domain_map = {}
    for code, name, max_marks, order in DOMAINS:
        obj, created = TierDomain.objects.update_or_create(
            code=code,
            defaults={'name': name, 'max_marks': max_marks, 'order': order},
        )
        domain_map[code] = obj
        print(f"  {'[+]' if created else '[~]'} Domain {code}: {name}")

    print()

    # Criteria
    criterion_map = {}
    for domain_code, code, name, max_marks, scoring_type, order in CRITERIA:
        obj, created = TierCriterion.objects.update_or_create(
            code=code,
            defaults={
                'domain':       domain_map[domain_code],
                'name':         name,
                'max_marks':    max_marks,
                'scoring_type': scoring_type,
                'order':        order,
                'is_active':    True,
            },
        )
        criterion_map[code] = obj
        print(f"  {'[+]' if created else '[~]'} Criterion: {code}")

    print()

    # Questions
    q19_obj = None
    q18_obj = None

    for q in QUESTIONS:
        criterion = criterion_map[q['criterion_code']]
        cond_on   = None

        defaults = {
            'criterion':      criterion,
            'text':           q['text'],
            'input_type':     q['input_type'],
            'answer_config':  q['answer_config'],
            'is_conditional': q.get('is_conditional', False),
            'condition_value': q.get('condition_value', ''),
            'is_required':    q.get('is_required', True),
            'has_upload':     q.get('has_upload', False),
            'upload_label':   q.get('upload_label', ''),
            'order':          q.get('order', q['question_no']),
        }

        obj, created = TierQuestion.objects.update_or_create(
            question_no=q['question_no'],
            defaults=defaults,
        )

        if q['question_no'] == 18:
            q18_obj = obj
        if q['question_no'] == 20:
            # Q20 is conditional on Q18
            obj.condition_on = q18_obj
            obj.save(update_fields=['condition_on'])
        if q['question_no'] == 19:
            # Q19 is conditional on Q18
            obj.condition_on = q18_obj
            obj.save(update_fields=['condition_on'])

        print(f"  {'[+]' if created else '[~]'} Q{q['question_no']}: {q['text'][:55]}")

    print()
    print(f'  Domains   : {TierDomain.objects.count()}')
    print(f'  Criteria  : {TierCriterion.objects.count()}')
    print(f'  Questions : {TierQuestion.objects.count()}')
    print('\nDone.')
