from django.urls import path
from . import views

urlpatterns = [
    path('exchange-rate/', views.ExchangeRateView.as_view(), name='exchange-rate'),
    path('quote/', views.PricingQuoteView.as_view(), name='pricing-quote'),
    path('logs/', views.PricingQuoteLogListView.as_view(), name='pricing-logs'),
]
