"""
Seed CBBO/NGO Organisations
============================
Placeholder organisations so the CBBO self-registration form
(POST /api/cbbo/register/) has something to select from — its
`organisation` field is required and sourced from this table, which
otherwise starts empty with no other way to populate it.

Usage:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/seed_organisations.py').read())
    seed_organisations()
    "

Only seeds if not already present (idempotent, keyed on name).
"""

from apps.database.models.organisation import Organisation


ORGANISATIONS = [
    {
        'name': 'Kerala Rural Development Trust',
        'org_type': 'ngo',
        'contact_person': 'Anitha Menon',
        'contact_designation': 'Programme Director',
        'contact_email': 'contact@keralaruraldevtrust.example',
        'contact_phone': '9847000001',
        'districts_covered': ['TVM', 'KLM', 'PTA'],
    },
    {
        'name': 'Malabar Community Business Organisation',
        'org_type': 'cbbo',
        'contact_person': 'Rajeev Nair',
        'contact_designation': 'Coordinator',
        'contact_email': 'info@malabarcbbo.example',
        'contact_phone': '9847000002',
        'districts_covered': ['KZD', 'WYD', 'KNR', 'KSD'],
    },
    {
        'name': 'Central Kerala Farmers Welfare Society',
        'org_type': 'ngo',
        'contact_person': 'Sindhu Thomas',
        'contact_designation': 'Executive Secretary',
        'contact_email': 'welfare@ckfws.example',
        'contact_phone': '9847000003',
        'districts_covered': ['EKM', 'TSR', 'IDK'],
    },
    {
        'name': 'Midland Capacity Building Organisation',
        'org_type': 'cbbo',
        'contact_person': 'Suresh Kumar',
        'contact_designation': 'Field Manager',
        'contact_email': 'suresh@midlandcbbo.example',
        'contact_phone': '9847000004',
        'districts_covered': ['KTM', 'ALP', 'PKD'],
    },
    {
        'name': 'Malappuram Agri Development Society',
        'org_type': 'ngo',
        'contact_person': 'Fathima Beevi',
        'contact_designation': 'Programme Officer',
        'contact_email': 'contact@mads.example',
        'contact_phone': '9847000005',
        'districts_covered': ['MLP'],
    },
]


def seed_organisations():
    print("=" * 60)
    print("SEEDING ORGANISATIONS")
    print("=" * 60)

    created = 0
    existing = 0
    for data in ORGANISATIONS:
        name = data['name']
        obj, was_created = Organisation.objects.get_or_create(
            name=name,
            defaults={**{k: v for k, v in data.items() if k != 'name'}, 'is_active': True},
        )
        if was_created:
            created += 1
            print(f"✅ Created  {name}")
        else:
            existing += 1
            print(f"⏭️  Exists   {name}")

    print("\n" + "=" * 60)
    print(f"✅ Done. Created: {created}, already existed: {existing}. Total organisations: {Organisation.objects.count()}")
    print("=" * 60)
