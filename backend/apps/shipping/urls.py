from django.urls import path
from . import views

urlpatterns = [
    path('quote/', views.ShippingQuoteView.as_view(), name='shipping-quote'),
    path('logs/', views.ShippingQuoteLogListView.as_view(), name='shipping-logs'),
    path('intl-estimate/', views.IntlShippingEstimateView.as_view(), name='shipping-intl-estimate'),
]
