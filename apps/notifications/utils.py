"""
Notification Utilities
======================

Encryption/decryption for sensitive config values (passwords, API keys).

Uses Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256).
Encryption key is read from NOTIFICATION_ENCRYPTION_KEY in settings.

Key generation (run once, store in .env):
    from cryptography.fernet import Fernet
    print(Fernet.generate_key().decode())
"""

import logging
from django.conf import settings

logger = logging.getLogger(__name__)

# Fields that contain sensitive data and must be encrypted at rest
SENSITIVE_FIELDS = {'password', 'api_key', 'secret', 'token', 'auth_key'}


def _get_fernet():
    """Get Fernet instance using the encryption key from settings."""
    try:
        from cryptography.fernet import Fernet
        key = getattr(settings, 'NOTIFICATION_ENCRYPTION_KEY', None)
        if not key:
            raise ValueError("NOTIFICATION_ENCRYPTION_KEY not set in settings")
        return Fernet(key.encode() if isinstance(key, str) else key)
    except ImportError:
        raise ImportError("cryptography package required: pip install cryptography")


def encrypt_value(value: str) -> str:
    """Encrypt a sensitive string value."""
    f = _get_fernet()
    return f.encrypt(value.encode()).decode()


def decrypt_value(value: str) -> str:
    """Decrypt an encrypted string value."""
    f = _get_fernet()
    return f.decrypt(value.encode()).decode()


def encrypt_config(config: dict) -> dict:
    """
    Encrypt sensitive fields in a config dict before saving to DB.

    Only fields whose names are in SENSITIVE_FIELDS are encrypted.
    Non-sensitive fields (host, port, from_email etc.) are stored as-is.
    """
    encrypted = {}
    for key, value in config.items():
        if key in SENSITIVE_FIELDS and isinstance(value, str) and value:
            try:
                encrypted[key] = encrypt_value(value)
            except Exception as e:
                logger.error(f"Failed to encrypt config field '{key}': {e}")
                encrypted[key] = value
        else:
            encrypted[key] = value
    return encrypted


def decrypt_config(config: dict) -> dict:
    """
    Decrypt sensitive fields in a config dict when reading from DB.

    Safe to call even if values are already decrypted or empty.
    """
    decrypted = {}
    for key, value in config.items():
        if key in SENSITIVE_FIELDS and isinstance(value, str) and value:
            try:
                decrypted[key] = decrypt_value(value)
            except Exception:
                # Value might not be encrypted (e.g. during initial setup)
                decrypted[key] = value
        else:
            decrypted[key] = value
    return decrypted
