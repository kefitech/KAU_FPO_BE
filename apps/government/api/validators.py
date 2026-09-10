"""
ID format validation for government official self-registration.
Format rules per Section 3.2 (Suggested Input Validation Architecture).
"""
import re

ID_PATTERNS = {
    'agri_officer': [r'^\d{6}$'],
    'university_official': [r'^\d{6}$'],
    'sfac_official': [r'^[A-Z]{5}\d{4}[A-Z]$'],
    'cbbo_personnel': [r'^[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}$'],
    'nabard_official': [r'^\d{5}$', r'^\d{6}$'],
    'atma_specialist': [r'^\d{6,8}$', r'^[A-Z]{5}\d{4}[A-Z]$'],
}

ID_LABELS = {
    'agri_officer': 'Permanent Employee Number (PEN) - 6-digit number',
    'university_official': 'Permanent Employee Number (PEN) - 6-digit number',
    'sfac_official': 'Permanent Account Number (PAN) - 10 characters',
    'cbbo_personnel': 'Corporate Identity Number (CIN) - 21 characters, starts with L or U',
    'nabard_official': 'Employee Index Number - 5 or 6-digit number',
    'atma_specialist': 'Employee ID (6-8 digits) or PAN (10 characters)',
}


def validate_id_number(category, id_number):
    """Returns (is_valid, error_message)."""
    patterns = ID_PATTERNS.get(category)
    if not patterns:
        return False, 'Unknown user category.'

    value = (id_number or '').strip().upper()
    for pattern in patterns:
        if re.match(pattern, value):
            return True, None

    label = ID_LABELS.get(category, 'a valid ID')
    return False, f'Invalid ID number. Expected format: {label}.'
