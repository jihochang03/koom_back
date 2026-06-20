from django.urls import path
from . import views

urlpatterns = [
    path('', views.OrderListView.as_view(), name='order-list'),
    path('groups/', views.OrderGroupListView.as_view(), name='order-group-list'),
    path('groups/create/', views.OrderGroupCreateView.as_view(), name='order-group-create'),
    path('groups/<str:group_number>/', views.OrderGroupDetailView.as_view(), name='order-group-detail'),
    path('admin/dashboard/', views.AdminDashboardView.as_view(), name='admin-dashboard'),
    path('admin/list/', views.AdminOrderListView.as_view(), name='admin-order-list'),
    path('<str:order_number>/status-log/', views.OrderStatusLogView.as_view(), name='order-status-log'),
    path('<str:order_number>/action-log/', views.AdminActionLogView.as_view(), name='order-action-log'),
    path('<str:order_number>/error/', views.ErrorInfoView.as_view(), name='order-error-info'),
    path('<str:order_number>/pg/', views.PGTransactionListView.as_view(), name='order-pg'),
    path('<str:order_number>/snapshot/', views.ProductSnapshotView.as_view(), name='order-snapshot'),
    path('snapshots/<uuid:snapshot_uuid>/', views.ProductSnapshotPublicView.as_view(), name='snapshot-public'),
    path('snapshots/<uuid:snapshot_uuid>/html/', views.ProductSnapshotHTMLView.as_view(), name='snapshot-html'),
    path('<str:order_number>/', views.OrderDetailView.as_view(), name='order-detail'),
    path('<str:order_number>/status/', views.OrderStatusUpdateView.as_view(), name='order-status-update'),
    path('<str:order_number>/admin/', views.OrderAdminUpdateView.as_view(), name='order-admin-update'),
]
