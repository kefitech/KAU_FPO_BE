"""
Arunima S


Marketplace-specific permission checks.

IsAdmin, IsFPOManager, IsAuthenticated all already exist in
apps.core.permissions.rbac — import those directly, don't redefine here.

IsApprovedFPO is genuinely new: rbac.IsFPOManager checks role/group
membership (is this user an fpo_manager at all), not approval *status*
(has this specific FPO been approved by admin). ARUNIMA.md / P2-11 business
rule 1 need the latter.

Confirmed against apps/core/utils/constants.py: FPOStatus.APPROVED = "approved".
"""

from rest_framework.permissions import BasePermission

from apps.core.utils.constants import FPOStatus


class IsApprovedFPO(BasePermission):
    """
    ARUNIMA.md: "Products (FPO — must be APPROVED to list products)"
    P2-11 README business rule 1: only APPROVED FPOs can list products.
    """

    message = 'Only approved FPOs can list products on the marketplace.'

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        fpo = getattr(user, 'fpo', None)
        if fpo is None:
            return False
        return fpo.status == FPOStatus.APPROVED