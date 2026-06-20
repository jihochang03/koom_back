from django.urls import path
from . import views

urlpatterns = [
    path('lookup/', views.TariffLookupView.as_view(), name='tariff-lookup'),
    path('logs/', views.TariffLookupLogListView.as_view(), name='tariff-logs'),
]
