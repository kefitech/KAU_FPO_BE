"""
Chatbot Knowledge — Auto-generate KB entries by reading the FE component tree.

Approved 2026-09-27: walk every `page.tsx` under a portal root, follow one
level of `_components/*.tsx` imports, extract every human-readable signal
(headings, buttons, form labels, breadcrumb titles, static content arrays)
and produce one KB entry per route.

Idempotent — every entry is written via `update_or_create` keyed on
`topic`. Safe to re-run after FE tweaks. Also produces a `preview` JSON
file so we can eyeball entries BEFORE seeding the DB.

Phases (Portals):
    'public' → src/app/(public)/**       audiences=['public','all']
    'fpo'    → src/app/fpo/(portal)/**   audiences=['fpo_manager']
             + src/app/fpo/(wizard)/**   audiences=['public','fpo_manager','all']
    (later: cbbo / expert / government / buyer / admin)

Usage — preview a phase:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/seed_chatbot_knowledge_from_fe.py').read())
    seed_chatbot_knowledge_from_fe(phase='public', mode='preview')
    "

Usage — seed a phase:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/seed_chatbot_knowledge_from_fe.py').read())
    seed_chatbot_knowledge_from_fe(phase='fpo', mode='seed')
    "

Author: Athul Gopan (Kefi Tech Solutions)
Created: 2026-09-27
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

# FE repo path — the parser reads .tsx files directly. Adjust if the FE repo
# lives elsewhere in your dev env; the deployed docker containers include a
# copy at /app/frontend/, but the seed is meant to be run locally / from a
# dev shell.
_FE_ROOT_CANDIDATES = [
    Path('/home/athul_dasp/Desktop/AGRI-THRISSUR/KAU-FPO Platform-FE'),
    Path('/app/frontend'),
]


def _find_fe_root() -> Path:
    for candidate in _FE_ROOT_CANDIDATES:
        if (candidate / 'src' / 'app').exists():
            return candidate
    raise RuntimeError(
        'KAU-FPO FE repo not found — checked ' +
        ', '.join(str(c) for c in _FE_ROOT_CANDIDATES)
    )


# Regexes for extracting text signals from .tsx files
# Order matters — we walk the file once and try each pattern.

# Match both `title="Static"` and `title={t.foo ?? "Fallback"}` patterns.
_BREADCRUMB_TITLE_RE = re.compile(
    r'<BreadCrumb[^>]*title=\{?(?:[^"?}]*\?\?\s*)?"([^"]+)"',
    re.MULTILINE,
)
_BREADCRUMB_CRUMB_RE = re.compile(
    r'breadCrumb=\{?(?:[^"?}]*\?\?\s*)?"([^"]+)"'
)

# Headings — literal children inside <h1..h6>...</h1..h6>.
# NB: match group must NOT contain `{` since that indicates JSX expression
# (e.g. `<h1>{t.title}</h1>`) — those don't have literal text to extract.
_HEADING_RE = re.compile(r'<h[1-6][^>]*>\s*([A-Z][^<{]{2,80}?)\s*</h[1-6]>', re.MULTILINE)

# JSX text nodes inside components — noisy, we only grab a few common containers
_CARDTITLE_RE = re.compile(r'<CardTitle[^>]*>\s*([A-Z][^<{]{2,80})\s*</CardTitle>')
_TABLEHEAD_RE = re.compile(r'<TableHead[^>]*>\s*([A-Z][^<{]{1,50})\s*</TableHead>')

# <Button ...>Text</Button> — text child only, skip icon-only buttons
_BUTTON_TEXT_RE = re.compile(r'<Button[^>]*>\s*(?:<[^>]+/>\s*)?([A-Z][A-Za-z0-9 \.,\-&]{1,60})\s*</Button>', re.MULTILINE)

# <a href="...">Text</a> — only literal-text anchors (skip icons + links with children)
_ANCHOR_TEXT_RE = re.compile(r'<a\s[^>]*>\s*([A-Z][A-Za-z0-9 \.,\-&]{2,60})\s*</a>')

# label / placeholder / title attributes carrying human-readable strings
_LABEL_ATTR_RE = re.compile(r'\b(?:aria-label|placeholder|title)=\{?"([A-Z][^"]{1,80})"')

# Fallback strings from `t.foo ?? "Fallback"` — this is where the *real* label lives
_T_FALLBACK_RE = re.compile(r't\??\.[a-zA-Z_]\w*\s*\?\?\s*"([^"]{2,100})"')

# The FPO portal + Admin portal use a very consistent pattern for their
# page title: `<h1 class="...">{t.page_title ?? "Actual Title"}</h1>`.
# Some pages assign the translation dict to another variable name
# (tPage, tCommon, translations), so allow any identifier before
# `.page_title`. Capturing this specifically gives us a reliable topic
# anchor on pages that don't use a BreadCrumb (portal pages don't).
_PAGE_TITLE_FALLBACK_RE = re.compile(
    r'\b[a-zA-Z_]\w*\??\.page_title\s*\?\?\s*"([^"]{2,80})"'
)

# translationsApi.getPublic(locale, "namespace") — record which translation
# namespace the page uses so we know where to look for i18n content later.
_TRANSLATION_NS_RE = re.compile(r'translationsApi\.getPublic\(\s*locale\s*,\s*"([^"]+)"')

# Named imports of components — used to follow one level of nesting
_IMPORT_RE = re.compile(
    r'^import\s+(?:\{[^}]+\}|(\w+))\s+from\s+"(\./[^"]+|\.\./[^"]+)"',
    re.MULTILINE,
)

# Strings inside a static array of dicts (like the SERVICES / CARDS pattern)
_STATIC_ARRAY_STRING_RE = re.compile(r'(?:title|description|label|name|key):\s*"([A-Z][^"]{2,120})"')


def _route_from_path(page_path: Path, app_root: Path) -> str:
    """Convert a filesystem `page.tsx` path into its Next.js route.

    Rules:
      * strip the `src/app/` prefix + trailing `page.tsx`
      * drop route groups — parenthesised segments like `(public)` and
        `(auth)` don't affect the URL
      * keep dynamic segments `[id]` as-is
      * root of a route group → `/`
    """
    rel = page_path.relative_to(app_root)
    parts = list(rel.parts[:-1])  # drop 'page.tsx'
    kept = [p for p in parts if not (p.startswith('(') and p.endswith(')'))]
    return '/' + '/'.join(kept) if kept else '/'


def _resolve_component_path(from_file: Path, spec: str) -> Path | None:
    """Resolve a `./foo` or `../bar/baz` import to an actual .tsx file."""
    base = from_file.parent
    candidate = (base / spec).resolve()
    for suffix in ('.tsx', '.ts', '/index.tsx', '/index.ts'):
        p = Path(str(candidate) + suffix)
        if p.exists():
            return p
    if candidate.is_file():
        return candidate
    return None


def _extract_signals(content: str) -> dict:
    """Pull every human-readable signal out of a single .tsx file."""
    signals = {
        'page_title':      [m.strip() for m in _PAGE_TITLE_FALLBACK_RE.findall(content)],
        'breadcrumb_title':[m.strip() for m in _BREADCRUMB_TITLE_RE.findall(content)],
        'breadcrumb_crumb':[m.strip() for m in _BREADCRUMB_CRUMB_RE.findall(content)],
        'headings':        [m.strip() for m in _HEADING_RE.findall(content)],
        'card_titles':     [m.strip() for m in _CARDTITLE_RE.findall(content)],
        'table_columns':   [m.strip() for m in _TABLEHEAD_RE.findall(content)],
        'buttons':         [m.strip() for m in _BUTTON_TEXT_RE.findall(content)],
        'anchors':         [m.strip() for m in _ANCHOR_TEXT_RE.findall(content)],
        'labels':          [m.strip() for m in _LABEL_ATTR_RE.findall(content)],
        't_fallbacks':     [m.strip() for m in _T_FALLBACK_RE.findall(content)],
        'static_strings':  [m.strip() for m in _STATIC_ARRAY_STRING_RE.findall(content)],
        'translation_ns':  _TRANSLATION_NS_RE.findall(content),
    }
    # Sort + dedupe within each list — keeps output stable across runs
    for k in signals:
        if isinstance(signals[k], list):
            signals[k] = sorted(set(signals[k]))
    return signals


def _read_page_and_children(page_path: Path) -> tuple[str, list[Path]]:
    """Read page.tsx and return (content, list_of_child_component_paths)."""
    content = page_path.read_text(encoding='utf-8', errors='replace')
    child_paths: list[Path] = []
    for _named, spec in _IMPORT_RE.findall(content):
        # Only follow relative imports that likely point to sibling components.
        if not spec.startswith(('./', '../')):
            continue
        resolved = _resolve_component_path(page_path, spec)
        if resolved and resolved.exists() and resolved != page_path:
            child_paths.append(resolved)
    return content, child_paths


def _merge_signals(a: dict, b: dict) -> dict:
    """Merge two signal dicts, dedupe within each list."""
    out = {}
    for k in a:
        combined = a.get(k, []) + b.get(k, [])
        out[k] = sorted(set(combined))
    return out


# Manual topic overrides for pages that don't cleanly expose a static title
# (dynamic <h1>{fpoName}</h1>, wizard-only routes, etc.). Keys are the route
# path as produced by `_route_from_path`.
_ROUTE_TITLE_OVERRIDES = {
    # FPO Portal — pages whose h1 is a dynamic value (FPO name, DPR title).
    '/fpo/dashboard':                    'FPO Dashboard',
    '/fpo/inbox':                        'Inbox',
    '/fpo/market':                       'Market Linkage',
    '/fpo/profile':                      'FPO Profile',
    '/fpo/settings':                     'Settings',
    '/fpo/settings/profile':             'Account Profile',
    '/fpo/buyer-directory':              'Buyer Directory',
    '/fpo/buyer-directory/fpo/[id]':     'Buyer Detail',
    '/fpo/dpr/[uuid]':                   'DPR Project Overview',
    '/fpo/dpr/[uuid]/sections/[key]':    'DPR Wizard — Section Editor',
    '/fpo/products/new':                 'Add New Product',
    '/fpo/products/[id]/edit':           'Edit Product',
    # FPO Registration Wizard
    '/fpo/register':                     'FPO Registration Wizard',
}


def _guess_topic(route: str, signals: dict, topic_prefix: str = 'Public — ') -> str:
    """Human-readable topic for a KB entry.

    Prefers BreadCrumb string picked up during signal extraction, then a
    genuine headline, then a `t.fallback` string, then the route slug.
    Filters out anything that looks like JSX expression syntax or a class
    string.

    `topic_prefix` — string prepended to the derived label so entries from
    different portals sort together (e.g. "Public — ", "FPO Portal — ").
    """
    def _clean(s: str) -> str | None:
        s = s.strip()
        if not s or s.startswith('{') or '}' in s or s.startswith('$'):
            return None
        if len(s) < 3 or len(s) > 60:
            return None
        return s

    # Root / home page — no BreadCrumb, but plenty of section signals. Give
    # it a stable topic so it doesn't pick up whichever section heading
    # happened to sort first alphabetically.
    if route == '/':
        return f'{topic_prefix}Home / Landing Page'

    # Manual overrides (see _ROUTE_TITLE_OVERRIDES). Applied first so we
    # don't fall through to an auto-detected wrong answer.
    override = _ROUTE_TITLE_OVERRIDES.get(route)
    if override:
        return f'{topic_prefix}{override}'

    # Portal pages (FPO / Admin / etc.) don't use BreadCrumb — they follow a
    # very consistent `<h1>{t.page_title ?? "Real Title"}</h1>` pattern.
    # Capture that first — it's the most reliable topic anchor.
    for h in signals.get('page_title', []):
        c = _clean(h)
        if c:
            return f'{topic_prefix}{c}'

    # BreadCrumb `title=` prop is next best — used by (public) pages.
    for h in signals.get('breadcrumb_title', []):
        c = _clean(h)
        if c:
            return f'{topic_prefix}{c}'
    for h in signals.get('headings', []):
        c = _clean(h)
        if c and c.lower() not in {'available', 'download', 'view', 'more'}:
            return f'{topic_prefix}{c}'
    for h in signals.get('t_fallbacks', []):
        c = _clean(h)
        if c:
            return f'{topic_prefix}{c}'

    slug = route.strip('/') or 'home'
    slug_pretty = slug.replace('/', ' → ').replace('-', ' ').title()
    return f'{topic_prefix}{slug_pretty} page'


def _looks_clean(s: str) -> bool:
    """Reject JSX expressions, class-name strings, path fragments, empty."""
    if not s or len(s) < 3:
        return False
    if s.startswith(('{', '$', '/', 'http')) or '}' in s:
        return False
    # Reject strings that look like class names or CSS
    if s.count(' ') > 6 and any(x in s for x in (':', 'flex-', 'grid-', 'text-', 'gap-', 'w-', 'h-')):
        return False
    return True


def _build_body(route: str, signals: dict) -> str:
    """Compose a 2-5 sentence KB body describing what this page shows."""
    parts: list[str] = []
    breadcrumb = ''
    for bc in signals.get('breadcrumb_title', []):
        if _looks_clean(bc):
            breadcrumb = bc
            break
    if breadcrumb:
        parts.append(f'This is the "{breadcrumb}" page on the public KAU-FPO site, at {route}.')
    else:
        parts.append(f'This public page lives at {route}.')

    def _clean_list(items: list[str], min_len: int = 3, max_len: int = 80) -> list[str]:
        return [s.strip() for s in items if _looks_clean(s.strip())
                and min_len <= len(s.strip()) <= max_len]

    # Headings + card titles describe the sections on the page.
    section_bits = list(dict.fromkeys(
        _clean_list(signals.get('headings', []) + signals.get('card_titles', []))
    ))[:8]
    if section_bits:
        parts.append('Sections and headings on the page: ' + ' / '.join(section_bits) + '.')

    # Buttons + anchors tell the user what actions are available.
    actions = list(dict.fromkeys(
        _clean_list(signals.get('buttons', []) + signals.get('anchors', []), max_len=60)
    ))[:8]
    if actions:
        parts.append('Buttons and links: ' + ', '.join(actions) + '.')

    # Table columns — useful when the page shows a data listing.
    cols = _clean_list(signals.get('table_columns', []), max_len=50)[:10]
    if cols:
        parts.append('Data columns shown: ' + ', '.join(cols) + '.')

    # Form fields — labels + placeholders + short fallbacks.
    fields = list(dict.fromkeys(
        _clean_list(signals.get('labels', []) + signals.get('t_fallbacks', []),
                    min_len=4, max_len=40)
    ))[:8]
    if fields:
        parts.append('Form fields or user inputs: ' + ', '.join(fields) + '.')

    # Static content (SERVICES / CARDS arrays) — often the meat of a listing page
    statics = _clean_list(signals.get('static_strings', []), max_len=120)[:6]
    if statics:
        parts.append('Content items surfaced: ' + ', '.join(statics) + '.')

    # If we ended up with just the "This page lives at ..." line, the page
    # is almost certainly a thin wrapper over a CMS-driven component (e.g.
    # /howtoregister loads its body from the CMS). Flag it so the admin
    # can decide whether to hand-write a proper KB entry later.
    if len(parts) == 1:
        parts.append(
            'The visible content on this page is loaded dynamically from '
            'the site content CMS — refer to the site content admin panel '
            'for the current copy.'
        )

    return ' '.join(parts)


def _build_keywords(route: str, signals: dict) -> str:
    """Space-separated keyword blob for FTS retrieval."""
    tokens: list[str] = []
    tokens.append(route.strip('/').replace('/', ' ').replace('-', ' '))
    for k in ('headings', 'card_titles', 'buttons', 'anchors', 'labels',
              't_fallbacks', 'static_strings'):
        for v in signals.get(k, [])[:5]:
            tokens.append(v)
    blob = ' '.join(tokens).lower()
    # Keep only alnum + spaces
    blob = re.sub(r'[^a-z0-9 ]+', ' ', blob)
    blob = re.sub(r'\s+', ' ', blob).strip()
    return blob[:800]


# ─────────────────────────────────────────────────────────────────────────────
# Phase config — one entry per audience surface
# ─────────────────────────────────────────────────────────────────────────────
#
# For each phase we declare the sub-roots to walk under `src/app/` and the
# audiences to assign to entries produced from each sub-root. Topic prefix
# is prepended to distinguish e.g. FPO Dashboard from Admin Dashboard.

_PHASES = {
    'public': [
        {
            'sub_root':      'src/app/(public)',
            'topic_prefix':  'Public — ',
            'audiences':     ['public', 'all'],
        },
    ],
    'fpo': [
        {
            'sub_root':      'src/app/fpo/(portal)',
            'topic_prefix':  'FPO Portal — ',
            'audiences':     ['fpo_manager'],
        },
        {
            'sub_root':      'src/app/fpo/(wizard)',
            'topic_prefix':  'FPO Registration Wizard — ',
            'audiences':     ['public', 'fpo_manager', 'all'],
        },
    ],
    # Placeholders for future phases — same shape when we get to them.
    # 'cbbo':       [{'sub_root': 'src/app/cbbo', ...}],
    # 'expert':     [{'sub_root': 'src/app/expert', ...}],
    # 'government': [{'sub_root': 'src/app/government', ...}],
    # 'buyer':      [{'sub_root': 'src/app/buyer', ...}],
    # 'admin':      [{'sub_root': 'src/app/admin', ...}],
}


def _walk_pages(fe_root: Path, sub_root: str) -> list[Path]:
    """Return every page.tsx under fe_root/<sub_root>/, skipping
    Next.js catch-all `[...not_found]/page.tsx` files."""
    root = fe_root / sub_root
    if not root.exists():
        return []
    return sorted(
        p for p in root.rglob('page.tsx')
        if '[...not_found]' not in str(p)
    )


def _entry_for(page_path: Path, fe_root: Path,
               topic_prefix: str, audiences: list[str]) -> dict:
    """Produce one KB-entry dict from one page.tsx (and its children)."""
    app_root = fe_root / 'src' / 'app'
    route = _route_from_path(page_path, app_root)

    page_content, children = _read_page_and_children(page_path)
    page_signals = _extract_signals(page_content)

    combined = page_signals
    for child in children:
        try:
            child_content = child.read_text(encoding='utf-8', errors='replace')
            child_signals = _extract_signals(child_content)
            combined = _merge_signals(combined, child_signals)
        except Exception:
            # Ignore unreadable / weird files silently — best-effort parse
            continue

    topic    = _guess_topic(route, combined, topic_prefix=topic_prefix)
    body     = _build_body(route, combined)
    keywords = _build_keywords(route, combined)

    return {
        'topic':      topic,
        'route':      route,
        'body_en':    body,
        'audiences':  list(audiences),
        'pages':      [route],
        'keywords':   keywords,
        'source':     f'fe_page:{route}',
        # Debug bits — kept only in the JSON preview, dropped before insert
        '_signals':   combined,
    }


def seed_chatbot_knowledge_from_fe(
    phase: str = 'public',
    mode: str = 'preview',
) -> None:
    """Public entrypoint.

    Args:
        phase — which portal to walk. See _PHASES keys.
                'public' = /(public) pages (19 routes)
                'fpo'    = /fpo/(portal) + /fpo/(wizard) (~29 routes)
        mode  — 'preview' writes /tmp/kb_from_fe_<phase>.json + summary.
                'seed'    also upserts into ChatKnowledgeEntry.
    """
    if mode not in ('preview', 'seed'):
        raise ValueError(f"mode must be 'preview' or 'seed', got {mode!r}")
    if phase not in _PHASES:
        raise ValueError(
            f"phase must be one of {list(_PHASES)}, got {phase!r}"
        )

    fe_root = _find_fe_root()
    print('=' * 70)
    print(f'CHATBOT KB — Phase: {phase}   mode: {mode}')
    print('FE root:', fe_root)
    print('=' * 70)

    entries: list[dict] = []
    for sub in _PHASES[phase]:
        pages = _walk_pages(fe_root, sub['sub_root'])
        print(f'\n[{sub["sub_root"]}] found {len(pages)} page(s), '
              f'audience={sub["audiences"]}')
        for page in pages:
            entry = _entry_for(
                page, fe_root,
                topic_prefix=sub['topic_prefix'],
                audiences=sub['audiences'],
            )
            entries.append(entry)
            print(f'  ✓ {entry["route"]:50s}  →  {entry["topic"][:70]}')

    # Write preview JSON (dropping debug signals so the file stays readable)
    preview_path = Path(f'/tmp/kb_from_fe_{phase}.json')
    with preview_path.open('w', encoding='utf-8') as f:
        json.dump(
            [{k: v for k, v in e.items() if not k.startswith('_')} for e in entries],
            f, indent=2, ensure_ascii=False,
        )
    print(f'\nPreview JSON written to: {preview_path}')

    if mode == 'seed':
        from apps.database.models import ChatKnowledgeEntry
        created, updated = 0, 0
        for e in entries:
            _obj, was_new = ChatKnowledgeEntry.objects.update_or_create(
                topic=e['topic'],
                defaults={
                    'body_en':   e['body_en'],
                    'audiences': e['audiences'],
                    'pages':     e['pages'],
                    'keywords':  e['keywords'],
                    'is_active': True,
                },
            )
            if was_new:
                created += 1
            else:
                updated += 1
        print(f'\n✅ Phase {phase!r} seeded — Created: {created}  Updated: {updated}')
        print(f'Total KB entries now: {ChatKnowledgeEntry.objects.count()}')
