from django.urls import path
from . import views

urlpatterns = [
    path('line/login/',    views.LineLoginView.as_view()),
    path('line/callback/', views.LineCallbackView.as_view()),
    path('verify/',        views.TokenVerifyView.as_view()),
]
