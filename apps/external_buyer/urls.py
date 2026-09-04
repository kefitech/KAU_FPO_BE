from django.urls import include, path

app_name = 'external_buyer'

urlpatterns = [
    path('', include('apps.external_buyer.api.urls')),
]