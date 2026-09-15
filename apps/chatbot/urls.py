from django.urls import include, path

app_name = 'chatbot'

urlpatterns = [
    path('', include('apps.chatbot.api.urls')),
]
