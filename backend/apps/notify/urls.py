from django.urls import path
from . import views

urlpatterns = [
    path('send/', views.NotifySendView.as_view()),
    path('logs/', views.NotifyLogView.as_view()),
]
