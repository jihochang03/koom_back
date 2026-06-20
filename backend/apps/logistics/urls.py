from django.urls import path
from . import views

urlpatterns = [
    # DHUB 배송지시 (order_number 없는 경로는 앞에)
    path('dhub/instruct/', views.DHubDeliveryInstructionView.as_view(), name='dhub-instruct'),
    path('stagnated/', views.StagnatedShipmentsView.as_view(), name='stagnated-shipments'),

    # 주문별 물류/배송/DHUB
    path('<str:order_number>/', views.LogisticsInfoView.as_view(), name='logistics-info'),
    path('<str:order_number>/inspection/', views.InspectionView.as_view(), name='logistics-inspection'),
    path('<str:order_number>/tracking/', views.ShippingTrackingView.as_view(), name='shipping-tracking'),
    path('<str:order_number>/tracking/sync/', views.DHubTrackingSyncView.as_view(), name='dhub-tracking-sync'),
    path('<str:order_number>/dhub/register/', views.DHubRegisterView.as_view(), name='dhub-register'),
]
