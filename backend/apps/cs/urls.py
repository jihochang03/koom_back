from django.urls import path
from . import views

urlpatterns = [
    path('inquiries/', views.InquiryListView.as_view(), name='inquiry-list'),
    path('inquiries/<int:pk>/', views.InquiryDetailView.as_view(), name='inquiry-detail'),
    path('cancel/', views.CancelRequestListView.as_view(), name='cancel-list'),
    path('cancel/<int:pk>/', views.CancelRequestDetailView.as_view(), name='cancel-detail'),
    path('refund/', views.RefundRequestListView.as_view(), name='refund-list'),
    path('refund/<int:pk>/', views.RefundRequestDetailView.as_view(), name='refund-detail'),
    path('refund/<int:pk>/execute/', views.RefundExecuteView.as_view(), name='refund-execute'),
    # 대리구매 작업 (FR-ORD-07, C-01)
    path('purchase-tasks/', views.PurchaseTaskListView.as_view(), name='purchase-task-list'),
    path('purchase-tasks/<str:order_number>/complete/', views.PurchaseTaskCompleteView.as_view(), name='purchase-task-complete'),
]
