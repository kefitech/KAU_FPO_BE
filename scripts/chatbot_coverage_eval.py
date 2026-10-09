"""
Chatbot coverage evaluation — Pass 1 (retrieval-only, zero AI cost).

Runs every tester question through the chatbot's KB retrieval (Postgres
FTS, role-scoped — the exact same `retrieve()` the live bot uses) and
classifies coverage WITHOUT calling any LLM:

    NO_COVERAGE — retrieval returned nothing: guaranteed KB gap.
    WEAK        — only low-rank matches: probably answers badly.
    LIKELY_OK   — strong match: Gemini very likely answers well.

Also flags SMALL_TALK rows (handled by the canned layer, no KB needed).

Usage (inside the web container):
    python manage.py shell -c "
    exec(open('scripts/chatbot_coverage_eval.py').read())
    run_coverage_eval('/tmp/questions.json', '/tmp/coverage_results.json')
    "

Input JSON:  [{"sheet": ..., "role": ..., "question": ...}, ...]
Output JSON: per-question verdict + top entries + ranks, plus summary.

Pass 2 (targeted Gemini verification of the WEAK/uncertain band) is run
separately and only after Pass 1 gaps are fixed.
"""

import json

WEAK_RANK_THRESHOLD = 0.05


def run_coverage_eval(in_path: str, out_path: str) -> dict:
    from apps.chatbot.services.retrieve import retrieve
    from apps.chatbot.services.small_talk import handle_small_talk

    with open(in_path) as f:
        questions = json.load(f)

    results = []
    summary: dict[str, dict[str, int]] = {}
    for i, row in enumerate(questions):
        q = (row.get('question') or '').strip()
        role = row.get('role') or None
        sheet = row.get('sheet') or '?'
        if not q:
            continue

        canned = None
        try:
            canned = handle_small_talk(q, user_role=role, lang='en')
        except Exception:  # noqa: BLE001
            pass

        entries = retrieve(query=q, user_role=role, current_path=None)
        tops = [
            {'topic': e.topic[:90], 'rank': round(float(getattr(e, 'rank', 0.0)), 4)}
            for e in entries
        ]
        top_rank = tops[0]['rank'] if tops else 0.0

        if canned:
            verdict = 'SMALL_TALK'
        elif not tops:
            verdict = 'NO_COVERAGE'
        elif top_rank < WEAK_RANK_THRESHOLD:
            verdict = 'WEAK'
        else:
            verdict = 'LIKELY_OK'

        results.append({
            'sheet': sheet, 'role': role or 'public', 'question': q,
            'verdict': verdict, 'top_rank': top_rank, 'matches': tops,
        })
        bucket = summary.setdefault(sheet, {})
        bucket[verdict] = bucket.get(verdict, 0) + 1
        if (i + 1) % 100 == 0:
            print(f'  ... {i + 1}/{len(questions)}')

    out = {'summary': summary, 'results': results}
    with open(out_path, 'w') as f:
        json.dump(out, f, indent=1)
    print('Summary by sheet:')
    for sheet, buckets in summary.items():
        print(' ', sheet, buckets)
    print(f'Wrote {len(results)} results to {out_path}')
    return out
