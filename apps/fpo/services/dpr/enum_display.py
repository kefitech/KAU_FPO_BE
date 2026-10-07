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
