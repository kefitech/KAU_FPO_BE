"""
Seed the default 5×5 DPR risk matrix per KAU RCD B.9.

Standard 5-level risk-management convention (Very Low → Very High on both axes,
25 cells total). Classification follows the bank-DPR heat-map convention:
  - Lower-left triangle  → Low
  - Diagonal band        → Moderate
  - Upper-right triangle → High
Extreme corners (Prob=Very High × Impact=Very High = score 25) escalate to
High as well.

                                IMPACT
                    VLow   Low   Med   High  VHigh
    Prob VLow       L(1)   L(2)  L(3)  M(4)  M(5)
    Prob Low        L(2)   L(4)  M(6)  M(8)  H(10)
    Prob Med        L(3)   M(6)  M(9)  H(12) H(15)
    Prob High       M(4)   M(8)  H(12) H(16) H(20)
    Prob VHigh      M(5)   H(10) H(15) H(20) H(25)

Idempotent — existing cells are left as-is on re-run (respects admin edits).

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/seed_dpr_risk_matrix.py').read())
    seed_dpr_risk_matrix()
    "
"""


# (probability, impact, risk_class, score)
DEFAULT_MATRIX = [
    # Very Low probability row
    ('very_low',  'very_low',  'low',       1),
    ('very_low',  'low',       'low',       2),
    ('very_low',  'medium',    'low',       3),
    ('very_low',  'high',      'moderate',  4),
    ('very_low',  'very_high', 'moderate',  5),
    # Low probability row
    ('low',       'very_low',  'low',       2),
    ('low',       'low',       'low',       4),
    ('low',       'medium',    'moderate',  6),
    ('low',       'high',      'moderate',  8),
    ('low',       'very_high', 'high',     10),
    # Medium probability row
    ('medium',    'very_low',  'low',       3),
    ('medium',    'low',       'moderate',  6),
    ('medium',    'medium',    'moderate',  9),
    ('medium',    'high',      'high',     12),
    ('medium',    'very_high', 'high',     15),
    # High probability row
    ('high',      'very_low',  'moderate',  4),
    ('high',      'low',       'moderate',  8),
    ('high',      'medium',    'high',     12),
    ('high',      'high',      'high',     16),
    ('high',      'very_high', 'high',     20),
    # Very High probability row
    ('very_high', 'very_low',  'moderate',  5),
    ('very_high', 'low',       'high',     10),
    ('very_high', 'medium',    'high',     15),
    ('very_high', 'high',      'high',     20),
    ('very_high', 'very_high', 'high',     25),
]


def seed_dpr_risk_matrix():
    from apps.database.models import DPRRiskMatrixCell

    created = 0
    skipped = 0
    for probability, impact, risk_class, score in DEFAULT_MATRIX:
        _, was_created = DPRRiskMatrixCell.objects.get_or_create(
            probability=probability,
            impact=impact,
            defaults={'risk_class': risk_class, 'score': score},
        )
        if was_created:
            created += 1
            print(f'  + {probability:>10} × {impact:>10} = {risk_class}  (score {score})')
        else:
            skipped += 1

    DPRRiskMatrixCell.invalidate_cache()
    print(f'\nDPR risk matrix seed complete: {created} created, {skipped} already present.')
