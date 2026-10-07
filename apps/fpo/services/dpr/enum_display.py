"""
DPR enum-display helpers — map raw code values stored on the FPO model
to the human label from the Translation table.

BUG-20 (KAU Section 6): the FPO stores `legal_structure`, `promoting_agency`,
`signatory_designation` etc. as plain CharField codes (`producer_companies`,
`nabard`, `ceo`). Those codes were being printed verbatim on the PDF, in the
Word export, and in the FACTS block fed to the AI. Both the appraiser and
the LLM then had to guess at the mapping. This helper resolves the
underlying Translation key `<category>.<code>` and returns the human label,
falling back to a title-cased version of the code when no translation
exists (so a never-seeded code still renders reasonably).

Called from:
    - apps/fpo/services/dpr/pdf.py / docx.py (direct)
    - apps/fpo/templates/dpr/report.html via the `dpr_enum` template filter
      registered in apps/fpo/templatetags/dpr_enum.py

Author: Athul Gopan (Kefi Tech Solutions)
"""
from __future__ import annotations

from apps.core.services.translation import t


def enum_display(category: str, code, language: str = 'en') -> str:
    """Return the human label for a `<category>.<code>` MasterLookup pair.

    Falls back to a title-cased version of the code (snake→Title Case) when
    the Translation table has no entry for the key — safer than returning
    an empty string, since the template or docx renderer may rely on the
    output being a readable word.

    None / empty code → empty string so callers can `{{ foo|default:'—' }}`.
    """
    if code is None or code == '':
        return ''
    key = f'{category}.{code}'
    result = t(key, language=language)
    if result and result != key:
        return result
    # Fallback: `producer_companies` → "Producer Companies"
    return str(code).replace('_', ' ').strip().title()


# BUG-24 (KAU §6): obvious test-data placeholders that leaked into the
# cover + Promoter Profile section of the DPR. The source is the FPO
# registration data where testers typed `TEST`, `OPK` etc. into the
# facilitating_agency_name field. Rather than block the DPR submit, we
# strip these at render time and treat the field as "Not disclosed by
# the FPO" so KAU doesn't see test clutter.
_TEST_PLACEHOLDER_PATTERNS = frozenset({
    'test', 'opk', 'todo', 'xxx', 'tbd', 'tba', 'na', 'n/a',
    'none', 'nil', 'dummy', 'sample', 'placeholder',
})


def is_test_placeholder(value) -> bool:
    """True when a free-text field value looks like a test / dummy entry.

    Matches the exact placeholder vocabulary (case-insensitive): TEST,
    OPK, TODO, XXX, TBD, TBA, NA, N/A, NONE, NIL, DUMMY, SAMPLE,
    PLACEHOLDER. Case-insensitive, trimmed.

    BUG-24 (KAU §6 retest, revision): the earlier version also rejected
    anything under 5 characters, which hid legitimate agency acronyms
    (ATMA, KVK, SFAC, NCDC). Testing team asked for exact-blocklist
    only — kept here.

    None / empty → False so the caller's own default kicks in.
    """
    if value is None:
        return False
    s = str(value).strip()
    if not s:
        return False
    return s.lower() in _TEST_PLACEHOLDER_PATTERNS


def display_or_undisclosed(value) -> str:
    """Return value if it looks real, else the 'not disclosed' sentinel.

    Shared by the PDF template filter + the docx renderer so the two
    stay consistent.
    """
    if is_test_placeholder(value):
        return 'Not disclosed by the FPO'
    return str(value or '').strip() or 'Not disclosed by the FPO'
