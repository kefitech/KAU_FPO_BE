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

from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.core.services.fpo_permission import get_member_fpo, has_fpo_permission
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
        # The primary user or an active team member of the FPO
        fpo = get_member_fpo(user)
        if fpo is None:
            return False
        return fpo.status == FPOStatus.APPROVED


class CanManageProducts(BasePermission):
    """
    Reads are open to every FPO member; changes need `can_manage_products`
    (always true for the primary user, granted per member by the primary).
    """

    message = 'You do not have permission to manage products.'

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return has_fpo_permission(request.user, get_member_fpo(request.user), 'can_manage_products')