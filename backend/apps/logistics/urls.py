from django.urls import path
from . import views

urlpatterns = [
    # order_number 없는 경로는 앞에
    path('dhub/instruct/', views.DHubDeliveryInstructionView.as_view(), name='dhub-instruct'),
    path('stagnated/', views.StagnatedShipmentsView.as_view(), name='stagnated-shipments'),
    path('customs/refund-due/', views.CustomsRefundDueView.as_view(), name='customs-refund-due'),
    path('failure/action-due/', views.DeliveryFailureActionDueView.as_view(), name='delivery-failure-due'),

    # 주문별 물류/배송/DHUB
    path('<str:order_number>/inspection/', views.InspectionView.as_view(), name='logistics-inspection'),
    path('<str:order_number>/timeline/', views.TrackingTimelineView.as_view(), name='tracking-timeline'),
    path('<str:order_number>/tracking/sync/', views.DHubTrackingSyncView.as_view(), name='dhub-tracking-sync'),
    path('<str:order_number>/tracking/', views.ShippingTrackingView.as_view(), name='shipping-tracking'),
    path('<str:order_number>/dhub/register/', views.DHubRegisterView.as_view(), name='dhub-register'),
    path('<str:order_number>/customs/refund/', views.CustomsRefundView.as_view(), name='customs-refund'),
    path('<str:order_number>/customs/respond/', views.CustomsRespondView.as_view(), name='customs-respond'),
    path('<str:order_number>/customs/', views.CustomsClearanceView.as_view(), name='customs-clearance'),
    path('<str:order_number>/failure/resolve/', views.DeliveryFailureResolveView.as_view(), name='delivery-failure-resolve'),
    path('<str:order_number>/failure/respond/', views.DeliveryFailureRespondView.as_view(), name='delivery-failure-respond'),
    path('<str:order_number>/failure/', views.DeliveryFailureView.as_view(), name='delivery-failure'),
    path('<str:order_number>/', views.LogisticsInfoView.as_view(), name='logistics-info'),
]
