from django.urls import path
from . import views

urlpatterns = [
    path('<str:customer_id>/addresses/', views.AddressListView.as_view(), name='address-list'),
    path('<str:customer_id>/addresses/<int:addr_id>/', views.AddressDetailView.as_view(), name='address-detail'),
    path('<str:customer_id>/coupons/', views.UserCouponListView.as_view(), name='coupon-list'),
    path('<str:customer_id>/points/', views.PointLogListView.as_view(), name='point-list'),
    path('<str:customer_id>/notifications/', views.NotificationSettingView.as_view(), name='notification-setting'),
    path('coupons/', views.CouponAdminListView.as_view(), name='coupon-admin-list'),
    path('coupons/<int:coupon_id>/', views.CouponAdminDetailView.as_view(), name='coupon-admin-detail'),
    path('coupons/<int:coupon_id>/issue/', views.UserCouponIssueView.as_view(), name='coupon-issue'),
]
