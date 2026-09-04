from django.urls import path

from apps.external_buyer.api.registration import BuyerSendEmailOTPView, BuyerVerifyEmailOTPView
from apps.external_buyer.api.auth import RegisterBuyerUserView

urlpatterns = [
    path('pre-register/send-email-otp/', BuyerSendEmailOTPView.as_view(), name='external-buyer-send-email-otp'),
    path('pre-register/verify-email-otp/', BuyerVerifyEmailOTPView.as_view(), name='external-buyer-verify-email-otp'),
    path('register/', RegisterBuyerUserView.as_view(), name='external-buyer-register'),
]