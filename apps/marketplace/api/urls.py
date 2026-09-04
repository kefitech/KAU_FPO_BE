from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.marketplace.api.buyers import FPOBuyerListViewSet
from apps.marketplace.api.market_prices import MarketOpportunitiesView, MarketPriceViewSet
from apps.marketplace.api.matches import BuyerSellerMatchViewSet
from apps.marketplace.api.products import ProductViewSet

# FPO-facing marketplace routes only.
# Admin routes (buyers CRUD, admin matches, admin price seeding) are
# registered in apps/accounts/api/admin/urls.py instead — that's where
# ALL admin endpoints live project-wide (confirmed via config/urls.py:
# path('api/admin/', include('apps.accounts.api.admin.urls'))).

router = DefaultRouter()
router.register(r'products', ProductViewSet, basename='marketplace-product')
router.register(r'buyers', FPOBuyerListViewSet, basename='marketplace-buyer')
router.register(r'matches', BuyerSellerMatchViewSet, basename='marketplace-match')
router.register(r'prices', MarketPriceViewSet, basename='marketplace-price')

urlpatterns = [
    path('', include(router.urls)),
    # Plain APIView, not router-registered — no CRUD, just one GET.
    path('opportunities/', MarketOpportunitiesView.as_view(), name='marketplace-opportunities'),
]