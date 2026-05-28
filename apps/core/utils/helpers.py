"""
Helper Utilities for KAU-FPO Platform
=====================================

Common utility functions used across the application:
- UUID generation and validation
- Date/time utilities
- String utilities
- Request utilities
- File utilities

Usage:
    from apps.core.utils.helpers import generate_application_id, get_client_ip
"""

import uuid
import re
import secrets
import hashlib
from typing import Optional, Any, Dict, List
from datetime import datetime, date, timedelta
from django.utils import timezone
from django.conf import settings


# =============================================================================
# UUID & ID GENERATION
# =============================================================================

def generate_uuid() -> str:
    """Generate a new UUID4 string."""
    return str(uuid.uuid4())


def generate_short_uuid(length: int = 8) -> str:
    """
    Generate a short UUID-like identifier.

    Args:
        length: Length of the identifier (default: 8)

    Returns:
        Alphanumeric string
    """
    return uuid.uuid4().hex[:length].upper()


def generate_application_id(prefix: str = "KAU") -> str:
    """
    Generate a unique application ID.

    Format: KAU-YYYYMM-XXXXX
    Example: KAU-202501-A3F2B

    Args:
        prefix: Prefix for the ID (default: "KAU")

    Returns:
        Unique application ID
    """
    now = timezone.now()
    year_month = now.strftime("%Y%m")
    random_part = generate_short_uuid(5)
    return f"{prefix}-{year_month}-{random_part}"


def generate_otp(length: int = 6) -> str:
    """
    Generate a numeric OTP.

    Args:
        length: Length of OTP (default: 6)

    Returns:
        Numeric string
    """
    return ''.join(secrets.choice('0123456789') for _ in range(length))


def generate_token(length: int = 32) -> str:
    """
    Generate a secure random token.

    Args:
        length: Length of token (default: 32)

    Returns:
        URL-safe base64 token
    """
    return secrets.token_urlsafe(length)


def is_valid_uuid(value: str) -> bool:
    """
    Check if a string is a valid UUID.

    Args:
        value: String to check

    Returns:
        True if valid UUID, False otherwise
    """
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError):
        return False


# =============================================================================
# DATE & TIME UTILITIES
# =============================================================================

def get_current_datetime() -> datetime:
    """Get current timezone-aware datetime."""
    return timezone.now()


def get_current_date() -> date:
    """Get current date."""
    return timezone.now().date()


def format_datetime(dt: datetime, format_str: str = "%d %b %Y, %I:%M %p") -> str:
    """
    Format datetime for display.

    Args:
        dt: Datetime to format
        format_str: Format string

    Returns:
        Formatted string
    """
    if dt is None:
        return ""
    return dt.strftime(format_str)


def format_date(d: date, format_str: str = "%d %b %Y") -> str:
    """
    Format date for display.

    Args:
        d: Date to format
        format_str: Format string

    Returns:
        Formatted string
    """
    if d is None:
        return ""
    return d.strftime(format_str)


def days_until(target_date: date) -> int:
    """
    Calculate days until a target date.

    Args:
        target_date: Target date

    Returns:
        Number of days (negative if past)
    """
    today = get_current_date()
    return (target_date - today).days


def add_days(days: int, from_date: date = None) -> date:
    """
    Add days to a date.

    Args:
        days: Number of days to add
        from_date: Starting date (default: today)

    Returns:
        New date
    """
    if from_date is None:
        from_date = get_current_date()
    return from_date + timedelta(days=days)


def is_past_date(d: date) -> bool:
    """Check if date is in the past."""
    return d < get_current_date()


def is_future_date(d: date) -> bool:
    """Check if date is in the future."""
    return d > get_current_date()


# =============================================================================
# STRING UTILITIES
# =============================================================================

def slugify(text: str, max_length: int = 255) -> str:
    """
    Convert text to URL-friendly slug.

    Args:
        text: Text to slugify
        max_length: Maximum length

    Returns:
        Slugified string
    """
    # Convert to lowercase
    slug = text.lower()
    # Replace spaces and special chars with hyphens
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[-\s]+', '-', slug)
    # Remove leading/trailing hyphens
    slug = slug.strip('-')
    # Truncate
    return slug[:max_length]


def truncate(text: str, length: int = 100, suffix: str = "...") -> str:
    """
    Truncate text to specified length.

    Args:
        text: Text to truncate
        length: Maximum length
        suffix: Suffix to add if truncated

    Returns:
        Truncated string
    """
    if len(text) <= length:
        return text
    return text[:length - len(suffix)] + suffix


def mask_email(email: str) -> str:
    """
    Mask email for privacy.

    Example: john.doe@example.com -> j***e@example.com

    Args:
        email: Email to mask

    Returns:
        Masked email
    """
    if '@' not in email:
        return email

    local, domain = email.split('@')
    if len(local) <= 2:
        masked_local = local[0] + '***'
    else:
        masked_local = local[0] + '***' + local[-1]

    return f"{masked_local}@{domain}"


def mask_phone(phone: str) -> str:
    """
    Mask phone number for privacy.

    Example: 9876543210 -> ******3210

    Args:
        phone: Phone number to mask

    Returns:
        Masked phone
    """
    if len(phone) <= 4:
        return '****'
    return '*' * (len(phone) - 4) + phone[-4:]


def clean_string(value: str) -> str:
    """
    Clean and normalize a string.

    Removes extra whitespace and strips.

    Args:
        value: String to clean

    Returns:
        Cleaned string
    """
    if not value:
        return ""
    return ' '.join(value.split())


# =============================================================================
# REQUEST UTILITIES
# =============================================================================

def get_client_ip(request) -> Optional[str]:
    """
    Extract client IP address from request.

    Handles X-Forwarded-For header for proxied requests.

    Args:
        request: Django/DRF request object

    Returns:
        IP address string or None
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def get_user_agent(request) -> str:
    """
    Extract user agent from request.

    Args:
        request: Django/DRF request object

    Returns:
        User agent string
    """
    return request.META.get('HTTP_USER_AGENT', '')[:500]


def get_language_from_request(request) -> str:
    """
    Get preferred language from request.

    Checks:
    1. Query parameter 'lang'
    2. Accept-Language header
    3. User preference (if authenticated)
    4. Default 'en'

    Validates against active languages from DB — not hardcoded to en/ml.
    Any language added by admin via /api/admin/languages/ is automatically supported.
    """
    def _active_codes():
        try:
            from apps.database.models import Language
            return set(Language.objects.filter(is_active=True).values_list('code', flat=True))
        except Exception:
            return {'en', 'ml'}

    # Check query parameter
    lang = request.GET.get('lang', '').strip().lower()
    if lang and lang in _active_codes():
        return lang

    # Check Accept-Language header against active languages
    accept_lang = request.META.get('HTTP_ACCEPT_LANGUAGE', '').lower()
    if accept_lang:
        for code in _active_codes():
            if code in accept_lang:
                return code

    # Check authenticated user preference
    if hasattr(request, 'user') and request.user.is_authenticated:
        try:
            pref = request.user.profile.preferred_language
            if pref and pref in _active_codes():
                return pref
        except Exception:
            pass

    return 'en'


# =============================================================================
# FILE UTILITIES
# =============================================================================

def get_file_extension(filename: str) -> str:
    """
    Get file extension from filename.

    Args:
        filename: File name

    Returns:
        Lowercase extension without dot
    """
    if '.' not in filename:
        return ''
    return filename.rsplit('.', 1)[-1].lower()


def generate_unique_filename(original_filename: str, prefix: str = "") -> str:
    """
    Generate unique filename for uploads.

    Args:
        original_filename: Original file name
        prefix: Optional prefix

    Returns:
        Unique filename
    """
    ext = get_file_extension(original_filename)
    unique_id = generate_short_uuid(8)
    timestamp = timezone.now().strftime("%Y%m%d")

    if prefix:
        return f"{prefix}_{timestamp}_{unique_id}.{ext}"
    return f"{timestamp}_{unique_id}.{ext}"


def get_upload_path(instance, filename: str, folder: str = "uploads") -> str:
    """
    Generate upload path for file fields.

    Args:
        instance: Model instance
        filename: Original filename
        folder: Folder name

    Returns:
        Upload path
    """
    ext = get_file_extension(filename)
    unique_name = f"{generate_short_uuid(12)}.{ext}"
    year_month = timezone.now().strftime("%Y/%m")
    return f"{folder}/{year_month}/{unique_name}"


def format_file_size(size_bytes: int) -> str:
    """
    Format file size for display.

    Args:
        size_bytes: Size in bytes

    Returns:
        Human-readable size (e.g., "2.5 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


# =============================================================================
# DATA UTILITIES
# =============================================================================

def safe_get(data: Dict, key: str, default: Any = None) -> Any:
    """
    Safely get value from dictionary.

    Supports nested keys with dot notation.

    Args:
        data: Dictionary
        key: Key (supports 'nested.key.path')
        default: Default value if not found

    Returns:
        Value or default
    """
    keys = key.split('.')
    result = data

    for k in keys:
        if isinstance(result, dict):
            result = result.get(k, default)
        else:
            return default

    return result if result is not None else default


def remove_none_values(data: Dict) -> Dict:
    """
    Remove None values from dictionary.

    Args:
        data: Dictionary

    Returns:
        Dictionary without None values
    """
    return {k: v for k, v in data.items() if v is not None}


def flatten_dict(data: Dict, parent_key: str = '', sep: str = '.') -> Dict:
    """
    Flatten nested dictionary.

    Args:
        data: Nested dictionary
        parent_key: Parent key prefix
        sep: Separator

    Returns:
        Flattened dictionary
    """
    items = []
    for k, v in data.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def chunk_list(lst: List, chunk_size: int) -> List[List]:
    """
    Split list into chunks.

    Args:
        lst: List to split
        chunk_size: Size of each chunk

    Returns:
        List of chunks
    """
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


# =============================================================================
# HASH UTILITIES
# =============================================================================

def hash_string(value: str, algorithm: str = 'sha256') -> str:
    """
    Hash a string.

    Args:
        value: String to hash
        algorithm: Hash algorithm

    Returns:
        Hex digest
    """
    h = hashlib.new(algorithm)
    h.update(value.encode('utf-8'))
    return h.hexdigest()


def hash_file(file, algorithm: str = 'sha256', chunk_size: int = 8192) -> str:
    """
    Hash file contents.

    Args:
        file: File object
        algorithm: Hash algorithm
        chunk_size: Read chunk size

    Returns:
        Hex digest
    """
    h = hashlib.new(algorithm)
    file.seek(0)
    while chunk := file.read(chunk_size):
        h.update(chunk)
    file.seek(0)
    return h.hexdigest()
