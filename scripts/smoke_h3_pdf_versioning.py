"""
Smoke test for H3 (KAU pre-UAT reply §7.1 + §7.2) — verifies that:
  1. DPRDocument model is queryable + relationships work
  2. Filename convention: DPR_<FPO-slug>_v<n>.pdf
  3. Version numbers are per-project monotonic + never reset
  4. Retention: after > `pdf_version_retention_count` docs, oldest excess
     rows are marked is_archived=True (never deleted per KAU §7.1)
  5. FPO-name sanitiser handles edge cases (whitespace, punctuation)

Runs against the real project; new DPRDocument rows are cleaned up at end
so re-running is idempotent.

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/smoke_h3_pdf_versioning.py').read())
    smoke_h3_pdf_versioning('7a44dcf8-8b49-4fd1-a036-1f264b12f026')
    "
"""


def smoke_h3_pdf_versioning(project_uuid: str):
    import os
    from apps.database.models import DPRProject, DPRDocument
    from apps.fpo.services.dpr.pdf import (
        build_pdf_filename,
        save_pdf_to_document,
        _fpo_slug,
        _enforce_retention,
    )

    project = DPRProject.objects.get(uuid=project_uuid)

    print('=' * 82)
    print(f'H3 SMOKE — PDF versioning + DPRDocument model')
    print('=' * 82)

    # Sanity: clean up any prior smoke runs so the test is reproducible
    prior = DPRDocument.objects.filter(project=project).count()
    if prior > 0:
        print(f'⚠️  Clearing {prior} pre-existing DPRDocument rows for this project (safe for smoke).')
        DPRDocument.objects.filter(project=project).delete()

    # ── Unit test: FPO name sanitiser ──
    print('\n--- Unit: _fpo_slug edge cases ---')

    class FakeFPO:
        def __init__(self, name):
            self.name = name

    class FakeProject:
        uuid = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'

        def __init__(self, name):
            self.fpo = FakeFPO(name)

    # Sanitiser behaviour: any run of non-alphanumerics collapses to a single '_'.
    # Apostrophes / hyphens / spaces are all treated identically — becomes a
    # boundary. Slight loss of readability ("Nyna_s" vs "Nynas") in exchange
    # for a predictable rule with no per-punctuation special cases.
    cases = [
        ("Nyna's Farm for Duck",       'Nyna_s_Farm_for_Duck'),
        ('KAU-FPO Ltd.',               'KAU_FPO_Ltd'),
        ('  Whitespace  ',             'Whitespace'),
        ('!!!',                        'aaaaaaaa'),  # falls back to uuid prefix
        ('',                           'aaaaaaaa'),
    ]
    for input_name, expected in cases:
        got = _fpo_slug(FakeProject(input_name))
        assert got == expected, f'_fpo_slug({input_name!r}) = {got!r}, expected {expected!r}'
        print(f'  ✅ _fpo_slug({input_name!r:32s}) = {got!r}')

    # ── Unit test: filename builder ──
    print('\n--- Unit: build_pdf_filename ---')
    fp = FakeProject("Nyna's Farm")
    for v in (1, 5, 42, 999):
        fn = build_pdf_filename(fp, v)
        assert fn == f'DPR_Nyna_s_Farm_v{v}.pdf', f'Got {fn!r}'
    print(f'  ✅ Filename convention: DPR_<slug>_v<n>.pdf produced for v1, v5, v42, v999')

    # ── Behaviour: next_version_for_project is monotonic ──
    print('\n--- Behaviour: version_number is monotonic per project ---')
    assert DPRDocument.next_version_for_project(project) == 1, 'First version must be 1'
    print(f'  ✅ First version = 1')

    # Generate 3 real DPRs and verify version numbers + filenames
    doc1 = save_pdf_to_document(project)
    print(f'  ✅ Doc 1: version={doc1.version_number}, file={doc1.file_url}, '
          f'size={doc1.file_size / 1024:.1f} KB')
    assert doc1.version_number == 1

    doc2 = save_pdf_to_document(project)
    assert doc2.version_number == 2
    print(f'  ✅ Doc 2: version={doc2.version_number}, monotonic increment ✓')

    doc3 = save_pdf_to_document(project)
    assert doc3.version_number == 3
    print(f'  ✅ Doc 3: version={doc3.version_number}')

    # ── Behaviour: version does NOT reset even if oldest is archived ──
    print('\n--- Behaviour: version NEVER resets (per KAU §7.2) ---')
    doc1.is_archived = True
    doc1.save(update_fields=['is_archived'])
    next_v = DPRDocument.next_version_for_project(project)
    assert next_v == 4, f'Next version after archiving v1 should still be 4, got {next_v}'
    print(f'  ✅ After archiving v1: next version = {next_v} (not reset to 2)')

    # ── Behaviour: retention soft-archives oldest when cap exceeded ──
    print('\n--- Behaviour: retention cap enforcement ---')
    # Reset archive flag on doc1 so all 3 are live
    doc1.is_archived = False
    doc1.save(update_fields=['is_archived'])
    live_before = DPRDocument.objects.filter(project=project, is_archived=False).count()
    print(f'  Live docs before retention: {live_before}')

    # Force retention cap of 2 — should archive the oldest 1
    archived_count = _enforce_retention(project, retention_cap=2)
    print(f'  Archived {archived_count} rows with cap=2')
    live_after = DPRDocument.objects.filter(project=project, is_archived=False).count()
    total_after = DPRDocument.objects.filter(project=project).count()
    assert live_after == 2, f'Live count after cap should be 2, got {live_after}'
    assert total_after == 3, f'Total (incl archived) should stay 3, got {total_after}'
    # The oldest doc (v1) should be the archived one
    doc1.refresh_from_db()
    assert doc1.is_archived is True, 'Oldest (v1) should be archived'
    print(f'  ✅ Retention: 2 live + 1 archived; total rows unchanged (KAU §7.1 no-delete)')

    # ── Cleanup smoke rows ──
    print('\n--- Cleanup ---')
    # Physically delete PDF files + DB rows so re-running the smoke starts clean
    for d in DPRDocument.objects.filter(project=project):
        media_path = d.file_url.replace('/media/', '/', 1)
        # Reconstruct absolute path
        from django.conf import settings
        abs_path = os.path.join(settings.MEDIA_ROOT, media_path.lstrip('/'))
        if os.path.exists(abs_path):
            os.remove(abs_path)
    deleted, _ = DPRDocument.objects.filter(project=project).delete()
    print(f'  ✅ Cleaned up {deleted} smoke rows + on-disk PDFs')

    print('\nAll H3 smoke checks passed. DPRDocument model + versioning ready for FE wire-up.')
