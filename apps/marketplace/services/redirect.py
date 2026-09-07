"""
Buyer Redirect Service
=======================
Determines whether a logged-in user is a buyer (external or FPO-as-buyer),
and if so, what their verification status is.

Mirrors apps/fpo/services/redirect.py's pattern exactly.
Backend never hardcodes frontend URLs — frontend owns route mapping.

Returns:
    {'status': 'pending' | 'verified' | 'rejected'}  if user is a buyer
    None                                              if user is not a buyer
"""
from apps.database.models import BuyerDirectory


def _get_buyer_row(user):
    """Resolve the BuyerDirectory row for this user, whichever way they're linked."""
    buyer = getattr(user, 'buyer_profile', None)
    if buyer is not None:
        return buyer

    fpo = getattr(user, 'fpo', None)
    if fpo is not None:
        buyer = getattr(fpo, 'buyer_registration', None)
        if buyer is not None:
            return buyer

    return None


def get_buyer_redirect(user):
    """
    Return redirect status dict for buyer users (external or FPO-as-buyer).
    Returns None if the user has no BuyerDirectory row at all.
    """
    buyer = _get_buyer_row(user)
    if buyer is None:
        return None
    return {'status': buyer.status}