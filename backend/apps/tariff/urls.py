from django.urls import path
from . import views

urlpatterns = [
    path('lookup/', views.TariffLookupView.as_view(), name='tariff-lookup'),
    path('classify/', views.TariffClassifyView.as_view(), name='tariff-classify'),
    path(
        'products/<int:pk>/classification/',
        views.ProductHsClassificationView.as_view(),
        name='tariff-product-classification',
    ),
    path('logs/', views.TariffLookupLogListView.as_view(), name='tariff-logs'),
]
