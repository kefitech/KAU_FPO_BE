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

urlpatterns = [
    path('me/', MyRecommendationView.as_view(), name='my-recommendation'),
    path('me/request/', RequestRecommendationView.as_view(), name='request-recommendation'),
    path('me/feedback/', RecommendationFeedbackView.as_view(), name='recommendation-feedback'),
    path('pop/', CropPackageOfPracticesDetailView.as_view(), name='fpo-crop-pop'),
    # Service-to-service (ml_service startup sync), token-protected -- not FPO-facing
    path('internal/active-model/', MLModelActiveInternalView.as_view(), name='internal-active-model'),
]