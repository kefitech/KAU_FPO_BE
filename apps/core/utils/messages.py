"""
Bilingual Message System for KAU-FPO Platform
=============================================

All messages in (English, Malayalam) tuples.
NO DATABASE QUERIES - Pure Python for maximum performance.

Usage:
    from apps.core.utils.messages import AuthMessages, msg

    # Get message with language
    message = msg(AuthMessages.LOGIN_SUCCESS, 'ml')  # Malayalam
    message = msg(AuthMessages.LOGIN_SUCCESS, 'en')  # English (default)

    # With formatting
    message = msg(AuthMessages.ACCOUNT_LOCKED, 'en', minutes=30)
"""

from typing import Tuple, Optional

# Language indices for message tuples
EN = 0  # English index
ML = 1  # Malayalam index


class AuthMessages:
    """Authentication and account related messages."""

    LOGIN_SUCCESS: Tuple[str, str] = (
        "Login successful",
        "ലോഗിൻ വിജയകരം"
    )
    INVALID_CREDENTIALS: Tuple[str, str] = (
        "Invalid email or password",
        "തെറ്റായ ഇമെയിൽ അല്ലെങ്കിൽ രഹസ്യവാക്ക്"
    )
    ACCOUNT_DISABLED: Tuple[str, str] = (
        "Your account has been disabled. Please contact support.",
        "നിങ്ങളുടെ അക്കൗണ്ട് നിർജ്ജീവമാക്കി. ദയവായി സപ്പോർട്ടുമായി ബന്ധപ്പെടുക."
    )
    ACCOUNT_NOT_VERIFIED: Tuple[str, str] = (
        "Please verify your email before logging in",
        "ലോഗിൻ ചെയ്യുന്നതിന് മുമ്പ് നിങ്ങളുടെ ഇമെയിൽ പരിശോധിക്കുക"
    )
    TOKEN_EXPIRED: Tuple[str, str] = (
        "Session expired. Please login again.",
        "സെഷൻ കാലഹരണപ്പെട്ടു. വീണ്ടും ലോഗിൻ ചെയ്യുക."
    )
    TOKEN_INVALID: Tuple[str, str] = (
        "Invalid or expired token",
        "അസാധുവായ അല്ലെങ്കിൽ കാലഹരണപ്പെട്ട ടോക്കൺ"
    )
    LOGOUT_SUCCESS: Tuple[str, str] = (
        "Logged out successfully",
        "വിജയകരമായി ലോഗൗട്ട് ചെയ്തു"
    )
    TOKEN_REFRESHED: Tuple[str, str] = (
        "Token refreshed successfully",
        "ടോക്കൺ വിജയകരമായി പുതുക്കി"
    )
    REGISTRATION_SUCCESS: Tuple[str, str] = (
        "Registration successful. Please check your email for verification.",
        "രജിസ്ട്രേഷൻ വിജയകരം. പരിശോധനയ്ക്കായി ഇമെയിൽ പരിശോധിക്കുക."
    )
    EMAIL_ALREADY_EXISTS: Tuple[str, str] = (
        "An account with this email already exists",
        "ഈ ഇമെയിലിൽ ഒരു അക്കൗണ്ട് ഇതിനകം നിലവിലുണ്ട്"
    )
    PHONE_ALREADY_EXISTS: Tuple[str, str] = (
        "An account with this phone number already exists",
        "ഈ ഫോൺ നമ്പറിൽ ഒരു അക്കൗണ്ട് ഇതിനകം നിലവിലുണ്ട്"
    )
    EMAIL_VERIFIED: Tuple[str, str] = (
        "Email verified successfully",
        "ഇമെയിൽ വിജയകരമായി പരിശോധിച്ചു"
    )
    EMAIL_VERIFICATION_SENT: Tuple[str, str] = (
        "Verification email sent successfully",
        "പരിശോധന ഇമെയിൽ വിജയകരമായി അയച്ചു"
    )
    PASSWORD_RESET_SENT: Tuple[str, str] = (
        "Password reset link sent to your email",
        "രഹസ്യവാക്ക് റീസെറ്റ് ലിങ്ക് നിങ്ങളുടെ ഇമെയിലിലേക്ക് അയച്ചു"
    )
    PASSWORD_CHANGED: Tuple[str, str] = (
        "Password changed successfully",
        "രഹസ്യവാക്ക് വിജയകരമായി മാറ്റി"
    )
    PROFILE_RETRIEVED: Tuple[str, str] = (
        "Profile retrieved successfully",
        "പ്രൊഫൈൽ വിജയകരമായി ലഭിച്ചു"
    )
    PASSWORD_MISMATCH: Tuple[str, str] = (
        "Passwords do not match",
        "പാസ്‌വേഡുകൾ പൊരുത്തപ്പെടുന്നില്ല"
    )
    CURRENT_PASSWORD_INCORRECT: Tuple[str, str] = (
        "Current password is incorrect",
        "നിലവിലെ രഹസ്യവാക്ക് തെറ്റാണ്"
    )
    ACCOUNT_LOCKED: Tuple[str, str] = (
        "Account locked due to too many failed attempts. Try after {{minutes}} minutes.",
        "നിരവധി പരാജയപ്പെട്ട ശ്രമങ്ങൾ കാരണം അക്കൗണ്ട് ലോക്ക് ചെയ്തു. {{minutes}} മിനിറ്റിന് ശേഷം ശ്രമിക്കുക."
    )
    USERNAME_ALREADY_EXISTS: Tuple[str, str] = (
        "An account with this username already exists",
        "ഈ ഉപയോക്തൃനാമത്തിൽ ഒരു അക്കൗണ്ട് ഇതിനകം നിലവിലുണ്ട്"
    )
    PASSWORD_TOO_SHORT: Tuple[str, str] = (
        "Password must be at least 8 characters long",
        "രഹസ്യവാക്ക് കുറഞ്ഞത് 8 അക്ഷരങ്ങൾ ദൈർഘ്യമുള്ളതായിരിക്കണം"
    )
    PASSWORD_TOO_WEAK: Tuple[str, str] = (
        "Password must contain at least one uppercase letter, one lowercase letter, and one number",
        "പാസ്‌വേഡിൽ കുറഞ്ഞത് ഒരു വലിയ അക്ഷരം, ഒരു ചെറിയ അക്ഷരം, ഒരു സംഖ്യ എന്നിവ അടങ്ങിയിരിക്കണം"
    )
    USER_CREATED: Tuple[str, str] = (
        "User account created successfully",
        "ഉപയോക്തൃ അക്കൗണ്ട് വിജയകരമായി സൃഷ്ടിച്ചു"
    )
    USER_UPDATED: Tuple[str, str] = (
        "User account updated successfully",
        "ഉപയോക്തൃ അക്കൗണ്ട് വിജയകരമായി അപ്‌ഡേറ്റ് ചെയ്തു"
    )
    USER_DELETED: Tuple[str, str] = (
        "User account deleted successfully",
        "ഉപയോക്തൃ അക്കൗണ്ട് വിജയകരമായി ഇല്ലാതാക്കി"
    )
    USER_NOT_FOUND: Tuple[str, str] = (
        "User account not found",
        "ഉപയോക്തൃ അക്കൗണ്ട് കണ്ടെത്തിയില്ല"
    )
    SUPER_ADMIN_CREATED: Tuple[str, str] = (
        "Super admin account created successfully",
        "സൂപ്പർ അഡ്മിൻ അക്കൗണ്ട് വിജയകരമായി സൃഷ്ടിച്ചു"
    )
    VALIDATION_FAILED: Tuple[str, str] = (
        "Validation failed. Please check your input.",
        "മൂല്യനിർണ്ണയം പരാജയപ്പെട്ടു. നിങ്ങളുടെ ഇൻപുട്ട് പരിശോധിക്കുക."
    )


class FPOMessages:
    """FPO registration and management messages."""

    FPO_REGISTERED: Tuple[str, str] = (
        "FPO registration submitted successfully. Application ID: {application_id}",
        "FPO രജിസ്ട്രേഷൻ വിജയകരമായി സമർപ്പിച്ചു. അപേക്ഷ ഐഡി: {application_id}"
    )
    FPO_UPDATED: Tuple[str, str] = (
        "FPO details updated successfully",
        "FPO വിവരങ്ങൾ വിജയകരമായി അപ്ഡേറ്റ് ചെയ്തു"
    )
    FPO_APPROVED: Tuple[str, str] = (
        "Congratulations! Your FPO application has been approved.",
        "അഭിനന്ദനങ്ങൾ! നിങ്ങളുടെ FPO അപേക്ഷ അംഗീകരിച്ചു."
    )
    FPO_REJECTED: Tuple[str, str] = (
        "Your FPO application has been rejected. Reason: {reason}",
        "നിങ്ങളുടെ FPO അപേക്ഷ നിരസിച്ചു. കാരണം: {reason}"
    )
    FPO_INFO_REQUIRED: Tuple[str, str] = (
        "Additional information required for your FPO application. Please update the requested details.",
        "നിങ്ങളുടെ FPO അപേക്ഷയ്ക്ക് അധിക വിവരങ്ങൾ ആവശ്യമാണ്. ദയവായി ആവശ്യപ്പെട്ട വിവരങ്ങൾ അപ്ഡേറ്റ് ചെയ്യുക."
    )
    FPO_NOT_FOUND: Tuple[str, str] = (
        "FPO not found",
        "FPO കണ്ടെത്തിയില്ല"
    )
    FPO_SUSPENDED: Tuple[str, str] = (
        "Your FPO has been suspended. Reason: {reason}",
        "നിങ്ങളുടെ FPO താൽക്കാലികമായി നിർത്തിവച്ചു. കാരണം: {reason}"
    )
    ELIGIBILITY_FAILED: Tuple[str, str] = (
        "FPO does not meet the eligibility criteria: {criteria}",
        "FPO യോഗ്യതാ മാനദണ്ഡങ്ങൾ പാലിക്കുന്നില്ല: {criteria}"
    )
    CANNOT_EDIT_STATUS: Tuple[str, str] = (
        "Cannot edit FPO in '{status}' status",
        "'{status}' സ്റ്റാറ്റസിൽ FPO എഡിറ്റ് ചെയ്യാൻ കഴിയില്ല"
    )
    INVALID_STATUS_TRANSITION: Tuple[str, str] = (
        "Cannot change status from '{from_status}' to '{to_status}'",
        "'{from_status}' ൽ നിന്ന് '{to_status}' ലേക്ക് സ്റ്റാറ്റസ് മാറ്റാൻ കഴിയില്ല"
    )
    MEMBER_ADDED: Tuple[str, str] = (
        "Member added successfully",
        "അംഗത്തെ വിജയകരമായി ചേർത്തു"
    )
    MEMBER_REMOVED: Tuple[str, str] = (
        "Member removed successfully",
        "അംഗത്തെ വിജയകരമായി നീക്കം ചെയ്തു"
    )
    # Email verification
    OFFICE_EMAIL_REQUIRED: Tuple[str, str] = (
        "Office email is required. Complete Step 2 before requesting OTP.",
        "ഓഫീസ് ഇമെയിൽ ആവശ്യമാണ്. OTP അഭ്യർത്ഥിക്കുന്നതിന് മുമ്പ് ഘട്ടം 2 പൂർത്തിയാക്കുക."
    )
    EMAIL_ALREADY_VERIFIED: Tuple[str, str] = (
        "Office email is already verified.",
        "ഓഫീസ് ഇമെയിൽ ഇതിനകം സ്ഥിരീകരിച്ചിട്ടുണ്ട്."
    )
    EMAIL_OTP_SENT: Tuple[str, str] = (
        "OTP sent to your office email. Valid for 10 minutes.",
        "OTP നിങ്ങളുടെ ഓഫീസ് ഇമെയിലിലേക്ക് അയച്ചു. 10 മിനിറ്റ് സാധുവാണ്."
    )
    EMAIL_VERIFIED: Tuple[str, str] = (
        "Office email verified successfully.",
        "ഓഫീസ് ഇമെയിൽ വിജയകരമായി സ്ഥിരീകരിച്ചു."
    )
    # Phone verification
    OFFICE_PHONE_REQUIRED: Tuple[str, str] = (
        "Office phone is required. Complete Step 2 before requesting OTP.",
        "ഓഫീസ് ഫോൺ ആവശ്യമാണ്. OTP അഭ്യർത്ഥിക്കുന്നതിന് മുമ്പ് ഘട്ടം 2 പൂർത്തിയാക്കുക."
    )
    PHONE_ALREADY_VERIFIED: Tuple[str, str] = (
        "Office phone is already verified.",
        "ഓഫീസ് ഫോൺ ഇതിനകം സ്ഥിരീകരിച്ചിട്ടുണ്ട്."
    )
    PHONE_OTP_SENT: Tuple[str, str] = (
        "OTP sent to your office phone via SMS. Valid for 10 minutes.",
        "OTP SMS വഴി നിങ്ങളുടെ ഓഫീസ് ഫോണിലേക്ക് അയച്ചു. 10 മിനിറ്റ് സാധുവാണ്."
    )
    PHONE_VERIFIED: Tuple[str, str] = (
        "Office phone verified successfully.",
        "ഓഫീസ് ഫോൺ വിജയകരമായി സ്ഥിരീകരിച്ചു."
    )
    INVALID_OR_EXPIRED_OTP: Tuple[str, str] = (
        "Invalid or expired OTP. Please request a new one.",
        "അസാധുവായ അല്ലെങ്കിൽ കാലഹരണപ്പെട്ട OTP. ദയവായി പുതിയ ഒന്ന് അഭ്യർത്ഥിക്കുക."
    )
    INVALID_OTP_WITH_ATTEMPTS: Tuple[str, str] = (
        "Incorrect OTP. {{attempts_remaining}} attempt(s) remaining. OTP is valid for {{validity_minutes}} minutes.",
        "തെറ്റായ OTP. {{attempts_remaining}} ശ്രമം(ങ്ങൾ) ശേഷിക്കുന്നു. OTP {{validity_minutes}} മിനിറ്റ് സാധുവാണ്."
    )
    OTP_ATTEMPTS_EXHAUSTED: Tuple[str, str] = (
        "Maximum attempts reached. Please request a new OTP.",
        "പരമാവധി ശ്രമങ്ങൾ കഴിഞ്ഞു. ദയവായി ഒരു പുതിയ OTP അഭ്യർത്ഥിക്കുക."
    )
    # Document upload
    INVALID_DOCUMENT_TYPE: Tuple[str, str] = (
        "Invalid document type.",
        "അസാധുവായ ഡോക്യുമെന്റ് തരം."
    )
    DOCUMENT_FILE_REQUIRED: Tuple[str, str] = (
        "Please select a file to upload.",
        "അപ്‌ലോഡ് ചെയ്യാൻ ഒരു ഫയൽ തിരഞ്ഞെടുക്കുക."
    )
    DOCUMENT_TOO_LARGE: Tuple[str, str] = (
        "File size exceeds the {limit} MB limit.",
        "ഫയൽ വലിപ്പം {limit} MB പരിധി കവിഞ്ഞു."
    )
    DOCUMENT_INVALID_FORMAT: Tuple[str, str] = (
        "Invalid file format. Allowed: PDF, JPG, PNG (XLSX for member list).",
        "അസാധുവായ ഫയൽ ഫോർമാറ്റ്. അനുവദനീയം: PDF, JPG, PNG (അംഗ പട്ടികയ്ക്ക് XLSX)."
    )
    DOCUMENT_UPLOADED: Tuple[str, str] = (
        "Document uploaded successfully.",
        "പ്രമാണം വിജയകരമായി അപ്‌ലോഡ് ചെയ്തു."
    )
    DOCUMENT_NOT_FOUND: Tuple[str, str] = (
        "Document not found.",
        "പ്രമാണം കണ്ടെത്തിയില്ല."
    )
    DOCUMENT_DELETED: Tuple[str, str] = (
        "Document deleted successfully.",
        "പ്രമാണം വിജയകരമായി ഇല്ലാതാക്കി."
    )
    # Submission
    OTP_RATE_LIMIT_EXCEEDED: Tuple[str, str] = (
        "Too many OTP requests. Please wait 10 minutes before trying again.",
        "അധിക OTP അഭ്യർത്ഥനകൾ. വീണ്ടും ശ്രമിക്കുന്നതിന് 10 മിനിറ്റ് കാത്തിരിക്കുക."
    )
    ALREADY_SUBMITTED: Tuple[str, str] = (
        "Application has already been submitted.",
        "അപേക്ഷ ഇതിനകം സമർപ്പിച്ചിട്ടുണ്ട്."
    )
    APPLICATION_SUBMITTED: Tuple[str, str] = (
        "Application submitted successfully. Your application ID is {application_id}.",
        "അപേക്ഷ വിജയകരമായി സമർപ്പിച്ചു. നിങ്ങളുടെ അപേക്ഷ ഐഡി: {application_id}."
    )
    APPLICATION_APPROVED: Tuple[str, str] = (
        "Your FPO registration has been approved. Your application ID is {application_id}.",
        "നിങ്ങളുടെ FPO രജിസ്ട്രേഷൻ അംഗീകരിക്കപ്പെട്ടു. അപേക്ഷ ഐഡി: {application_id}."
    )


class DocumentMessages:
    """Document upload and management messages."""

    DOCUMENT_UPLOADED: Tuple[str, str] = (
        "Document uploaded successfully",
        "പ്രമാണം വിജയകരമായി അപ്‌ലോഡ് ചെയ്തു"
    )
    DOCUMENT_DELETED: Tuple[str, str] = (
        "Document deleted successfully",
        "പ്രമാണം വിജയകരമായി ഇല്ലാതാക്കി"
    )
    DOCUMENT_REQUIRED: Tuple[str, str] = (
        "Required document missing: {document_type}",
        "ആവശ്യമായ പ്രമാണം കാണുന്നില്ല: {document_type}"
    )
    INVALID_FILE_TYPE: Tuple[str, str] = (
        "Invalid file type. Allowed types: {allowed_types}",
        "അസാധുവായ ഫയൽ തരം. അനുവദനീയമായ തരങ്ങൾ: {allowed_types}"
    )
    FILE_TOO_LARGE: Tuple[str, str] = (
        "File size exceeds maximum allowed size of {max_size}MB",
        "ഫയൽ വലിപ്പം പരമാവധി അനുവദനീയമായ {max_size}MB കവിയുന്നു"
    )
    DOCUMENT_NOT_FOUND: Tuple[str, str] = (
        "Document not found",
        "പ്രമാണം കണ്ടെത്തിയില്ല"
    )


class ValidationMessages:
    """Form and data validation messages."""

    REQUIRED: Tuple[str, str] = (
        "This field is required",
        "ഈ ഫീൽഡ് ആവശ്യമാണ്"
    )
    INVALID_EMAIL: Tuple[str, str] = (
        "Enter a valid email address",
        "സാധുവായ ഇമെയിൽ വിലാസം നൽകുക"
    )
    INVALID_PHONE: Tuple[str, str] = (
        "Enter a valid 10-digit Indian phone number",
        "സാധുവായ 10 അക്ക ഇന്ത്യൻ ഫോൺ നമ്പർ നൽകുക"
    )
    INVALID_PINCODE: Tuple[str, str] = (
        "Enter a valid Kerala pincode",
        "സാധുവായ കേരള പിൻകോഡ് നൽകുക"
    )
    INVALID_DISTRICT: Tuple[str, str] = (
        "Select a valid Kerala district",
        "സാധുവായ കേരള ജില്ല തിരഞ്ഞെടുക്കുക"
    )
    INVALID_PAN: Tuple[str, str] = (
        "Enter a valid PAN number (e.g., ABCDE1234F)",
        "സാധുവായ PAN നമ്പർ നൽകുക (ഉദാ: ABCDE1234F)"
    )
    INVALID_GST: Tuple[str, str] = (
        "Enter a valid 15-digit GST number",
        "സാധുവായ 15 അക്ക GST നമ്പർ നൽകുക"
    )
    INVALID_IFSC: Tuple[str, str] = (
        "Enter a valid IFSC code (e.g., SBIN0001234)",
        "സാധുവായ IFSC കോഡ് നൽകുക (ഉദാ: SBIN0001234)"
    )
    INVALID_ACCOUNT_NUMBER: Tuple[str, str] = (
        "Enter a valid bank account number",
        "സാധുവായ ബാങ്ക് അക്കൗണ്ട് നമ്പർ നൽകുക"
    )
    MIN_LENGTH: Tuple[str, str] = (
        "Minimum {min} characters required",
        "കുറഞ്ഞത് {min} അക്ഷരങ്ങൾ ആവശ്യമാണ്"
    )
    MAX_LENGTH: Tuple[str, str] = (
        "Maximum {max} characters allowed",
        "പരമാവധി {max} അക്ഷരങ്ങൾ അനുവദനീയമാണ്"
    )
    MIN_VALUE: Tuple[str, str] = (
        "Value must be at least {min}",
        "മൂല്യം കുറഞ്ഞത് {min} ആയിരിക്കണം"
    )
    MAX_VALUE: Tuple[str, str] = (
        "Value must not exceed {max}",
        "മൂല്യം {max} കവിയരുത്"
    )
    MIN_MEMBERS: Tuple[str, str] = (
        "Minimum {min} members required for FPO registration",
        "FPO രജിസ്ട്രേഷനായി കുറഞ്ഞത് {min} അംഗങ്ങൾ ആവശ്യമാണ്"
    )
    INVALID_DATE: Tuple[str, str] = (
        "Enter a valid date",
        "സാധുവായ തീയതി നൽകുക"
    )
    FUTURE_DATE_NOT_ALLOWED: Tuple[str, str] = (
        "Future date is not allowed",
        "ഭാവി തീയതി അനുവദനീയമല്ല"
    )
    PAST_DATE_NOT_ALLOWED: Tuple[str, str] = (
        "Past date is not allowed",
        "കഴിഞ്ഞ തീയതി അനുവദനീയമല്ല"
    )
    INVALID_COORDINATES: Tuple[str, str] = (
        "Location must be within Kerala boundaries",
        "സ്ഥാനം കേരള അതിർത്തിക്കുള്ളിൽ ആയിരിക്കണം"
    )


class CommonMessages:
    """Common/generic messages used across the application."""

    CREATED: Tuple[str, str] = (
        "Created successfully",
        "വിജയകരമായി സൃഷ്ടിച്ചു"
    )
    UPDATED: Tuple[str, str] = (
        "Updated successfully",
        "വിജയകരമായി അപ്‌ഡേറ്റ് ചെയ്തു"
    )
    DELETED: Tuple[str, str] = (
        "Deleted successfully",
        "വിജയകരമായി ഇല്ലാതാക്കി"
    )
    NOT_FOUND: Tuple[str, str] = (
        "The requested resource was not found",
        "അഭ്യർത്ഥിച്ച വിഭവം കണ്ടെത്തിയില്ല"
    )
    PERMISSION_DENIED: Tuple[str, str] = (
        "You do not have permission to perform this action",
        "ഈ പ്രവർത്തനം ചെയ്യാൻ നിങ്ങൾക്ക് അനുമതിയില്ല"
    )
    UNAUTHORIZED: Tuple[str, str] = (
        "Authentication required. Please login.",
        "പ്രാമാണീകരണം ആവശ്യമാണ്. ദയവായി ലോഗിൻ ചെയ്യുക."
    )
    SERVER_ERROR: Tuple[str, str] = (
        "An unexpected error occurred. Please try again later.",
        "അപ്രതീക്ഷിത പിശക് സംഭവിച്ചു. പിന്നീട് വീണ്ടും ശ്രമിക്കുക."
    )
    BAD_REQUEST: Tuple[str, str] = (
        "Invalid request. Please check your input.",
        "അസാധുവായ അഭ്യർത്ഥന. നിങ്ങളുടെ ഇൻപുട്ട് പരിശോധിക്കുക."
    )
    RATE_LIMITED: Tuple[str, str] = (
        "Too many requests. Please try again after {{seconds}} seconds.",
        "നിരവധി അഭ്യർത്ഥനകൾ. {{seconds}} സെക്കൻഡിന് ശേഷം വീണ്ടും ശ്രമിക്കുക."
    )
    OPERATION_NOT_ALLOWED: Tuple[str, str] = (
        "This operation is not allowed",
        "ഈ പ്രവർത്തനം അനുവദനീയമല്ല"
    )
    DUPLICATE_ENTRY: Tuple[str, str] = (
        "A record with this information already exists",
        "ഈ വിവരങ്ങളുള്ള ഒരു റെക്കോർഡ് ഇതിനകം നിലവിലുണ്ട്"
    )


class NotificationMessages:
    """Notification related messages."""

    NOTIFICATION_SENT: Tuple[str, str] = (
        "Notification sent successfully",
        "അറിയിപ്പ് വിജയകരമായി അയച്ചു"
    )
    NOTIFICATION_FAILED: Tuple[str, str] = (
        "Failed to send notification",
        "അറിയിപ്പ് അയയ്ക്കുന്നതിൽ പരാജയപ്പെട്ടു"
    )
    MARKED_AS_READ: Tuple[str, str] = (
        "Notification marked as read",
        "അറിയിപ്പ് വായിച്ചതായി അടയാളപ്പെടുത്തി"
    )
    ALL_MARKED_AS_READ: Tuple[str, str] = (
        "All notifications marked as read",
        "എല്ലാ അറിയിപ്പുകളും വായിച്ചതായി അടയാളപ്പെടുത്തി"
    )


class RoleMessages:
    """Role management related messages."""

    ROLE_CREATED: Tuple[str, str] = (
        "Role created successfully",
        "റോൾ വിജയകരമായി സൃഷ്ടിച്ചു"
    )
    ROLE_UPDATED: Tuple[str, str] = (
        "Role updated successfully",
        "റോൾ വിജയകരമായി അപ്‌ഡേറ്റ് ചെയ്തു"
    )
    ROLE_DELETED: Tuple[str, str] = (
        "Role deleted successfully",
        "റോൾ വിജയകരമായി ഇല്ലാതാക്കി"
    )
    ROLES_RETRIEVED: Tuple[str, str] = (
        "Roles retrieved successfully",
        "റോളുകൾ വിജയകരമായി വീണ്ടെടുത്തു"
    )
    ROLE_NOT_FOUND: Tuple[str, str] = (
        "Role not found",
        "റോൾ കണ്ടെത്തിയില്ല"
    )
    ROLE_ALREADY_EXISTS: Tuple[str, str] = (
        "Role with name '{name}' already exists",
        "'{name}' എന്ന പേരിൽ റോൾ ഇതിനകം നിലവിലുണ്ട്"
    )
    ROLE_NAME_REQUIRED: Tuple[str, str] = (
        "Role name cannot be empty",
        "റോൾ പേര് ശൂന്യമാകരുത്"
    )
    ROLE_HAS_USERS: Tuple[str, str] = (
        "Cannot delete role. {count} user(s) are assigned to this role",
        "റോൾ ഇല്ലാതാക്കാൻ കഴിയില്ല. {count} ഉപയോക്താക്കൾ ഈ റോളിലേക്ക് നിയോഗിച്ചിട്ടുണ്ട്"
    )
    VALIDATION_FAILED: Tuple[str, str] = (
        "Validation failed",
        "മൂല്യനിർണ്ണയം പരാജയപ്പെട്ടു"
    )


# =============================================================================
# MESSAGE HELPER FUNCTIONS
# =============================================================================

def get_message(message_tuple: Tuple[str, str], language: str = 'en', **kwargs) -> str:
    """
    Get message in specified language with optional formatting.

    Args:
        message_tuple: Tuple of (English, Malayalam) messages
        language: 'en' for English, 'ml' for Malayalam
        **kwargs: Format arguments for message

    Returns:
        Formatted message in specified language

    Example:
        message = get_message(AuthMessages.ACCOUNT_LOCKED, 'en', minutes=30)
        # Returns: "Account locked due to too many failed attempts. Try after 30 minutes."
    """
    index = ML if language == 'ml' else EN
    message = message_tuple[index]

    if kwargs:
        try:
            message = message.format(**kwargs)
        except KeyError:
            # If format fails, return message as-is
            pass

    return message


def msg(message_tuple: Tuple[str, str], language: str = 'en', **kwargs) -> str:
    """
    Shorthand for get_message().

    Args:
        message_tuple: Tuple of (English, Malayalam) messages
        language: 'en' for English, 'ml' for Malayalam
        **kwargs: Format arguments for message

    Returns:
        Formatted message in specified language
    """
    return get_message(message_tuple, language, **kwargs)


def get_both_messages(message_tuple: Tuple[str, str], **kwargs) -> dict:
    """
    Get message in both languages.

    Args:
        message_tuple: Tuple of (English, Malayalam) messages
        **kwargs: Format arguments for message

    Returns:
        Dict with 'en' and 'ml' keys

    Example:
        messages = get_both_messages(CommonMessages.CREATED)
        # Returns: {'en': 'Created successfully', 'ml': 'വിജയകരമായി സൃഷ്ടിച്ചു'}
    """
    return {
        'en': get_message(message_tuple, 'en', **kwargs),
        'ml': get_message(message_tuple, 'ml', **kwargs),
    }
