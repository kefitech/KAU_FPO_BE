"""
One-shot backfill for DPRProject.status.

Historical projects were all left at status='draft' because the transitions
DRAFT -> IN_PROGRESS and IN_PROGRESS -> GENERATED were never written before
today. This script rewrites their status based on observable state.

Rules:
    - Has at least one DPRDocument (PDF)  → GENERATED
    - Otherwise has at least one populated DPRSection<X> row → IN_PROGRESS
    - Otherwise stays DRAFT

Safe to re-run: only re-classifies; never demotes GENERATED -> anything else.

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/backfill_dpr_statuses.py').read())
    backfill_dpr_statuses()
    "
"""


def backfill_dpr_statuses():
    from apps.database.models import DPRProject, DPRDocument
    from apps.fpo.signals import _get_section_model_map

    section_models = list(_get_section_model_map().keys())

    print("=" * 60)
    print("BACKFILLING DPR PROJECT STATUSES")
    print("=" * 60)

    all_projects = DPRProject.objects.filter(is_deleted=False)
    print(f"Total projects to consider: {all_projects.count()}")

    generated_count = 0
    progress_count = 0
    still_draft = 0

    for project in all_projects:
        # 1. Has at least one non-archived PDF? → GENERATED
        has_pdf = DPRDocument.objects.filter(project=project, is_deleted=False).exists()
        if has_pdf:
            if project.status != DPRProject.Status.GENERATED:
                DPRProject.objects.filter(pk=project.pk).update(
                    status=DPRProject.Status.GENERATED,
                )
                generated_count += 1
                print(f"  GENERATED  id={project.id} '{project.title[:40]}'")
            continue

        # 2. Any populated section row for this project? → IN_PROGRESS.
        # Section models don't inherit BaseModel, so no is_deleted here —
        # the row's existence alone is the signal.
        has_section = any(
            model_cls.objects.filter(project=project).exists()
            for model_cls in section_models
        )
        if has_section:
            if project.status == DPRProject.Status.DRAFT:
                DPRProject.objects.filter(pk=project.pk, status=DPRProject.Status.DRAFT).update(
                    status=DPRProject.Status.IN_PROGRESS,
                )
                progress_count += 1
                print(f"  IN_PROGRESS id={project.id} '{project.title[:40]}'")
            continue

        # 3. No PDF, no sections → leave DRAFT
        still_draft += 1

    print("=" * 60)
    print(f"Result: +{generated_count} generated, +{progress_count} in_progress, {still_draft} left as draft")
    print("=" * 60)
