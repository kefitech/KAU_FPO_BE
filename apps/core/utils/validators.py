"""
Custom Validators for KAU-FPO Platform
======================================

Kerala-specific and Indian validators for:
- Phone numbers (10-digit Indian mobile)
- PIN codes (Kerala specific)
- PAN card numbers
- GST numbers
- IFSC codes
- Geographic coordinates (within Kerala)

Usage:
    from apps.core.utils.validators import validate_kerala_pincode, validate_indian_phone

    validate_kerala_pincode('680001')  # Valid
    validate_kerala_pincode('110001')  # Raises ValidationError
"""

import re
from typing import Optional
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

from .constants import (
    KERALA_PINCODE_PREFIX,
    KERALA_PINCODES_RANGE,
    KERALA_BOUNDS,
    INDIAN_PHONE_REGEX,
    PAN_REGEX,
    GST_REGEX,
    IFSC_REGEX,
    ALLOWED_DOCUMENT_EXTENSIONS,
    MAX_FILE_SIZE_BYTES,
)
from .messages import ValidationMessages, msg  # fallback for module-level class attributes

def _t(key, language='en', **kwargs):
    """Lazy wrapper around TranslationService to avoid circular imports at module load."""
    from apps.core.services.translation import t
    return t(key, language, **kwargs)


# =============================================================================
# PHONE VALIDATORS
# =============================================================================

def validate_indian_phone(value: str, language: str = 'en') -> str:
    """
    Validate Indian mobile phone number.

    Args:
        value: Phone number to validate
        language: Language for error message

    Returns:
        Cleaned phone number (digits only)

    Raises:
        ValidationError: If phone number is invalid
    """
    # Remove spaces, dashes, and country code
    cleaned = re.sub(r'[\s\-]', '', value)
    if cleaned.startswith('+91'):
        cleaned = cleaned[3:]
    elif cleaned.startswith('91') and len(cleaned) == 12:
        cleaned = cleaned[2:]

    if not re.match(INDIAN_PHONE_REGEX, cleaned):
        raise ValidationError(_t('invalid_phone', language))

    return cleaned


class IndianPhoneValidator(RegexValidator):
    """Django validator for Indian phone numbers."""
    regex = INDIAN_PHONE_REGEX
    message = msg(ValidationMessages.INVALID_PHONE, 'en')
    code = 'invalid_phone'


# =============================================================================
# PINCODE VALIDATORS
# =============================================================================

def validate_kerala_pincode(value: str, language: str = 'en') -> str:
    """
    Validate Kerala PIN code.

    Kerala PIN codes range from 670001 to 695999.

    Args:
        value: PIN code to validate
        language: Language for error message

    Returns:
        Validated PIN code

    Raises:
        ValidationError: If PIN code is invalid
    """
    cleaned = re.sub(r'\s', '', value)

    if not cleaned.isdigit() or len(cleaned) != 6:
        raise ValidationError(_t('invalid_pincode', language))

    pincode_int = int(cleaned)
    min_pin, max_pin = KERALA_PINCODES_RANGE

    if pincode_int < min_pin or pincode_int > max_pin:
        raise ValidationError(_t('invalid_pincode', language))

    return cleaned


class KeralaPincodeValidator:
    """Django validator for Kerala PIN codes."""

    def __init__(self, language: str = 'en'):
        self.language = language

    def __call__(self, value):
        validate_kerala_pincode(value, self.language)


# =============================================================================
# PAN CARD VALIDATORS
# =============================================================================

def validate_pan(value: str, language: str = 'en') -> str:
    """
    Validate Indian PAN (Permanent Account Number).

    Format: ABCDE1234F (5 letters + 4 digits + 1 letter)

    Args:
        value: PAN to validate
        language: Language for error message

    Returns:
        Uppercase PAN

    Raises:
        ValidationError: If PAN is invalid
    """
    cleaned = value.upper().strip()

    if not re.match(PAN_REGEX, cleaned):
        raise ValidationError(_t('invalid_pan', language))

    return cleaned


class PANValidator(RegexValidator):
    """Django validator for PAN numbers."""
    regex = PAN_REGEX
    message = msg(ValidationMessages.INVALID_PAN, 'en')
    code = 'invalid_pan'

    def __call__(self, value):
        super().__call__(value.upper().strip())


# =============================================================================
# GST VALIDATORS
# =============================================================================

def validate_gst(value: str, language: str = 'en') -> str:
    """
    Validate Indian GST (Goods and Services Tax) number.

    Format: 15-character alphanumeric
    Example: 22AAAAA0000A1Z5

    Args:
        value: GST number to validate
        language: Language for error message

    Returns:
        Uppercase GST number

    Raises:
        ValidationError: If GST number is invalid
    """
    cleaned = value.upper().strip()

    if not re.match(GST_REGEX, cleaned):
        raise ValidationError(_t('invalid_gst', language))

    return cleaned


class GSTValidator(RegexValidator):
    """Django validator for GST numbers."""
    regex = GST_REGEX
    message = msg(ValidationMessages.INVALID_GST, 'en')
    code = 'invalid_gst'

    def __call__(self, value):
        super().__call__(value.upper().strip())


# =============================================================================
# IFSC CODE VALIDATORS
# =============================================================================

def validate_ifsc(value: str, language: str = 'en') -> str:
    """
    Validate Indian IFSC (Indian Financial System Code).

    Format: 4 letters + 0 + 6 alphanumeric
    Example: SBIN0001234

    Args:
        value: IFSC code to validate
        language: Language for error message

    Returns:
        Uppercase IFSC code

    Raises:
        ValidationError: If IFSC code is invalid
    """
    cleaned = value.upper().strip()

    if not re.match(IFSC_REGEX, cleaned):
        raise ValidationError(_t('invalid_ifsc', language))

    return cleaned


class IFSCValidator(RegexValidator):
    """Django validator for IFSC codes."""
    regex = IFSC_REGEX
    message = msg(ValidationMessages.INVALID_IFSC, 'en')
    code = 'invalid_ifsc'

    def __call__(self, value):
        super().__call__(value.upper().strip())


# =============================================================================
# GEOGRAPHIC VALIDATORS
# =============================================================================

def validate_kerala_coordinates(
    latitude: float,
    longitude: float,
    language: str = 'en'
) -> tuple:
    """
    Validate coordinates are within Kerala boundaries.

    Kerala bounds:
        Latitude: 8.17° to 12.79° N
        Longitude: 74.86° to 77.42° E

    Args:
        latitude: Latitude value
        longitude: Longitude value
        language: Language for error message

    Returns:
        Tuple of (latitude, longitude)

    Raises:
        ValidationError: If coordinates are outside Kerala
    """
    lat_min = KERALA_BOUNDS['lat_min']
    lat_max = KERALA_BOUNDS['lat_max']
    lng_min = KERALA_BOUNDS['lng_min']
    lng_max = KERALA_BOUNDS['lng_max']

    if not (lat_min <= latitude <= lat_max and lng_min <= longitude <= lng_max):
        raise ValidationError(_t('invalid_coordinates', language))

    return (latitude, longitude)


class KeralaCoordinatesValidator:
    """Django validator for Kerala geographic coordinates."""

    def __init__(self, language: str = 'en'):
        self.language = language

    def __call__(self, value):
        if isinstance(value, (list, tuple)) and len(value) == 2:
            validate_kerala_coordinates(value[0], value[1], self.language)
        else:
            raise ValidationError("Invalid coordinate format. Expected [latitude, longitude].")


# =============================================================================
# FILE VALIDATORS
# =============================================================================

def validate_file_extension(
    filename: str,
    allowed_extensions: list = None,
    language: str = 'en'
) -> str:
    """
    Validate file extension.

    Args:
        filename: Name of the file
        allowed_extensions: List of allowed extensions (default: ALLOWED_DOCUMENT_EXTENSIONS)
        language: Language for error message

    Returns:
        Lowercase file extension

    Raises:
        ValidationError: If extension is not allowed
    """
    if allowed_extensions is None:
        allowed_extensions = ALLOWED_DOCUMENT_EXTENSIONS

    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''

    if ext not in allowed_extensions:
        raise ValidationError(
            _t('invalid_file_type', language, allowed_types=', '.join(allowed_extensions).upper())
        )

    return ext


def validate_file_size(
    file_size: int,
    max_size: int = None,
    language: str = 'en'
) -> int:
    """
    Validate file size.

    Args:
        file_size: Size of file in bytes
        max_size: Maximum allowed size in bytes (default: MAX_FILE_SIZE_BYTES)
        language: Language for error message

    Returns:
        File size

    Raises:
        ValidationError: If file size exceeds maximum
    """
    if max_size is None:
        max_size = MAX_FILE_SIZE_BYTES

    if file_size > max_size:
        max_mb = max_size / (1024 * 1024)
        raise ValidationError(
            _t('file_too_large', language, max_size=int(max_mb))
        )

    return file_size


class FileValidator:
    """Combined file validator for extension and size."""

    def __init__(
        self,
        allowed_extensions: list = None,
        max_size: int = None,
        language: str = 'en'
    ):
        self.allowed_extensions = allowed_extensions or ALLOWED_DOCUMENT_EXTENSIONS
        self.max_size = max_size or MAX_FILE_SIZE_BYTES
        self.language = language

    def __call__(self, file):
        validate_file_extension(file.name, self.allowed_extensions, self.language)
        validate_file_size(file.size, self.max_size, self.language)


# =============================================================================
# BANK ACCOUNT VALIDATORS
# =============================================================================

def validate_bank_account_number(value: str, language: str = 'en') -> str:
    """
    Validate Indian bank account number.

    Bank account numbers in India are typically 9-18 digits.

    Args:
        value: Account number to validate
        language: Language for error message

    Returns:
        Cleaned account number

    Raises:
        ValidationError: If account number is invalid
    """
    cleaned = re.sub(r'\s', '', value)

    if not cleaned.isdigit() or not (9 <= len(cleaned) <= 18):
        raise ValidationError(_t('invalid_account_number', language))

    return cleaned


# =============================================================================
# EMAIL VALIDATORS
# =============================================================================

def validate_email_format(value: str, language: str = 'en') -> str:
    """
    Validate email format.

    Args:
        value: Email to validate
        language: Language for error message

    Returns:
        Lowercase email

    Raises:
        ValidationError: If email format is invalid
    """
    # Basic email regex
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    cleaned = value.lower().strip()

    if not re.match(email_regex, cleaned):
        raise ValidationError(_t('invalid_email', language))

    return cleaned


# =============================================================================
# DISTRICT VALIDATOR
# =============================================================================

def validate_kerala_district(value: str, language: str = 'en') -> str:
    """
    Validate Kerala district code.

    Args:
        value: District code to validate
        language: Language for error message

    Returns:
        Uppercase district code

    Raises:
        ValidationError: If district code is invalid
    """
    from .constants import District

    cleaned = value.upper().strip()
    valid_codes = [choice.value for choice in District]

    if cleaned not in valid_codes:
        raise ValidationError(_t('invalid_district', language))

    return cleaned


# =============================================================================
# PASSWORD STRENGTH VALIDATOR (KAU RCD Reply, June 2026)
# =============================================================================

def validate_password_strength(value: str) -> str:
    """
    Validate password meets KAU security requirements:
    - Minimum 8 characters
    - At least 1 uppercase letter
    - At least 1 lowercase letter
    - At least 1 digit
    - At least 1 special character

    Raises:
        ValidationError: If any requirement is not met
    """
    errors = []
    if len(value) < 8:
        errors.append('Password must be at least 8 characters long.')
    if not re.search(r'[A-Z]', value):
        errors.append('Password must contain at least one uppercase letter.')
    if not re.search(r'[a-z]', value):
        errors.append('Password must contain at least one lowercase letter.')
    if not re.search(r'[0-9]', value):
        errors.append('Password must contain at least one number.')
    if not re.search(r'[!@#$%^&*(),.?":{}|<>\-_=+\[\];\'\\`~/]', value):
        errors.append('Password must contain at least one special character (e.g. @, #, $).')
    if errors:
        raise ValidationError(errors)
    return value
