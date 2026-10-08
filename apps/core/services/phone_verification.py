"""
Phone-change verification
=========================
A new phone number may only be saved to a user's profile after it has been
verified by OTP. POST /api/fpo/pre-register/send-otp/ + verify-otp/ issue a
one-time phone_token (30 min TTL) bound to the verified number; the profile
endpoints consume it here before saving that number.
"""

from django.core.cache import cache

PHONE_OTP_REQUIRED_MESSAGE = 'Verify the new phone number with OTP before saving it.'


def consume_phone_token(token, phone):
    """True if `token` was issued by verify-otp for exactly `phone`. Single use."""
    if not token:
        return False
    key = f'fpo:prereg_phone_token:{token}'
    if cache.get(key) != phone:
        return False
    cache.delete(key)
    return True
