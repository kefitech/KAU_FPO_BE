"""
Custom DRF Throttle Classes
===========================

IP-based rate limits for public/sensitive endpoints.
Rates are configured in settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'].

Usage on any APIView:
    from apps.core.utils.throttles import LoginThrottle

    class LoginView(APIView):
        throttle_classes = [LoginThrottle]
"""

from rest_framework.throttling import AnonRateThrottle


class LoginThrottle(AnonRateThrottle):
    scope = 'login'


class ForgotPasswordThrottle(AnonRateThrottle):
    scope = 'forgot_password'


class OTPVerifyThrottle(AnonRateThrottle):
    scope = 'otp_verify'


class RegisterThrottle(AnonRateThrottle):
    scope = 'register'


class TwoFactorLoginThrottle(AnonRateThrottle):
    scope = 'two_factor_login'


class TwoFactorSetupThrottle(AnonRateThrottle):
    scope = 'two_factor_setup'


class Disable2FAOTPThrottle(AnonRateThrottle):
    scope = 'disable_2fa_otp'
