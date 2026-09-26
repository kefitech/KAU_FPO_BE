"""
Chatbot Knowledge — Auto-Generation Script (Option B, 2026-09-26)

Bulk-generates ChatKnowledgeEntry rows from two structured sources so
the chatbot can answer questions across the whole platform without a
tech writer hand-crafting every entry:

  1. `MenuItem` table — one entry per sidebar page, using the menu label
     as the topic and the page's path + role as the shape. This gives
     "what is X for?" coverage for every navigable screen.

  2. `Documents/Usermanual/*.docx` files — chunk each user manual by
     heading, take the first paragraph after each heading as body_en.
     Filename → audience heuristic (LandingPage→public, AdminPortal→
     super_admin, FPO_Registration→fpo_manager).

Dedupe rule: an entry is skipped if a case-insensitive substring match
on `topic` already exists. Re-running the script only adds new rows.

Usage:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/seed_chatbot_knowledge_auto.py').read())
    seed_chatbot_knowledge_auto()
    "

The script prints a per-source summary + final total. Safe to re-run.

Author: Athul Gopan (Kefi Tech Solutions)
Created: 2026-09-26
"""
from __future__ import annotations

import os
import re
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

# Root of the repo — resolved via Django's BASE_DIR because this script is
# usually invoked through `manage.py shell -c "exec(open(...).read())"`,
# where __file__ points to manage.py, not to this script.
def _repo_root() -> Path:
    try:
        from django.conf import settings
        return Path(settings.BASE_DIR)
    except Exception:
        return Path(__file__).resolve().parent.parent


# .docx user manuals live here. Missing files are skipped, not fatal.
_USERMANUAL_DIR = _repo_root() / 'Documents' / 'Usermanual'

# Filename → audience list. Matches by lowercase substring.
_FILENAME_AUDIENCE = [
    ('landingpage',    ['public']),
    ('adminportal',    ['super_admin', 'sub_admin']),
    ('registration',   ['public', 'fpo_manager']),
    ('fpo_register',   ['public', 'fpo_manager']),
    ('landing',        ['public']),
    ('admin',          ['super_admin', 'sub_admin']),
    ('cbbo',           ['cbbo']),
    ('government',     ['government']),
    ('expert',         ['expert']),
    ('buyer',          ['external_buyer']),
    ('fpo',            ['fpo_manager']),
]

# Skip menu items whose label contains any of these (nav-only, not features).
_MENU_SKIP_LABELS = {'logout', 'settings', 'my profile', 'menu.logout', 'menu.settings'}

# Chunking: keep body 1-3 sentences. This is the max chars we take from a
# manual paragraph — anything longer gets truncated at a sentence boundary.
_MAX_BODY_CHARS = 400


# ─────────────────────────────────────────────────────────────────────────────
# Dedupe helpers
# ─────────────────────────────────────────────────────────────────────────────

def _existing_topics() -> set[str]:
    """Return lowercased topics of every active KB entry — for dedupe."""
    from apps.database.models import ChatKnowledgeEntry
    return {
        (e.topic or '').strip().lower()
        for e in ChatKnowledgeEntry.objects.filter(is_active=True)
    }


def _is_duplicate(topic: str, existing: set[str]) -> bool:
    """True if `topic` matches an existing KB topic (substring, case-insensitive)."""
    t = (topic or '').strip().lower()
    if not t:
        return True  # empty topic — treat as duplicate to skip
    for e in existing:
        if t == e or t in e or e in t:
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Source 1 — MenuItem table
# ─────────────────────────────────────────────────────────────────────────────

def _menu_item_body(label: str, path: str, is_admin: bool) -> str:
    """Compose a one-sentence body_en for a sidebar page.

    Kept generic on purpose — this is the "shell" entry that says
    "here's where X lives"; deeper how-to lives in the manual entries.
    """
    friendly_label = label.replace('menu.', '').replace('_', ' ').title()
    if is_admin:
        return (
            f'The {friendly_label} page is an admin console at {path}. '
            f'Open it from the sidebar to manage the underlying records.'
        )
    return (
        f'The {friendly_label} page is at {path}. Open it from the sidebar '
        f'to view or edit the relevant records for your role.'
    )


def _generate_from_menu(existing: set[str]) -> list[dict]:
    """Emit KB rows from the MenuItem table."""
    from apps.database.models import MenuItem
    out: list[dict] = []
    for item in MenuItem.objects.filter(is_active=True).prefetch_related('roles'):
        label_key = (item.label_key or '').strip()
        path = (item.path or '').strip()
        if not label_key or not path:
            continue
        if any(skip in label_key.lower() for skip in _MENU_SKIP_LABELS):
            continue
        # Friendly label — strip category prefixes like "menu."
        friendly = label_key.split('.')[-1].replace('_', ' ').strip()
        topic = f'{friendly.title()} page'
        if _is_duplicate(topic, existing):
            continue

        roles = [r.name for r in item.roles.all()] or ['all']
        is_admin = any(r in ('super_admin', 'sub_admin') for r in roles)

        out.append({
            'topic':     topic,
            'body_en':   _menu_item_body(friendly, path, is_admin),
            'audiences': roles,
            'pages':     [path],
            'keywords':  f'sidebar navigate page {friendly}',
            'source':    'menu_item',
        })
        existing.add(topic.lower())
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Source 2 — User manual .docx files
# ─────────────────────────────────────────────────────────────────────────────

def _audience_for_filename(filename: str) -> list[str]:
    """Guess audience list from the filename. Falls back to ['all']."""
    lower = filename.lower()
    for needle, aud in _FILENAME_AUDIENCE:
        if needle in lower:
            return aud
    return ['all']


def _clean_paragraph(text: str) -> str:
    """Strip whitespace, collapse repeated whitespace, truncate at sentence."""
    text = ' '.join(text.split())
    if len(text) <= _MAX_BODY_CHARS:
        return text
    # Truncate at the last full sentence within the char budget.
    cut = text[:_MAX_BODY_CHARS]
    last_dot = max(cut.rfind('.'), cut.rfind('!'), cut.rfind('?'))
    if last_dot > 100:
        return cut[: last_dot + 1]
    return cut.rstrip() + '…'


def _parse_docx(path: Path) -> list[tuple[str, str]]:
    """Return list of (heading, body) pairs from a .docx file.

    Heading = any paragraph whose style name starts with 'Heading'.
    Body = the concatenation of the next 1-3 normal paragraphs, truncated.
    """
    try:
        from docx import Document
    except ImportError:
        print(f'  [skip {path.name}] python-docx not installed')
        return []

    try:
        doc = Document(str(path))
    except Exception as e:
        print(f'  [skip {path.name}] failed to open: {e}')
        return []

    pairs: list[tuple[str, str]] = []
    current_heading: str = ''
    current_body: list[str] = []

    def flush():
        if current_heading and current_body:
            body_text = _clean_paragraph(' '.join(current_body))
            if body_text and len(body_text) > 30:
                pairs.append((current_heading.strip(), body_text))

    for para in doc.paragraphs:
        text = (para.text or '').strip()
        if not text:
            continue
        style = (para.style.name or '') if para.style else ''
        if style.startswith('Heading'):
            flush()
            current_heading = text
            current_body = []
        else:
            # Cap the number of paragraphs we accumulate per heading — too
            # long a chunk hurts retrieval + wastes tokens.
            if len(current_body) < 3:
                current_body.append(text)
    flush()
    return pairs


def _generate_from_manuals(existing: set[str]) -> list[dict]:
    """Emit KB rows from every .docx in Documents/Usermanual/."""
    if not _USERMANUAL_DIR.exists():
        print(f'  [skip manuals] {_USERMANUAL_DIR} not found')
        return []

    out: list[dict] = []
    for path in sorted(_USERMANUAL_DIR.glob('*.docx')):
        aud = _audience_for_filename(path.name)
        pairs = _parse_docx(path)
        added = 0
        for heading, body in pairs:
            topic = heading[:180]
            if _is_duplicate(topic, existing):
                continue
            out.append({
                'topic':     topic,
                'body_en':   body,
                'audiences': aud,
                'pages':     [],
                'keywords':  f'manual {path.stem} {heading.lower()}',
                'source':    path.name,
            })
            existing.add(topic.lower())
            added += 1
        print(f'  [{path.name}] {len(pairs)} sections → {added} new entries')
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Persist
# ─────────────────────────────────────────────────────────────────────────────

def _upsert_entries(rows: list[dict]) -> tuple[int, int]:
    """Insert new KB entries. Returns (created, skipped)."""
    from apps.database.models import ChatKnowledgeEntry
    created, skipped = 0, 0
    for r in rows:
        obj, was_created = ChatKnowledgeEntry.objects.get_or_create(
            topic=r['topic'],
            defaults={
                'body_en':   r['body_en'],
                'audiences': r['audiences'],
                'pages':     r.get('pages') or [],
                'keywords':  r.get('keywords', ''),
                'is_active': True,
            },
        )
        if was_created:
            created += 1
        else:
            skipped += 1
    return created, skipped


# ─────────────────────────────────────────────────────────────────────────────
# Public entrypoint
# ─────────────────────────────────────────────────────────────────────────────

def seed_chatbot_knowledge_auto():
    """Main entry — run all sources + report."""
    print('=' * 60)
    print('CHATBOT KB — AUTO-GENERATION FROM MENU + USER MANUALS')
    print('=' * 60)

    existing = _existing_topics()
    print(f'Existing KB entries: {len(existing)}')

    print('\n[Source 1] MenuItem table:')
    menu_rows = _generate_from_menu(existing)
    print(f'  → {len(menu_rows)} new entries')

    print('\n[Source 2] User manuals (Documents/Usermanual/*.docx):')
    manual_rows = _generate_from_manuals(existing)
    print(f'  → {len(manual_rows)} new entries')

    all_rows = menu_rows + manual_rows
    if not all_rows:
        print('\nNo new entries to add.')
        return

    print(f'\nPersisting {len(all_rows)} entries...')
    created, skipped = _upsert_entries(all_rows)
    print(f'✅ Created: {created}  Skipped (duplicate): {skipped}')

    from apps.database.models import ChatKnowledgeEntry
    print(f'Total KB entries now: {ChatKnowledgeEntry.objects.count()}')
