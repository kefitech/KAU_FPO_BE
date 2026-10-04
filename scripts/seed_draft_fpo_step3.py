"""
Seed a DRAFT FPO at Step 3 for DPR-09 end-to-end validator testing.

Creates (or reuses) a test user + FPO row stuck at step 2 so the tester
can PATCH /api/fpo/me/ with step=3 payloads to exercise the board-size
validator added in `FPOStep3Serializer.validate` (DPR-09 UAT fix):

    total_directors > total_members → 400 with the error:
    "Total directors cannot exceed total members — the board is drawn
     from the membership. Reduce directors to at most the total member
     count."

Idempotent: re-running updates the FPO + user back to the seed state.

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/seed_draft_fpo_step3.py').read())
    seed_draft_fpo_step3()
    "

Credentials returned (print at end of run):
    email: dpr09-test@kefitech.com
    password: Test@1234
"""

from django.contrib.auth.models import Group, User
from django.contrib.auth.hashers import make_password

from apps.database.models import FPO
from apps.core.utils.constants import FPOStatus


_TEST_EMAIL = 'dpr09-test@kefitech.com'
_TEST_PASSWORD = 'Test@1234'


def seed_draft_fpo_step3():
    # 1. Ensure the user exists in the fpo_manager group
    user, created = User.objects.get_or_create(
        username=_TEST_EMAIL,
        defaults={
            'email': _TEST_EMAIL,
            'first_name': 'DPR09',
            'last_name': 'Tester',
            'is_active': True,
            'password': make_password(_TEST_PASSWORD),
        },
    )
    if not created:
        user.email = _TEST_EMAIL
        user.first_name = 'DPR09'
        user.last_name = 'Tester'
        user.is_active = True
        user.password = make_password(_TEST_PASSWORD)
        user.save()
    group, _ = Group.objects.get_or_create(name='fpo_manager')
    user.groups.add(group)
    print(f'  ✓ user {_TEST_EMAIL} ready (id={user.id})')

    # 2. Ensure a draft FPO linked to this user, parked at step 2 so the
    #    next PATCH on step=3 drives through FPOStep3Serializer.validate.
    fpo, created = FPO.objects.get_or_create(
        primary_user=user,
        defaults={
            'name': 'DPR09 Draft FPO',
            'status': FPOStatus.DRAFT,
            'current_step': 2,
            'office_email': _TEST_EMAIL,
            'office_phone': '9999999999',
            'district': 'TRS',
            # Step 1 fields that validate on draft creation
            'legal_structure': 'companies_act',
            'registration_number': 'DPR09-TEST-001',
        },
    )
    if not created:
        fpo.status = FPOStatus.DRAFT
        fpo.current_step = 2
        fpo.name = 'DPR09 Draft FPO'
        fpo.save()
    print(f'  ✓ FPO {fpo.name!r} ready (id={fpo.id}, status={fpo.status}, step={fpo.current_step})')
    print()
    print('Test credentials:')
    print(f'  email:    {_TEST_EMAIL}')
    print(f'  password: {_TEST_PASSWORD}')
    print()
    print('Steps to exercise DPR-09:')
    print('  1. Login via the FPO portal with the credentials above.')
    print('  2. Open the registration wizard → Step 3 should be editable.')
    print('  3. Enter total_members=10, total_directors=20 → expect')
    print('     "Total directors cannot exceed total members..." error.')
    print('  4. Change to total_directors=7 → should save.')
    print('  5. Change to total_directors=10 (equal) → should also save.')
    print()
    print('Done.')


if __name__ == '__main__':
    seed_draft_fpo_step3()
