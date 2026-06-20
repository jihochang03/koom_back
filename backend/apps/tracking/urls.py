from django.urls import path
from . import views

urlpatterns = [
    path('carriers/', views.TrackingCarriersView.as_view()),
    path('<str:carrier_code>/<str:tracking_number>/', views.TrackingView.as_view()),
]
