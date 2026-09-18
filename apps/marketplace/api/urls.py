from django.urls import include, path
from rest_framework.routers import DefaultRouter
from apps.marketplace.api.buyer_dashboard import BuyerDashboardView

from apps.marketplace.api.buyer_products import BuyerProductListView

from apps.marketplace.api.buyers import FPOBuyerListViewSet
#arunima 16 th sep 
from apps.marketplace.api.inquiries import InquiryCreateView, InquiryViewSet, MarketHubInquiryViewSet
#-------
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
#arunima 16 th sep 
router.register(r'inquiries', InquiryViewSet, basename='marketplace-inquiry')
router.register(r'market-hub-inquiries', MarketHubInquiryViewSet, basename='marketplace-market-hub-inquiry')

urlpatterns = [
    path('', include(router.urls)),
    # Plain APIView, not router-registered — no CRUD, just one GET.
    path('opportunities/', MarketOpportunitiesView.as_view(), name='marketplace-opportunities'),
     # arunima 07 sep
    path('buyer/dashboard/', BuyerDashboardView.as_view(), name='buyer-dashboard'),
    path('buyer/products/', BuyerProductListView.as_view(), name='buyer-products'),
    #arunima 16 th sep 
    path('buyer/products/<int:pk>/inquire/', InquiryCreateView.as_view(), name='buyer-product-inquire'),
]