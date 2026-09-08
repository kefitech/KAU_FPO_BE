"""
Seed the default 3×3 DPR risk matrix per KAU RCD B.9.

Standard risk-management convention:
                      IMPACT
                Low     Medium    High
    Prob Low    Low     Low       Moderate
    Prob Med    Low     Moderate  High
    Prob High   Moderate High     High

Idempotent — existing cells are left as-is on re-run (respects admin edits).

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/seed_dpr_risk_matrix.py').read())
    seed_dpr_risk_matrix()
    "
"""


# (probability, impact, risk_class, score)
DEFAULT_MATRIX = [
    ('low',    'low',    'low',      1),
    ('low',    'medium', 'low',      2),
    ('low',    'high',   'moderate', 3),
    ('medium', 'low',    'low',      2),
    ('medium', 'medium', 'moderate', 3),
    ('medium', 'high',   'high',     4),
    ('high',   'low',    'moderate', 3),
    ('high',   'medium', 'high',     4),
    ('high',   'high',   'high',     5),
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
            print(f'  + {probability:>6} × {impact:>6} = {risk_class}  (score {score})')
        else:
            skipped += 1

    DPRRiskMatrixCell.invalidate_cache()
    print(f'\nDPR risk matrix seed complete: {created} created, {skipped} already present.')
