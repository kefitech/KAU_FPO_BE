"""
Recommendations API URLs — P2-06 (FPO-facing only)
"""
from django.urls import path

from apps.recommendations.api.recommendations import (
    MyRecommendationView,
    RequestRecommendationView,
    RecommendationFeedbackView,
    CropPackageOfPracticesDetailView,
)

urlpatterns = [
    path('me/', MyRecommendationView.as_view(), name='my-recommendation'),
    path('me/request/', RequestRecommendationView.as_view(), name='request-recommendation'),
    path('me/feedback/', RecommendationFeedbackView.as_view(), name='recommendation-feedback'),
    # Crop Package of Practices — FPO-facing lookup (Aravind — P2-06)
    path('pop/', CropPackageOfPracticesDetailView.as_view(), name='fpo-crop-pop'),
]