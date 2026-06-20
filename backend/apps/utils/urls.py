from django.urls import path
from . import views

urlpatterns = [
    path('zipcode/<str:code>/', views.ZipcodeView.as_view()),
]
