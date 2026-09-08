"""
Base: /api/experts/
"""
from django.urls import path

from .api.views import ExpertListView, ExpertDetailView, ExpertEnquiryView
from .api.me import MyExpertProfileView
from .api.booking_views import (
    ExpertAvailabilityView, CreateBookingView, CancelBookingView,
    AdminSetAvailabilityView, AdminBookingListView,
    AdminConfirmBookingView, AdminRejectBookingView, AdminRescheduleBookingView,
)

app_name = 'experts'

urlpatterns = [
    path('me/',                MyExpertProfileView.as_view(), name='expert-me'),
    path('',                   ExpertListView.as_view(),      name='expert-list'),
    path('<int:pk>/',          ExpertDetailView.as_view(),    name='expert-detail'),
    path('<int:pk>/enquiry/',  ExpertEnquiryView.as_view(),   name='expert-enquiry'),
    # FPO-side booking
    path('<int:pk>/availability/',   ExpertAvailabilityView.as_view(), name='expert-availability'),
    path('<int:pk>/book/',           CreateBookingView.as_view(),      name='expert-book'),
    path('bookings/<int:pk>/cancel/', CancelBookingView.as_view(),     name='booking-cancel'),
    # Admin-side booking management
    path('admin/<int:pk>/availability/',         AdminSetAvailabilityView.as_view(),    name='admin-set-availability'),
    path('admin/bookings/',                      AdminBookingListView.as_view(),        name='admin-booking-list'),
    path('admin/bookings/<int:pk>/confirm/',     AdminConfirmBookingView.as_view(),     name='admin-booking-confirm'),
    path('admin/bookings/<int:pk>/reject/',      AdminRejectBookingView.as_view(),      name='admin-booking-reject'),
    path('admin/bookings/<int:pk>/reschedule/',  AdminRescheduleBookingView.as_view(),  name='admin-booking-reschedule'),
]
