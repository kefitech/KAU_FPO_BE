"""
Constants for KAU-FPO Platform
==============================

All constants are Python enums - ZERO database queries.
This ensures maximum performance as no DB lookup is needed.

Usage:
    from apps.core.utils.constants import District, UserRole, FPOStatus

    # Check user's role (via groups)
    user.groups.filter(name=UserRole.FPO_MANAGER).exists()

    # Assign district to FPO
    fpo.district = District.THRISSUR
"""

from django.db import models


# =============================================================================
# KERALA DISTRICTS (Fixed - 14 districts)
# =============================================================================

class District(models.TextChoices):
    """
    Kerala's 14 districts with 3-letter codes.
    Used for FPO location, user address, etc.
    """
    THIRUVANANTHAPURAM = "TVM", "Thiruvananthapuram"
    KOLLAM = "KLM", "Kollam"
    PATHANAMTHITTA = "PTA", "Pathanamthitta"
    ALAPPUZHA = "ALP", "Alappuzha"
    KOTTAYAM = "KTM", "Kottayam"
    IDUKKI = "IDK", "Idukki"
    ERNAKULAM = "EKM", "Ernakulam"
    THRISSUR = "TSR", "Thrissur"
    PALAKKAD = "PKD", "Palakkad"
    MALAPPURAM = "MLP", "Malappuram"
    KOZHIKODE = "KZD", "Kozhikode"
    WAYANAD = "WYD", "Wayanad"
    KANNUR = "KNR", "Kannur"
    KASARAGOD = "KSD", "Kasaragod"


# District names with Malayalam translations
DISTRICTS_BILINGUAL = {
    "TVM": ("Thiruvananthapuram", "തിരുവനന്തപുരം"),
    "KLM": ("Kollam", "കൊല്ലം"),
    "PTA": ("Pathanamthitta", "പത്തനംതിട്ട"),
    "ALP": ("Alappuzha", "ആലപ്പുഴ"),
    "KTM": ("Kottayam", "കോട്ടയം"),
    "IDK": ("Idukki", "ഇടുക്കി"),
    "EKM": ("Ernakulam", "എറണാകുളം"),
    "TSR": ("Thrissur", "തൃശ്ശൂർ"),
    "PKD": ("Palakkad", "പാലക്കാട്"),
    "MLP": ("Malappuram", "മലപ്പുറം"),
    "KZD": ("Kozhikode", "കോഴിക്കോട്"),
    "WYD": ("Wayanad", "വയനാട്"),
    "KNR": ("Kannur", "കണ്ണൂർ"),
    "KSD": ("Kasaragod", "കാസർഗോഡ്"),
}


def get_district_name(code: str, language: str = 'en') -> str:
    """
    Get district name in specified language.

    EN and ML are stored in DISTRICTS_BILINGUAL.
    Other languages (ta, hi, etc.) are resolved via Translation table
    using category='district', key=district_code.
    Admin adds new language translations via /api/admin/translations/.
    """
    if language not in ('en', 'ml'):
        try:
            from apps.core.services.translation import t
            result = t(f'district.{code}', language=language)
            if result != f'district.{code}':
                return result
        except Exception:
            pass

    names = DISTRICTS_BILINGUAL.get(code)
    if not names:
        return code
    return names[1] if language == 'ml' else names[0]


# =============================================================================
# USER ROLES
# =============================================================================

class UserRole(models.TextChoices):
    """
    User roles for RBAC (Role-Based Access Control).
    Each role has specific permissions defined in rbac.py.
    """
    SUPER_ADMIN = "super_admin", "Super Admin"
    SUB_ADMIN   = "sub_admin",   "Sub Admin"
    ADMIN       = "admin",       "Admin"
    FPO_MANAGER = "fpo_manager", "FPO Manager"
    GOVERNMENT  = "government",  "Government Official"
    CBBO        = "cbbo",        "CBBO/NGO"
    EXPERT      = "expert",      "Expert"
    VIEWER      = "viewer",      "Viewer"


# Role hierarchy (higher level can do everything lower level can)
ROLE_HIERARCHY = {
    UserRole.SUPER_ADMIN: 100,
    UserRole.SUB_ADMIN:   90,
    UserRole.ADMIN:       80,
    UserRole.GOVERNMENT:  60,
    UserRole.CBBO:        50,
    UserRole.FPO_MANAGER: 40,
    UserRole.EXPERT:      30,
    UserRole.VIEWER:      10,
}


# Available permissions that super admin can assign to sub-admins.
# Format: (codename, description)
# Add new entries here as new features are built.
SUB_ADMIN_PERMISSIONS = [
    ('can_approve_fpo',      'Can approve or reject FPO applications'),
    ('can_view_all_fpos',    'Can view all FPO profiles'),
    ('can_request_info',     'Can request additional info from FPO'),
    ('can_verify_documents', 'Can mark FPO documents as verified'),
    ('can_generate_reports', 'Can export FPO summary reports'),
]


# =============================================================================
# FPO STATUS
# =============================================================================

class FPOStatus(models.TextChoices):
    """
    FPO application workflow statuses.
    Defines the lifecycle of an FPO registration.
    """
    DRAFT = "draft", "Draft"
    SUBMITTED = "submitted", "Submitted"
    UNDER_REVIEW = "under_review", "Under Review"
    INFO_REQUIRED = "info_required", "Additional Info Required"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    SUSPENDED = "suspended", "Suspended"
    CLAIMED = "claimed", "Claimed (Ownership Transferred)"


# Valid status transitions (from_status -> [allowed_to_statuses])
FPO_STATUS_TRANSITIONS = {
    FPOStatus.DRAFT:         [FPOStatus.SUBMITTED],
    FPOStatus.SUBMITTED:     [FPOStatus.APPROVED, FPOStatus.UNDER_REVIEW, FPOStatus.REJECTED],
    FPOStatus.UNDER_REVIEW:  [FPOStatus.APPROVED, FPOStatus.REJECTED, FPOStatus.INFO_REQUIRED],
    FPOStatus.INFO_REQUIRED: [FPOStatus.SUBMITTED],
    FPOStatus.APPROVED:      [FPOStatus.SUSPENDED, FPOStatus.REJECTED, FPOStatus.CLAIMED],
    FPOStatus.REJECTED:      [FPOStatus.DRAFT],
    FPOStatus.SUSPENDED:     [FPOStatus.APPROVED],
}


def can_transition_fpo_status(from_status: str, to_status: str) -> bool:
    """
    Check if FPO status transition is valid.

    Args:
        from_status: Current status
        to_status: Target status

    Returns:
        True if transition is allowed
    """
    allowed = FPO_STATUS_TRANSITIONS.get(from_status, [])
    return to_status in allowed


# =============================================================================
# DOCUMENT TYPES
# =============================================================================

class DocumentType(models.TextChoices):
    """
    Types of documents for FPO registration.
    Each type has specific validation requirements.
    """
    FPO_REGISTRATION_CERT = "fpo_reg_cert", "FPO Registration Certificate"
    BANK_DETAILS = "bank_details", "Bank Account Details"
    SIGNATORY_ID = "signatory_id", "Authorized Signatory ID"
    PAN_CARD = "pan_card", "PAN Card"
    GST_CERTIFICATE = "gst_cert", "GST Certificate"
    ANNUAL_REPORT = "annual_report", "Annual Report"
    MEMBER_LIST = "member_list", "Member List"
    BOARD_RESOLUTION = "board_resolution", "Board Resolution"
    MOA_AOA = "moa_aoa", "MOA/AOA"
    OTHER = "other", "Other Document"
    CLAIM_SUPPORT = "claim_support", "Ownership Claim Supporting Document"


# Documents required for FPO registration (KAU confirmed 3 docs, June 2026)
# Signatory ID removed — Aadhaar last 4 digits captured as a form field
REQUIRED_DOCUMENTS = [
    DocumentType.FPO_REGISTRATION_CERT,
    DocumentType.BANK_DETAILS,
    DocumentType.PAN_CARD,
]

# Optional but recommended documents
OPTIONAL_DOCUMENTS = [
    DocumentType.GST_CERTIFICATE,
    DocumentType.ANNUAL_REPORT,
    DocumentType.MEMBER_LIST,
    DocumentType.BOARD_RESOLUTION,
    DocumentType.MOA_AOA,
]


# =============================================================================
# NOTIFICATION TYPES
# =============================================================================

class NotificationType(models.TextChoices):
    """Events that trigger notifications."""
    USER_REGISTERED = "user_registered", "User Registered"
    EMAIL_VERIFIED = "email_verified", "Email Verified"
    FPO_EMAIL_OTP = "fpo_email_otp", "FPO Email OTP Verification"
    FPO_PHONE_OTP = "fpo_phone_otp", "FPO Phone OTP Verification"
    FPO_SUBMITTED = "fpo_submitted", "FPO Application Submitted"
    ADMIN_NEW_FPO_APPLICATION = "admin_new_fpo_application", "Admin - New FPO Application"
    FPO_APPROVED = "fpo_approved", "FPO Application Approved"
    FPO_REJECTED = "fpo_rejected", "FPO Application Rejected"
    FPO_INFO_REQUIRED = "fpo_info_required", "Additional Info Required"
    PASSWORD_RESET = "password_reset", "Password Reset"
    PASSWORD_CHANGED = "password_changed", "Password Changed"
    DOCUMENT_UPLOADED = "document_uploaded", "Document Uploaded"
    ACCOUNT_SUSPENDED = "account_suspended", "Account Suspended"


class NotificationChannel(models.TextChoices):
    """Channels for sending notifications."""
    EMAIL = "email", "Email"
    SMS = "sms", "SMS"
    IN_APP = "in_app", "In-App"
    PUSH = "push", "Push Notification"


class DeliveryStatus(models.TextChoices):
    """Status of notification delivery."""
    QUEUED = "queued", "Queued"
    SENDING = "sending", "Sending"
    SENT = "sent", "Sent"
    DELIVERED = "delivered", "Delivered"
    FAILED = "failed", "Failed"
    BOUNCED = "bounced", "Bounced"


# =============================================================================
# LANGUAGE
# =============================================================================

class Language(models.TextChoices):
    """Supported languages."""
    ENGLISH = "en", "English"
    MALAYALAM = "ml", "Malayalam"


DEFAULT_LANGUAGE = Language.ENGLISH


# =============================================================================
# FILE SETTINGS
# =============================================================================

ALLOWED_DOCUMENT_EXTENSIONS = ['pdf', 'jpg', 'jpeg', 'png']
ALLOWED_IMAGE_EXTENSIONS = ['jpg', 'jpeg', 'png', 'gif', 'webp']
MAX_FILE_SIZE_MB = 5
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024  # 5MB in bytes
MAX_PROFILE_IMAGE_SIZE_MB = 2
MAX_PROFILE_IMAGE_SIZE_BYTES = MAX_PROFILE_IMAGE_SIZE_MB * 1024 * 1024


# =============================================================================
# KERALA SPECIFIC VALIDATION
# =============================================================================

KERALA_PINCODE_PREFIX = "6"
KERALA_PINCODES_RANGE = (670001, 695999)  # Kerala pincode range

KERALA_BOUNDS = {
    "lat_min": 8.17,
    "lat_max": 12.79,
    "lng_min": 74.86,
    "lng_max": 77.42
}

# Indian phone pattern
INDIAN_PHONE_REGEX = r'^[6-9]\d{9}$'

# PAN card pattern
PAN_REGEX = r'^[A-Z]{5}[0-9]{4}[A-Z]$'

# GST number pattern (15 digits)
GST_REGEX = r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$'

# IFSC code pattern
IFSC_REGEX = r'^[A-Z]{4}0[A-Z0-9]{6}$'


# =============================================================================
# FPO ELIGIBILITY CRITERIA
# =============================================================================

MIN_FPO_MEMBERS = 10  # Minimum members required for FPO registration
MIN_FPO_SHARE_CAPITAL = 100000  # Minimum share capital in INR (Rs. 1 Lakh)
MIN_FPO_FARMER_MEMBERS = 10  # Minimum farmer members


# =============================================================================
# PAGINATION
# =============================================================================

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


# =============================================================================
# CACHE KEYS & TTL
# =============================================================================

CACHE_TTL_SHORT = 60 * 5  # 5 minutes
CACHE_TTL_MEDIUM = 60 * 60  # 1 hour
CACHE_TTL_LONG = 60 * 60 * 24  # 24 hours

CACHE_KEY_PREFIX = {
    'lookup': 'lookup',
    'template': 'notif_template',
    'user': 'user',
    'fpo': 'fpo',
}

# =============================================================================
# PASSWORD RESET TOKEN TTLs
# =============================================================================

PASSWORD_RESET_EMAIL_TOKEN_TTL = 15 * 60   # 15 minutes
PASSWORD_RESET_OTP_TTL         = 10 * 60   # 10 minutes
PASSWORD_RESET_TOKEN_TTL       = 15 * 60   # 15 minutes (after OTP verified)


# =============================================================================
# API RESPONSE CODES
# =============================================================================

class ResponseCode(models.TextChoices):
    """Standard API response codes."""
    SUCCESS = "success", "Success"
    CREATED = "created", "Created"
    UPDATED = "updated", "Updated"
    DELETED = "deleted", "Deleted"
    ERROR = "error", "Error"
    VALIDATION_ERROR = "validation_error", "Validation Error"
    NOT_FOUND = "not_found", "Not Found"
    UNAUTHORIZED = "unauthorized", "Unauthorized"
    FORBIDDEN = "forbidden", "Forbidden"
    SERVER_ERROR = "server_error", "Server Error"
