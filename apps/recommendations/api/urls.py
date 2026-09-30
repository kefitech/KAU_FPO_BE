"""
Recommendations API URLs — P2-06 (FPO-facing only)
"""
from django.urls import path

from apps.recommendations.api.recommendations import (
    MyRecommendationView,
    RequestRecommendationView,
    RecommendationFeedbackView,
    CropPackageOfPracticesDetailView,
    MLModelActiveInternalView,
)
from apps.recommendations.api.business_plan import (
    MyBusinessPlanView,
    GenerateBusinessPlanView,
)

urlpatterns = [
    path('me/', MyRecommendationView.as_view(), name='my-recommendation'),
    path('me/request/', RequestRecommendationView.as_view(), name='request-recommendation'),
    path('me/feedback/', RecommendationFeedbackView.as_view(), name='recommendation-feedback'),
    path('pop/', CropPackageOfPracticesDetailView.as_view(), name='fpo-crop-pop'),
    path('business-plan/me/', MyBusinessPlanView.as_view(), name='my-business-plan'),
    path('business-plan/me/generate/', GenerateBusinessPlanView.as_view(), name='generate-business-plan'),
    # Service-to-service (ml_service startup sync), token-protected -- not FPO-facing
    path('internal/active-model/', MLModelActiveInternalView.as_view(), name='internal-active-model'),
]